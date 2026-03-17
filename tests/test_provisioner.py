"""
Provisioner behavior tests.

Run with:
    cd /home/michael/prj/mumble-bg-ice-connections
    DJANGO_SETTINGS_MODULE=tests.test_settings /home/michael/.venv/mumble-bg/bin/python -m django test tests.test_provisioner -v 2
"""

from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from bg.provisioner import provision_registrations
from bg.state.models import AccessRule, MumbleServer, MumbleUser


class ProvisionerPasswordCreationTest(TestCase):
    """Provisioning should generate hash data for newly created rows."""

    def setUp(self):
        self.server = MumbleServer.objects.create(
            name='Test Server',
            address='127.0.0.1:64738',
            ice_host='127.0.0.1',
            ice_port=6502,
        )
        AccessRule.objects.create(entity_id=99000001, entity_type='alliance', deny=False)
        self.char_rows = [
            {
                'user_id': 1001,
                'character_id': 90000001,
                'character_name': 'Test Pilot',
                'corporation_id': 111,
                'corporation_name': 'Test Corp',
                'alliance_id': 99000001,
                'alliance_name': 'Alliance',
            },
        ]
        self.main_rows = {
            1001: {
                'user_id': 1001,
                'character_id': 90000001,
                'character_name': 'Test Pilot',
                'corporation_name': 'Test Corp',
                'alliance_name': 'Alliance',
                'is_main': True,
            },
        }

    def test_create_row_generates_password_hash(self):
        with patch('bg.provisioner._query_character_rows', return_value=self.char_rows):
            with patch('bg.provisioner._query_main_rows', return_value=self.main_rows):
                result = provision_registrations(None, server=self.server, dry_run=False)
        self.assertEqual(result.created, 1)
        user = MumbleUser.objects.get(user__id=1001, server=self.server)
        self.assertTrue(user.is_active)
        self.assertNotEqual(user.pwhash, '')
        self.assertNotEqual(user.pw_salt, '')
        self.assertTrue(user.kdf_iterations > 0)


class ProvisionerReactivationKeepsPasswordTest(TestCase):
    """Reactivating inactive rows should not mutate existing password data."""

    def setUp(self):
        self.server = MumbleServer.objects.create(
            name='Test Server',
            address='127.0.0.1:64738',
            ice_host='127.0.0.1',
            ice_port=6502,
        )
        AccessRule.objects.create(entity_id=99000001, entity_type='alliance', deny=False)
        user = User.objects.create(pk=2002, username='Another Pilot')
        MumbleUser.objects.create(
            user=user,
            server=self.server,
            evepilot_id=90000002,
            corporation_id=111,
            alliance_id=99000001,
            username='Another Pilot',
            display_name='Another Pilot',
            pwhash='legacy-hash',
            hashfn='legacy-hashfn',
            pw_salt='legacy-salt',
            kdf_iterations=2000,
            is_active=False,
        )
        self.char_rows = [
            {
                'user_id': 2002,
                'character_id': 90000002,
                'character_name': 'Another Pilot',
                'corporation_id': 111,
                'corporation_name': 'Test Corp',
                'alliance_id': 99000001,
                'alliance_name': 'Alliance',
            },
        ]
        self.main_rows = {
            2002: {
                'user_id': 2002,
                'character_id': 90000002,
                'character_name': 'Another Pilot',
                'corporation_name': 'Test Corp',
                'alliance_name': 'Alliance',
                'is_main': True,
            },
        }

    def test_reactivate_keeps_existing_password_hash(self):
        with patch('bg.provisioner._query_character_rows', return_value=self.char_rows):
            with patch('bg.provisioner._query_main_rows', return_value=self.main_rows):
                result = provision_registrations(None, server=self.server, dry_run=False)
        self.assertEqual(result.activated, 1)
        user = MumbleUser.objects.get(user__id=2002, server=self.server)
        self.assertTrue(user.is_active)
        self.assertEqual(user.pwhash, 'legacy-hash')
        self.assertEqual(user.pw_salt, 'legacy-salt')
        self.assertEqual(user.hashfn, 'legacy-hashfn')
        self.assertEqual(user.kdf_iterations, 2000)
