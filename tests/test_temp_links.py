from django.contrib.auth.models import User
from django.test import Client, TestCase
from unittest.mock import patch

from bg.state.models import MumbleServer, MumbleUser


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
        self.assertEqual(payload['display_name'], 'Guest User')
        row = MumbleUser.objects.get(server=self.server, username=payload['username'])
        self.assertTrue(row.is_temporary)
        self.assertEqual(row.display_name, 'Guest User')
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
