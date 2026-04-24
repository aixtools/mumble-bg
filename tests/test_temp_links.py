from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import Client, TestCase

from bg.pilot import registrations as registrations_module
from bg.pilot.registrations import (
    MurmurSyncError,
    _find_existing_userid,
    sync_murmur_registration,
)
from bg.state.models import MumbleServer, MumbleUser
from tests.conftest import IceOwnedInvalidUserException


class TempLinksRedeemEndpointTest(TestCase):
    def setUp(self):
        self.client = Client(HTTP_X_FGBG_PSK='test-secret')
        self.server = MumbleServer.objects.create(
            name='Finland',
            address='voice.example.com:64738',
            ice_host='127.0.0.1',
            ice_port=6502,
        )

    @patch('bg.control._configured_control_secrets', return_value=([(None, 'test-secret')], 'env'))
    @patch('bg.control.sync_murmur_registration', return_value=321)
    def test_redeem_creates_temporary_guest_registration(self, _mock_sync, _mock_secrets):
        response = self.client.post(
            '/v1/temp-links/redeem',
            data={
                'request_id': 'req-1',
                'requested_by': 'temp-link:deadbeef',
                'payload': {
                    'server_key': self.server.server_key,
                    'display_name': 'Guest User',
                    'groups': 'Guest',
                    'expires_at': '2099-01-01T00:00:00+00:00',
                    'link_token': 'deadbeef',
                },
            },
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'completed')
        self.assertEqual(payload['server_name'], 'Finland')
        self.assertTrue(payload['username'].startswith('temp_'))
        self.assertEqual(payload['display_name'], '[TEMP] Guest User')
        row = MumbleUser.objects.get(server=self.server, username=payload['username'])
        self.assertTrue(row.is_temporary)
        self.assertEqual(row.display_name, '[TEMP] Guest User')
        self.assertEqual(row.groups, 'Guest')
        self.assertEqual(row.mumble_userid, 321)
        self.assertEqual(row.temporary_link_token, 'deadbeef')
        self.assertTrue(User.objects.filter(pk=row.user_id, username=row.username).exists())

    @patch('bg.control._configured_control_secrets', return_value=([(None, 'test-secret')], 'env'))
    @patch('bg.control.unregister_murmur_registration', return_value=True)
    def test_revoke_disables_temporary_rows_for_link(self, _mock_unregister, _mock_secrets):
        auth_user = User.objects.create_user('temp_user')
        row = MumbleUser.objects.create(
            user=auth_user,
            server=self.server,
            username='temp_user',
            display_name='Guest User',
            pwhash='x',
            hashfn='murmur-pbkdf2-sha384',
            pw_salt='salt',
            groups='Guest',
            is_temporary=True,
            temporary_link_token='deadbeef',
            is_active=True,
        )
        response = self.client.post(
            '/v1/temp-links/revoke',
            data={
                'request_id': 'req-2',
                'requested_by': 'admin',
                'payload': {'link_token': 'deadbeef'},
            },
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        row.refresh_from_db()
        self.assertFalse(row.is_active)


class FindExistingUseridAliasGuardTest(TestCase):
    """`_find_existing_userid` must ignore `[TEMP] …` aliases so that a new
    temp redemption can't alias onto a lingering expired guest registration."""

    def test_temp_prefixed_alias_is_ignored(self):
        proxy = MagicMock()
        proxy.getRegisteredUsers.return_value = {42: '[TEMP] Sil Ver'}
        result = _find_existing_userid(
            proxy,
            username='temp_sil_ver_deadbeef_abc123',
            aliases=['[TEMP] Sil Ver'],
        )
        self.assertIsNone(result)

    def test_legit_alias_still_matches(self):
        proxy = MagicMock()
        proxy.getRegisteredUsers.return_value = {7: 'SilVerAlias'}
        result = _find_existing_userid(
            proxy,
            username='primary',
            aliases=['SilVerAlias'],
        )
        self.assertEqual(result, 7)

    def test_case_insensitive_prefix_is_ignored(self):
        proxy = MagicMock()
        proxy.getRegisteredUsers.return_value = {99: '[TEMP] Foo'}
        result = _find_existing_userid(
            proxy,
            username='temp_foo_xxxx_yyy',
            aliases=['[temp] Foo', '[TEMP] FOO'],
        )
        self.assertIsNone(result)


class SyncMurmurRegistrationForTemporaryTest(TestCase):
    """`sync_murmur_registration(for_temporary=True)` must never overwrite an
    existing Murmur registration — it should create a fresh one or raise.
    """

    def setUp(self):
        user = User.objects.create_user(username='pilot_temp', password='pw')
        self.server = MumbleServer.objects.create(
            name='Srv', address='s:64738', ice_host='127.0.0.1', ice_port=6502, is_active=True,
        )
        self.mumble_user = MumbleUser.objects.create(
            user=user,
            server=self.server,
            username='temp_foo_deadbeef_abc123',
            display_name='[TEMP] Sil Ver',
            pwhash='h',
            is_temporary=True,
        )

    def _patch_ice(self, *, registered_users, register_user_return=888):
        M = SimpleNamespace(
            InvalidUserException=IceOwnedInvalidUserException,
            UserInfo=SimpleNamespace(
                UserName='name', UserPassword='pw', UserHash='cert', UserComment='comment',
            ),
        )
        server_proxy = MagicMock()
        server_proxy.getRegisteredUsers.return_value = registered_users
        server_proxy.registerUser.return_value = register_user_return
        communicator = MagicMock()
        return [
            patch.object(
                registrations_module,
                '_open_target_server',
                return_value=(communicator, M, server_proxy),
            ),
            patch.object(
                registrations_module, '_build_registration_info', return_value={},
            ),
        ], server_proxy

    def test_for_temporary_ignores_display_name_collision_and_registers_fresh(self):
        # Simulate a lingering Murmur registration whose UserName exactly
        # matches the new temp's display_name alias. Without for_temporary=True
        # this would trigger updateRegistration on userid 42 and corrupt the
        # existing pilot's record. With for_temporary=True, the alias must be
        # skipped and registerUser called instead.
        patchers, server_proxy = self._patch_ice(
            registered_users={42: '[TEMP] Sil Ver'},
        )
        for p in patchers:
            p.start()
        try:
            result = sync_murmur_registration(
                self.mumble_user, password='pw', for_temporary=True,
            )
        finally:
            for p in patchers:
                p.stop()
        self.assertEqual(result, 888)
        server_proxy.registerUser.assert_called_once()
        server_proxy.updateRegistration.assert_not_called()

    def test_for_temporary_raises_on_exact_username_collision(self):
        # Direct username collision with an existing registration is
        # essentially impossible given the random-hex suffix in temp usernames,
        # but if it ever happens we refuse to overwrite.
        patchers, _ = self._patch_ice(
            registered_users={77: 'temp_foo_deadbeef_abc123'},
        )
        for p in patchers:
            p.start()
        try:
            with self.assertRaises(MurmurSyncError):
                sync_murmur_registration(
                    self.mumble_user, password='pw', for_temporary=True,
                )
        finally:
            for p in patchers:
                p.stop()

    def test_non_temporary_still_aliases_on_display_name(self):
        # Regression guard: the non-temporary default path must keep its
        # alias-matching behavior so normal pilots can reconnect after a
        # username change.
        non_temp_user = User.objects.create_user(username='pilot_real', password='pw')
        row = MumbleUser.objects.create(
            user=non_temp_user,
            server=self.server,
            username='newname',
            display_name='OldName',
            pwhash='h',
            is_temporary=False,
        )
        patchers, server_proxy = self._patch_ice(
            registered_users={55: 'OldName'},
        )
        for p in patchers:
            p.start()
        try:
            result = sync_murmur_registration(row, password='pw')
        finally:
            for p in patchers:
                p.stop()
        self.assertEqual(result, 55)
        server_proxy.updateRegistration.assert_called_once()
        server_proxy.registerUser.assert_not_called()


class TempLinkRedeemRetryAndErrorHandlingTest(TestCase):
    """`temp_links_redeem` must survive a transient IntegrityError on the
    auth_user save (e.g. PG sequence drift) via the savepointed retry loop,
    and must return a clean CONFLICT response if the whole redemption
    collapses with an IntegrityError."""

    def setUp(self):
        self.client = Client(HTTP_X_FGBG_PSK='test-secret')
        self.server = MumbleServer.objects.create(
            name='Finland',
            address='voice.example.com:64738',
            ice_host='127.0.0.1',
            ice_port=6502,
        )

    @staticmethod
    def _redeem_payload():
        return {
            'request_id': 'req-retry',
            'requested_by': 'temp-link:deadbeef',
            'payload': {
                'server_key': None,  # filled by caller
                'display_name': 'Guest User',
                'groups': 'Guest',
                'expires_at': '2099-01-01T00:00:00+00:00',
                'link_token': 'deadbeef',
            },
        }

    @patch('bg.control._configured_control_secrets', return_value=([(None, 'test-secret')], 'env'))
    @patch('bg.control.sync_murmur_registration', return_value=321)
    def test_retry_loop_recovers_from_transient_save_integrity_error(
        self, _mock_sync, _mock_secrets,
    ):
        real_save = User.save
        calls = {'n': 0}

        def flaky_save(self, *args, **kwargs):
            calls['n'] += 1
            if calls['n'] == 1:
                raise IntegrityError('simulated sequence collision')
            return real_save(self, *args, **kwargs)

        body = self._redeem_payload()
        body['payload']['server_key'] = self.server.server_key

        with patch.object(User, 'save', flaky_save):
            response = self.client.post(
                '/v1/temp-links/redeem',
                data=body,
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertGreaterEqual(calls['n'], 2)
        self.assertTrue(MumbleUser.objects.filter(is_temporary=True).exists())

    @patch('bg.control._configured_control_secrets', return_value=([(None, 'test-secret')], 'env'))
    @patch('bg.control.sync_murmur_registration', return_value=321)
    def test_integrity_error_returns_conflict_not_500(
        self, _mock_sync, _mock_secrets,
    ):
        body = self._redeem_payload()
        body['payload']['server_key'] = self.server.server_key

        original_save = MumbleUser.save

        def poisoned_save(self, *args, **kwargs):
            if kwargs.get('update_fields') == ['mumble_userid', 'is_active', 'updated_at']:
                raise IntegrityError('simulated partial-unique-index violation')
            return original_save(self, *args, **kwargs)

        with patch.object(MumbleUser, 'save', poisoned_save):
            response = self.client.post(
                '/v1/temp-links/redeem',
                data=body,
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 409)
        payload = response.json()
        self.assertEqual(payload['status'], 'failed')
        self.assertIn('Temporary registration could not be committed', payload['message'])
