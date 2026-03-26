from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from bg.pulse.reconciler import MurmurReconcileAction, MurmurRegistrationReconciler


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
