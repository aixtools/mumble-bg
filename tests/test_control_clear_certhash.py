import json

from django.contrib.auth.models import User
from django.test import Client, TestCase

from bg.passwords import build_murmur_password_record
from bg.state.models import (
    BG_AUDIT_ACTION_PILOT_CERTHASH_CLEAR,
    BgAudit,
    MumbleServer,
    MumbleUser,
)


class ClearCerthashControlTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='pilot7', password='pass', pk=7)
        self.server = MumbleServer.objects.create(
            name='Country 1',
            address='voice-a.example.com:64738',
            ice_host='127.0.0.1',
            ice_port=6502,
            is_active=True,
        )
        seed = build_murmur_password_record('pwd')
        self.mu = MumbleUser.objects.create(
            user=self.user,
            server=self.server,
            username='pilot7',
            display_name='Pilot Seven',
            pwhash=seed['pwhash'],
            hashfn=seed['hashfn'],
            pw_salt=seed['pw_salt'],
            kdf_iterations=seed['kdf_iterations'],
            certhash='AABBCC11',
            mumble_userid=42,
            is_active=True,
        )

    def _post(self, payload: dict, requested_by: str = 'tester'):
        envelope = {
            'request_id': 'cc-test',
            'requested_by': requested_by,
            'is_super': True,
            'payload': payload,
        }
        return self.client.post(
            '/v1/clear-certhash',
            data=json.dumps(envelope),
            content_type='application/json',
        )

    def test_clears_certhash_and_writes_audit(self):
        response = self._post({'pkid': 7, 'server_id': self.server.id})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['status'], 'completed')
        self.assertEqual(body['user_id'], 7)
        self.assertEqual(body['mumble_userid'], 42)
        self.assertEqual(body['username'], 'pilot7')
        self.assertTrue(body['had_certhash'])

        self.mu.refresh_from_db()
        self.assertEqual(self.mu.certhash, '')

        audits = BgAudit.objects.filter(action=BG_AUDIT_ACTION_PILOT_CERTHASH_CLEAR)
        self.assertEqual(audits.count(), 1)
        audit = audits.first()
        self.assertEqual(audit.user_id, 7)
        self.assertEqual(audit.server_name, 'Country 1')
        self.assertEqual(audit.requested_by, 'tester')
        self.assertEqual(audit.metadata['username'], 'pilot7')
        self.assertEqual(audit.metadata['mumble_userid'], 42)
        self.assertTrue(audit.metadata['had_certhash'])

    def test_idempotent_when_certhash_already_empty(self):
        self.mu.certhash = ''
        self.mu.save(update_fields=['certhash', 'updated_at'])

        response = self._post({'pkid': 7, 'server_id': self.server.id})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['status'], 'completed')
        self.assertFalse(body['had_certhash'])

        self.mu.refresh_from_db()
        self.assertEqual(self.mu.certhash, '')

        audits = BgAudit.objects.filter(action=BG_AUDIT_ACTION_PILOT_CERTHASH_CLEAR)
        self.assertEqual(audits.count(), 1)
        self.assertFalse(audits.first().metadata['had_certhash'])

    def test_404_when_registration_missing(self):
        response = self._post({'pkid': 999, 'server_id': self.server.id})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['status'], 'not_found')
        self.assertFalse(BgAudit.objects.filter(action=BG_AUDIT_ACTION_PILOT_CERTHASH_CLEAR).exists())

    def test_400_when_server_missing(self):
        response = self._post({'pkid': 7})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['status'], 'rejected')

    def test_400_when_requested_by_missing(self):
        response = self._post({'pkid': 7, 'server_id': self.server.id}, requested_by='')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['status'], 'rejected')
