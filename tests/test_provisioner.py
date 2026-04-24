from unittest.mock import patch

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
            display_name=f'[ALLY CORP] {character_name}' if display_name is None and pkid == 42 else str(display_name or ''),
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
        # Username contract: provisioner uses account_username verbatim.
        # Display name carries the bracketed corp/alliance ticker.
        self.assertEqual(mumble_user.username, 'pilot_login')
        self.assertEqual(mumble_user.display_name, '[ALLY CORP] Pilot One')
        self.assertEqual(mumble_user.evepilot_id, 9001)
        self.assertEqual(mumble_user.alliance_id, 9901)

    def test_provision_uses_account_username_verbatim(self):
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
        self.assertEqual(mumble_user.username, 'Leo Rises')
        self.assertEqual(User.objects.get(pk=42).username, 'Leo Rises')

    def test_provision_skips_when_account_username_is_empty(self):
        # Username contract requires a non-empty account_username; an empty one
        # signals that FG hasn't resolved the pilot's identity yet, so the
        # provisioner skips the row instead of synthesizing a username.
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

        self.assertEqual(result.created, 0)
        self.assertFalse(MumbleUser.objects.filter(user_id=42).exists())
        self.assertTrue(any('No valid display username' in err for err in (result.errors or [])))

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
        # Username tracks account_username from the cached snapshot, not the
        # bracketed display name; auth_user is renamed to match.
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

    def test_provision_rewrites_name_tags_to_ticker_tags(self):
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
            display_name='[Alliance One Corp One] Pilot One',
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

    def test_provision_skips_new_registration_when_tickers_are_unresolved(self):
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

        result = provision_registrations(dry_run=False)

        self.assertEqual(result.created, 0)
        self.assertTrue(any('cannot resolve ticker' in message for message in (result.errors or [])))
        self.assertFalse(MumbleUser.objects.filter(user_id=42, server=self.server).exists())

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


class ProvisionerPkidFilterTest(TestCase):
    """pkid_filter scopes the full-snapshot provisioner down to a single
    account so /v1/registrations/sync can provision-on-miss cheaply."""

    def setUp(self):
        self.server = MumbleServer.objects.create(
            name='Main',
            address='voice.example.com:64738',
            ice_host='127.0.0.1',
            ice_port=6502,
            is_active=True,
        )
        AccessRule.objects.create(entity_id=9901, entity_type='alliance', deny=False)
        for pkid, name in ((42, 'Pilot One'), (43, 'Pilot Two'), (44, 'Pilot Three')):
            account = PilotAccountCache.objects.create(
                pkid=pkid,
                account_username=f'pilot_{pkid}',
                display_name=f'[ALLY CORP] {name}',
                main_character_id=9000 + pkid,
                main_character_name=name,
            )
            PilotCharacterCache.objects.create(
                account=account,
                character_id=9000 + pkid,
                character_name=name,
                corporation_id=8801,
                corporation_name='Corp One',
                alliance_id=9901,
                alliance_name='Alliance One',
                is_main=True,
            )

    def test_pkid_filter_only_provisions_the_requested_account(self):
        result = provision_registrations(pkid_filter=43, dry_run=False)
        self.assertEqual(result.created, 1)
        self.assertTrue(MumbleUser.objects.filter(user_id=43, server=self.server).exists())
        self.assertFalse(MumbleUser.objects.filter(user_id=42, server=self.server).exists())
        self.assertFalse(MumbleUser.objects.filter(user_id=44, server=self.server).exists())

    def test_pkid_filter_noop_when_requested_account_is_ineligible(self):
        # pkid 999 is not in the snapshot → filter yields an empty set and
        # nothing is created for any pilot (no collateral damage).
        result = provision_registrations(pkid_filter=999, dry_run=False)
        self.assertEqual(result.created, 0)
        self.assertEqual(MumbleUser.objects.count(), 0)

    def test_pkid_filter_does_not_deactivate_other_accounts(self):
        # Pre-seed a row for another pilot who is currently denied by a corp
        # rule. Full provision would deactivate it; filtered provision must not.
        AccessRule.objects.create(entity_id=8801, entity_type='corporation', deny=True)
        auth_user = User.objects.create(pk=42, username='pilot_42')
        existing = MumbleUser.objects.create(
            user=auth_user,
            server=self.server,
            evepilot_id=9042,
            corporation_id=8801,
            alliance_id=9901,
            username='pilot_42',
            display_name='Pilot One',
            pwhash='x',
            is_active=True,
        )
        provision_registrations(pkid_filter=43, dry_run=False)
        existing.refresh_from_db()
        self.assertTrue(existing.is_active)


class RegistrationsSyncAutoProvisionTest(TestCase):
    """/v1/registrations/sync must provision-on-miss when the pilot is
    eligible per the cached snapshot but the periodic provisioner hasn't
    created their row yet — otherwise FG's activate flow 404s on every
    newly-eligible pilot."""

    def setUp(self):
        from django.test import Client

        self.client = Client(HTTP_X_FGBG_PSK='test-secret')
        self.server = MumbleServer.objects.create(
            name='Main',
            address='voice.example.com:64738',
            ice_host='127.0.0.1',
            ice_port=6502,
            is_active=True,
        )
        AccessRule.objects.create(entity_id=9901, entity_type='alliance', deny=False)
        account = PilotAccountCache.objects.create(
            pkid=999,
            account_username='neal_erata',
            display_name='[EVIL. SPY.] Neal Erata',
            main_character_id=94797689,
            main_character_name='Neal Erata',
        )
        PilotCharacterCache.objects.create(
            account=account,
            character_id=94797689,
            character_name='Neal Erata',
            corporation_id=8801,
            corporation_name='Spy Corp',
            alliance_id=9901,
            alliance_name='Insidious.',
            is_main=True,
        )

    def _sync_request(self):
        return {
            'request_id': 'req-activate',
            'requested_by': 'fg.views.activate',
            'payload': {
                'pkid': 999,
                'server_name': 'Main',
                'username': '[EVIL. SPY.] Neal Erata',
                'display_name': '[EVIL. SPY.] Neal Erata',
            },
        }

    @patch('bg.control._configured_control_secrets', return_value=([(None, 'test-secret')], 'env'))
    @patch('bg.control.sync_murmur_registration', return_value=4242)
    def test_missing_row_is_auto_provisioned_and_synced(self, _mock_sync, _mock_secrets):
        self.assertFalse(MumbleUser.objects.filter(user_id=999).exists())
        response = self.client.post(
            '/v1/registrations/sync',
            data=self._sync_request(),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['status'], 'completed')
        self.assertEqual(payload['user_id'], 999)
        row = MumbleUser.objects.get(user_id=999, server=self.server)
        self.assertTrue(row.is_active)
        self.assertEqual(row.mumble_userid, 4242)

    @patch('bg.control._configured_control_secrets', return_value=([(None, 'test-secret')], 'env'))
    @patch('bg.control.sync_murmur_registration', return_value=4242)
    def test_ineligible_pkid_still_returns_404(self, _mock_sync, _mock_secrets):
        body = self._sync_request()
        body['payload']['pkid'] = 12345  # not in snapshot
        response = self.client.post(
            '/v1/registrations/sync',
            data=body,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 404)
