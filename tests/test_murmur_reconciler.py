from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from bg.pulse.reconciler import (
    MurmurReconcileAction,
    MurmurRegistrationReconciler,
    _MurmurServerAdapter,
)
from tests.conftest import IceOwnedInvalidUserException


class _FakeAdapter:
    live_usernames: list[str] = []

    def __init__(self, server):
        self.server = server

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def list_registered_usernames(self):
        return list(self.live_usernames)


class MurmurRegistrationReconcilerPlanTest(SimpleTestCase):
    def setUp(self):
        self.server = SimpleNamespace(id=1, pk=1, name="Local BG Test")
        self.desired_user = SimpleNamespace(pk=5, username="leorises")

    @patch("bg.pulse.reconciler._MurmurServerAdapter", _FakeAdapter)
    def test_build_plans_does_not_delete_superuser(self):
        _FakeAdapter.live_usernames = ["SuperUser", "leorises"]
        reconciler = MurmurRegistrationReconciler()

        with patch.object(reconciler, "_load_servers", return_value=[self.server]):
            with patch.object(reconciler, "_load_desired_users", return_value=[self.desired_user]):
                plans = reconciler.build_plans()

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].delete_count, 0)
        self.assertEqual(tuple(action.action for action in plans[0].actions), ())

    @patch("bg.pulse.reconciler._MurmurServerAdapter", _FakeAdapter)
    def test_build_plans_still_deletes_non_reserved_stale_user(self):
        _FakeAdapter.live_usernames = ["SuperUser", "leorises", "stale-user"]
        reconciler = MurmurRegistrationReconciler()

        with patch.object(reconciler, "_load_servers", return_value=[self.server]):
            with patch.object(reconciler, "_load_desired_users", return_value=[self.desired_user]):
                plans = reconciler.build_plans()

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].delete_count, 1)
        self.assertEqual(plans[0].actions[0].action, MurmurReconcileAction.DELETE)
        self.assertEqual(plans[0].actions[0].username, "stale-user")


class MurmurServerAdapterInvalidUserExceptionTest(SimpleTestCase):
    """The adapter must treat InvalidUserException as idempotent success:
    it means BG's ICE authenticator already claims the username, so the
    sqlite push Murmur would perform is unnecessary (ICE auth is authoritative).
    """

    def _make_adapter(self, *, existing_userid):
        server = SimpleNamespace(id=1, pk=1, name="Local BG Test")
        adapter = _MurmurServerAdapter(server)
        adapter._server_proxy = MagicMock()
        adapter._M = SimpleNamespace(
            InvalidUserException=IceOwnedInvalidUserException,
            UserInfo=SimpleNamespace(
                UserName="name", UserPassword="pw", UserHash="cert", UserComment="comment",
            ),
        )
        adapter._find_userid = MagicMock(return_value=existing_userid)
        return adapter

    def test_register_raises_invalid_user_is_treated_as_ice_owned(self):
        adapter = self._make_adapter(existing_userid=None)
        adapter._server_proxy.registerUser.side_effect = IceOwnedInvalidUserException()

        user = SimpleNamespace(username="beli_zmaj", display_name="", certhash="")
        result = adapter.create_or_update_user(user)

        self.assertIsNone(result)
        adapter._server_proxy.registerUser.assert_called_once()
        adapter._server_proxy.updateRegistration.assert_not_called()

    def test_update_raises_invalid_user_returns_existing_userid(self):
        adapter = self._make_adapter(existing_userid=42)
        adapter._server_proxy.updateRegistration.side_effect = IceOwnedInvalidUserException()

        user = SimpleNamespace(username="beli_zmaj", display_name="", certhash="")
        result = adapter.create_or_update_user(user)

        self.assertEqual(result, 42)
        adapter._server_proxy.updateRegistration.assert_called_once()
        adapter._server_proxy.registerUser.assert_not_called()
