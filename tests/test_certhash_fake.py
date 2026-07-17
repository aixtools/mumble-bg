"""Derived fake certhash for ShitSpeak's Randomized privacy mode.

Covers the shared cross-language vector (must equal
``shitspeak_runtime::privacy::randomized_certificate_hash_hex``) and that the
ShitSpeak authenticate endpoint persists the presented cert hash on the row.
"""

import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase

from bg import shitspeak
from bg.authd.service import derive_fake_certhash
from bg.state.models import MumbleServer, MumbleUser

# Shared vector — keep byte-for-byte identical to the Rust privacy test.
_REAL = '00112233445566778899aabbccddeeff00112233'
_FAKE = '1879fca7aa5b06b4d1792cf0ef21d753fd5111e5'
_OTHER = 'ffeeddccbbaa99887766554433221100ffeeddcc'
TOKEN = 'test-shitspeak-token'


class DeriveFakeCerthashTest(TestCase):
    def test_matches_shared_cross_language_vector(self):
        self.assertEqual(derive_fake_certhash(_REAL), _FAKE)

    def test_deterministic_and_distinct_per_cert(self):
        self.assertEqual(derive_fake_certhash(_REAL), derive_fake_certhash(_REAL))
        self.assertNotEqual(derive_fake_certhash(_REAL), derive_fake_certhash(_OTHER))
        self.assertNotEqual(derive_fake_certhash(_REAL), _REAL)

    def test_input_is_case_insensitive(self):
        self.assertEqual(derive_fake_certhash(_REAL.upper()), _FAKE)

    def test_rejects_non_hash_input(self):
        for bad in ('', None, 'not-hex', '00ff', _REAL + 'ff'):
            self.assertEqual(derive_fake_certhash(bad), '')


class ShitSpeakAuthPersistsCerthashTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='pilot1', password='x')
        self.server = MumbleServer.objects.create(
            name='mumble-beta',
            address='voice-beta.example.com:64738',
            ice_host='',
            ice_port=6502,
            driver=MumbleServer.DRIVER_SHITSPEAK,
            auth_token=TOKEN,
            is_active=True,
        )
        self.registration = MumbleUser.objects.create(
            user=self.user,
            server=self.server,
            username='pilot1',
            display_name='Pilot One',
            is_active=True,
        )

    def _post(self, payload):
        return self.client.post(
            '/shitspeak/authenticate',
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {TOKEN}',
        )

    def test_successful_auth_persists_presented_certhash(self):
        accept = (self.registration.pk, 99, 'Pilot One', ['member'], 5, 'cert')
        with patch.object(shitspeak, 'authd_authenticate', return_value=accept), \
                patch.object(shitspeak, 'update_connection_info') as persist:
            resp = self._post({
                'username': 'pilot1',
                'server_id': self.server.pk,
                'auxiliary_data': {'certificate_hash_hex': _REAL},
            })
        self.assertEqual(resp.status_code, 200)
        # The endpoint delegates persistence to update_connection_info, which
        # writes certhash + derives certhash_fake.
        persist.assert_called_once_with(self.registration.pk, _REAL)

    def test_auth_without_certhash_skips_persistence(self):
        accept = (self.registration.pk, 99, 'Pilot One', ['member'], 5, 'password')
        with patch.object(shitspeak, 'authd_authenticate', return_value=accept), \
                patch.object(shitspeak, 'update_connection_info') as persist:
            resp = self._post({
                'username': 'pilot1',
                'password': 'pw',
                'server_id': self.server.pk,
            })
        self.assertEqual(resp.status_code, 200)
        persist.assert_not_called()
