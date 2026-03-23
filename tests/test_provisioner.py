from django.contrib.auth.models import User
from django.test import TestCase

from bg.passwords import build_murmur_password_record
from bg.provisioner import provision_registrations
from bg.state.models import (
    AccessRule,
    EveObject,
    MumbleServer,
    MumbleUser,
    PilotAccountCache,
    PilotCharacterCache,
)


class ProvisionerSnapshotTest(TestCase):
    def setUp(self):
        self.server = MumbleServer.objects.create(
            name='Main',
            address='voice.example.com:64738',
            ice_host='127.0.0.1',
            ice_port=6502,
            is_active=True,
        )

    def _seed_snapshot(
        self,
        *,
        pkid,
        character_id,
        character_name,
        account_username='',
        corporation_id=None,
        corporation_name='',
        alliance_id=None,
        alliance_name='',
        display_name=None,
    ):
        account = PilotAccountCache.objects.create(
            pkid=pkid,
            account_username=account_username,
            display_name='[ALLY CORP] Pilot One' if display_name is None and pkid == 42 else str(display_name or ''),
            main_character_id=character_id,
            main_character_name=character_name,
        )
        PilotCharacterCache.objects.create(
            account=account,
            character_id=character_id,
            character_name=character_name,
            corporation_id=corporation_id,
            corporation_name=corporation_name,
            alliance_id=alliance_id,
            alliance_name=alliance_name,
            is_main=True,
        )
        return account

    def test_provision_creates_registration_for_eligible_snapshot_account(self):
        AccessRule.objects.create(entity_id=9901, entity_type='alliance', deny=False)
        self._seed_snapshot(
            pkid=42,
            character_id=9001,
            character_name='Pilot One',
            account_username='pilot_login',
            alliance_id=9901,
            alliance_name='Alliance One',
            corporation_id=8801,
            corporation_name='Corp One',
        )

        result = provision_registrations(dry_run=False)

        self.assertEqual(result.created, 1)
        mumble_user = MumbleUser.objects.get(user_id=42, server=self.server)
        self.assertTrue(mumble_user.is_active)
        self.assertEqual(mumble_user.username, 'pilot_login')
        self.assertEqual(mumble_user.display_name, '[ALLY CORP] Pilot One')
        self.assertEqual(mumble_user.evepilot_id, 9001)
        self.assertEqual(mumble_user.alliance_id, 9901)

    def test_provision_normalizes_username_to_login_style(self):
        AccessRule.objects.create(entity_id=9901, entity_type='alliance', deny=False)
        self._seed_snapshot(
            pkid=42,
            character_id=9001,
            character_name='Leo Rises',
            account_username='Leo Rises',
            alliance_id=9901,
            alliance_name='Alliance One',
            corporation_id=8801,
            corporation_name='Corp One',
        )

        result = provision_registrations(dry_run=False)

        self.assertEqual(result.created, 1)
        mumble_user = MumbleUser.objects.get(user_id=42, server=self.server)
        self.assertEqual(mumble_user.username, 'leorises')
        self.assertEqual(User.objects.get(pk=42).username, 'leorises')

    def test_provision_does_not_fallback_to_character_name_for_username(self):
        AccessRule.objects.create(entity_id=9901, entity_type='alliance', deny=False)
        self._seed_snapshot(
            pkid=42,
            character_id=9001,
            character_name='Zosma Rises',
            account_username='',
            alliance_id=9901,
            alliance_name='Alliance One',
            corporation_id=8801,
            corporation_name='Corp One',
        )

        result = provision_registrations(dry_run=False)

        self.assertEqual(result.created, 1)
        mumble_user = MumbleUser.objects.get(user_id=42, server=self.server)
        self.assertEqual(mumble_user.username, 'pkid_42')
        self.assertEqual(User.objects.get(pk=42).username, 'pkid_42')

    def test_provision_creates_registration_for_each_active_server(self):
        secondary = MumbleServer.objects.create(
            name='Secondary',
            address='voice2.example.com:64738',
            ice_host='127.0.0.1',
            ice_port=6503,
            is_active=True,
        )
        AccessRule.objects.create(entity_id=9901, entity_type='alliance', deny=False)
        self._seed_snapshot(
            pkid=42,
            character_id=9001,
            character_name='Pilot One',
            account_username='pilot_login',
            alliance_id=9901,
            alliance_name='Alliance One',
            corporation_id=8801,
            corporation_name='Corp One',
        )

        result = provision_registrations(dry_run=False)

        self.assertEqual(result.created, 2)
        rows = list(MumbleUser.objects.filter(user_id=42).order_by('server_id'))
        self.assertEqual(len(rows), 2)
        self.assertEqual({rows[0].server_id, rows[1].server_id}, {self.server.id, secondary.id})
        self.assertTrue(all(row.is_active for row in rows))

    def test_provision_deactivates_blocked_registration_from_snapshot(self):
        AccessRule.objects.create(entity_id=9901, entity_type='alliance', deny=False)
        AccessRule.objects.create(entity_id=8801, entity_type='corporation', deny=True)
        self._seed_snapshot(
            pkid=42,
            character_id=9001,
            character_name='Pilot One',
            account_username='pilot_login',
            alliance_id=9901,
            alliance_name='Alliance One',
            corporation_id=8801,
            corporation_name='Corp One',
        )

        user = User.objects.create(pk=42, username='pilot_login')
        password_record = build_murmur_password_record('temporary-pass')
        MumbleUser.objects.create(
            user=user,
            server=self.server,
            evepilot_id=9001,
            corporation_id=8801,
            alliance_id=9901,
            username='pilot_login',
            display_name='Pilot One',
            pwhash=password_record['pwhash'],
            hashfn=password_record['hashfn'],
            pw_salt=password_record['pw_salt'],
            kdf_iterations=password_record['kdf_iterations'],
            is_active=True,
        )

        result = provision_registrations(dry_run=False)

        self.assertEqual(result.deactivated, 1)
        self.assertFalse(MumbleUser.objects.get(user_id=42, server=self.server).is_active)

    def test_provision_updates_existing_display_name_from_snapshot(self):
        AccessRule.objects.create(entity_id=9901, entity_type='alliance', deny=False)
        self._seed_snapshot(
            pkid=42,
            character_id=9001,
            character_name='Pilot One',
            account_username='pilot_login',
            alliance_id=9901,
            alliance_name='Alliance One',
            corporation_id=8801,
            corporation_name='Corp One',
        )

        user = User.objects.create(pk=42, username='old_login')
        password_record = build_murmur_password_record('temporary-pass')
        MumbleUser.objects.create(
            user=user,
            server=self.server,
            evepilot_id=9001,
            corporation_id=8801,
            alliance_id=9901,
            username='Pilot One',
            display_name='Pilot One',
            pwhash=password_record['pwhash'],
            hashfn=password_record['hashfn'],
            pw_salt=password_record['pw_salt'],
            kdf_iterations=password_record['kdf_iterations'],
            is_active=True,
        )

        result = provision_registrations(dry_run=False)

        self.assertEqual(result.unchanged, 1)
        updated = MumbleUser.objects.get(user_id=42, server=self.server)
        self.assertEqual(updated.display_name, '[ALLY CORP] Pilot One')
        self.assertEqual(updated.username, 'pilot_login')
        self.assertEqual(User.objects.get(pk=42).username, 'pilot_login')

    def test_provision_sets_admin_from_pilot_acl_admin(self):
        AccessRule.objects.create(entity_id=9901, entity_type='alliance', deny=False)
        AccessRule.objects.create(entity_id=9001, entity_type='pilot', deny=False, acl_admin=True)
        self._seed_snapshot(
            pkid=42,
            character_id=9001,
            character_name='Pilot One',
            account_username='pilot_login',
            alliance_id=9901,
            alliance_name='Alliance One',
            corporation_id=8801,
            corporation_name='Corp One',
        )

        provision_registrations(dry_run=False)

        mumble_user = MumbleUser.objects.get(user_id=42, server=self.server)
        self.assertTrue(mumble_user.is_active)
        self.assertTrue(mumble_user.is_mumble_admin)

    def test_provision_resolves_placeholder_display_name_from_eveobject_cache(self):
        AccessRule.objects.create(entity_id=9901, entity_type='alliance', deny=False)
        self._seed_snapshot(
            pkid=42,
            character_id=9001,
            character_name='Pilot One',
            account_username='pilot_login',
            alliance_id=9901,
            alliance_name='Alliance One',
            corporation_id=8801,
            corporation_name='Corp One',
            display_name='[???? ????] Pilot One',
        )
        EveObject.objects.create(
            entity_id=9901,
            type='alliance',
            category='alliance',
            name='Alliance One',
            ticker='ALLY',
        )
        EveObject.objects.create(
            entity_id=8801,
            type='corporation',
            category='corporation',
            name='Corp One',
            ticker='CORP',
        )

        result = provision_registrations(dry_run=False)

        self.assertEqual(result.created, 1)
        mumble_user = MumbleUser.objects.get(user_id=42, server=self.server)
        self.assertEqual(mumble_user.display_name, '[ALLY CORP] Pilot One')
        self.assertEqual(PilotAccountCache.objects.get(pkid=42).display_name, '[ALLY CORP] Pilot One')

    def test_provision_clears_admin_when_corp_or_alliance_is_denied(self):
        AccessRule.objects.create(entity_id=9901, entity_type='alliance', deny=False)
        AccessRule.objects.create(entity_id=9001, entity_type='pilot', deny=False, acl_admin=True)
        AccessRule.objects.create(entity_id=8801, entity_type='corporation', deny=True)
        self._seed_snapshot(
            pkid=42,
            character_id=9001,
            character_name='Pilot One',
            account_username='pilot_login',
            alliance_id=9901,
            alliance_name='Alliance One',
            corporation_id=8801,
            corporation_name='Corp One',
        )

        user = User.objects.create(pk=42, username='pilot_login')
        password_record = build_murmur_password_record('temporary-pass')
        MumbleUser.objects.create(
            user=user,
            server=self.server,
            evepilot_id=9001,
            corporation_id=8801,
            alliance_id=9901,
            username='pilot_login',
            display_name='Pilot One',
            pwhash=password_record['pwhash'],
            hashfn=password_record['hashfn'],
            pw_salt=password_record['pw_salt'],
            kdf_iterations=password_record['kdf_iterations'],
            is_mumble_admin=True,
            is_active=True,
        )

        provision_registrations(dry_run=False)

        updated = MumbleUser.objects.get(user_id=42, server=self.server)
        self.assertTrue(updated.is_active)
        self.assertFalse(updated.is_mumble_admin)
