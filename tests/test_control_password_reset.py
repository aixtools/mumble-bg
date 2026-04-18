import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import Client, TestCase

from bg.passwords import build_murmur_password_record
from bg.pilot import registrations as registrations_module
from bg.pilot.registrations import MurmurSyncError, sync_murmur_registration
from bg.state.models import MumbleServer, MumbleUser
from tests.conftest import IceOwnedInvalidUserException


class PasswordResetControlTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='pilot5', password='pass', pk=5)
        self.server_a = MumbleServer.objects.create(
            name='Country 1',
            address='voice-a.example.com:64738',
            ice_host='127.0.0.1',
            ice_port=6502,
            is_active=True,
        )
        self.server_b = MumbleServer.objects.create(
            name='Nation 2',
            address='voice-b.example.com:64738',
            ice_host='127.0.0.1',
            ice_port=6503,
            is_active=True,
        )
        seed = build_murmur_password_record('OldPass123!')
        self.old_hash = seed['pwhash']
        self.user_a = MumbleUser.objects.create(
            user=self.user,
            server=self.server_a,
            username='pilot5',
            display_name='Pilot Five',
            pwhash=seed['pwhash'],
            hashfn=seed['hashfn'],
            pw_salt=seed['pw_salt'],
            kdf_iterations=seed['kdf_iterations'],
            is_active=True,
        )
        self.user_b = MumbleUser.objects.create(
            user=self.user,
            server=self.server_b,
            username='pilot5',
            display_name='Pilot Five',
            pwhash=seed['pwhash'],
            hashfn=seed['hashfn'],
            pw_salt=seed['pw_salt'],
            kdf_iterations=seed['kdf_iterations'],
            is_active=True,
        )

    def _post(self, payload: dict):
        envelope = {
            'request_id': 'pw-reset-test',
            'requested_by': 'tester',
            'is_super': True,
            'payload': payload,
        }
        return self.client.post(
            '/v1/password-reset',
            data=json.dumps(envelope),
            content_type='application/json',
        )

    @patch('bg.control.sync_murmur_registration')
    def test_password_reset_updates_all_active_servers(self, sync_mock):
        seen_passwords = []

        def _sync_side_effect(mumble_user, password=None):
            seen_passwords.append((mumble_user.server.name, password))
            return 100 + mumble_user.server_id

        sync_mock.side_effect = _sync_side_effect

        response = self._post({'pkid': 5})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'completed')
        self.assertEqual(payload['server_count'], 2)
        self.assertEqual(payload['synced_server_count'], 2)
        self.assertEqual(payload['ice_down_servers'], [])

        self.assertEqual(sync_mock.call_count, 2)
        self.assertEqual(len({item[1] for item in seen_passwords}), 1)

        self.user_a.refresh_from_db()
        self.user_b.refresh_from_db()
        self.assertTrue(self.user_a.pwhash)
        self.assertTrue(self.user_b.pwhash)
        self.assertNotEqual(self.user_a.pwhash, self.old_hash)
        self.assertNotEqual(self.user_b.pwhash, self.old_hash)
        self.assertEqual(self.user_a.mumble_userid, 100 + self.server_a.id)
        self.assertEqual(self.user_b.mumble_userid, 100 + self.server_b.id)

    @patch('bg.control.sync_murmur_registration')
    def test_password_reset_reports_ice_down_but_still_updates_bg(self, sync_mock):
        def _sync_side_effect(mumble_user, password=None):
            if mumble_user.server_id == self.server_b.id:
                raise MurmurSyncError(
                    f'Failed to connect to ICE on {mumble_user.server.ice_host}:{mumble_user.server.ice_port}'
                )
            return 777

        sync_mock.side_effect = _sync_side_effect

        response = self._post({'pkid': 5})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'partial')
        self.assertIn('ICE servers are down', payload['message'])
        self.assertEqual(payload['server_count'], 2)
        self.assertEqual(payload['synced_server_count'], 1)
        self.assertEqual(payload['ice_down_servers'], ['Nation 2'])

        self.user_a.refresh_from_db()
        self.user_b.refresh_from_db()
        self.assertTrue(self.user_a.pwhash)
        self.assertTrue(self.user_b.pwhash)
        self.assertEqual(self.user_a.mumble_userid, 777)
        self.assertIsNone(self.user_b.mumble_userid)


class SyncMurmurRegistrationInvalidUserTest(TestCase):
    """When Murmur throws InvalidUserException during register/update, it
    means BG's ICE authenticator already claims the username; the sqlite
    push Murmur is attempting is unnecessary. sync_murmur_registration
    must treat this as idempotent success so password resets don't fail.
    """

    def setUp(self):
        user = User.objects.create_user(username='pilotx', password='pw', pk=99)
        server = MumbleServer.objects.create(
            name='TestSrv', address='x:64738', ice_host='127.0.0.1', ice_port=6502, is_active=True,
        )
        seed = build_murmur_password_record('Pass123!')
        self.mumble_user = MumbleUser.objects.create(
            user=user, server=server, username='pilotx', display_name='PilotX',
            pwhash=seed['pwhash'], hashfn=seed['hashfn'],
            pw_salt=seed['pw_salt'], kdf_iterations=seed['kdf_iterations'],
            is_active=True, mumble_userid=42,
        )

    def _mock_ice(self, *, find_existing_userid, raising_method):
        M = SimpleNamespace(
            InvalidUserException=IceOwnedInvalidUserException,
            UserInfo=SimpleNamespace(
                UserName='name', UserPassword='pw', UserHash='cert', UserComment='comment',
            ),
        )
        server_proxy = MagicMock()
        getattr(server_proxy, raising_method).side_effect = IceOwnedInvalidUserException()
        server_proxy.getRegistration.return_value = {}
        communicator = MagicMock()
        return [
            patch.object(registrations_module, '_open_target_server',
                         return_value=(communicator, M, server_proxy)),
            patch.object(registrations_module, '_find_existing_userid',
                         return_value=find_existing_userid),
            patch.object(registrations_module, '_build_registration_info', return_value={}),
        ]

    def test_register_invalid_user_is_idempotent_success(self):
        patchers = self._mock_ice(find_existing_userid=None, raising_method='registerUser')
        for p in patchers:
            p.start()
        try:
            result = sync_murmur_registration(self.mumble_user, password='NewPass!')
        finally:
            for p in patchers:
                p.stop()
        self.assertIsNone(result)

    def test_update_invalid_user_returns_existing_userid(self):
        patchers = self._mock_ice(find_existing_userid=42, raising_method='updateRegistration')
        for p in patchers:
            p.start()
        try:
            result = sync_murmur_registration(self.mumble_user, password='NewPass!')
        finally:
            for p in patchers:
                p.stop()
        self.assertEqual(result, 42)

    def test_update_invalid_user_return_details(self):
        patchers = self._mock_ice(find_existing_userid=42, raising_method='updateRegistration')
        for p in patchers:
            p.start()
        try:
            details = sync_murmur_registration(
                self.mumble_user, password='NewPass!', return_details=True,
            )
        finally:
            for p in patchers:
                p.stop()
        self.assertEqual(details, {'murmur_userid': 42, 'created': False, 'reenabled': False})
