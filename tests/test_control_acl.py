"""
Tests for the BG access-rules/sync control endpoint.

Run with:
    cd /home/michael/prj/mumble-bg
    DJANGO_SETTINGS_MODULE=tests.test_settings python -m django test tests.test_control_acl -v2
"""

import json

from django.test import TestCase, Client

from bg.state.models import AccessRule


def _post_acl_sync(client, rules, *, requested_by='test-user', is_super=True):
    """Post a full ACL sync request to the control endpoint."""
    payload = {
        'request_id': 'test-request-1',
        'requested_by': requested_by,
        'is_super': is_super,
        'payload': {
            'rules': rules,
        },
    }
    return client.post(
        '/v1/access-rules/sync',
        data=json.dumps(payload),
        content_type='application/json',
    )


class AccessRulesSyncBasicTest(TestCase):
    """Test basic ACL sync: create, update, delete."""

    def setUp(self):
        self.client = Client()

    def test_sync_creates_rules(self):
        rules = [
            {'entity_id': 99000001, 'entity_type': 'alliance', 'deny': False, 'note': 'Main alliance'},
            {'entity_id': 98000001, 'entity_type': 'corporation', 'deny': True, 'note': 'Bad corp'},
            {'entity_id': 90000001, 'entity_type': 'pilot', 'deny': False, 'note': 'Trusted pilot'},
        ]
        resp = _post_acl_sync(self.client, rules)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'completed')
        self.assertEqual(data['created'], 3)
        self.assertEqual(data['updated'], 0)
        self.assertEqual(data['deleted'], 0)
        self.assertEqual(data['total'], 3)
        self.assertEqual(AccessRule.objects.count(), 3)

    def test_sync_updates_existing(self):
        AccessRule.objects.create(
            entity_id=99000001, entity_type='alliance', deny=False, note='Old note',
        )
        rules = [
            {'entity_id': 99000001, 'entity_type': 'alliance', 'deny': True, 'note': 'Now denied'},
        ]
        resp = _post_acl_sync(self.client, rules)
        data = resp.json()
        self.assertEqual(data['created'], 0)
        self.assertEqual(data['updated'], 1)
        rule = AccessRule.objects.get(entity_id=99000001)
        self.assertTrue(rule.deny)
        self.assertEqual(rule.note, 'Now denied')

    def test_sync_deletes_missing_rules(self):
        AccessRule.objects.create(entity_id=99000001, entity_type='alliance', deny=False)
        AccessRule.objects.create(entity_id=99000002, entity_type='alliance', deny=False)
        AccessRule.objects.create(entity_id=98000001, entity_type='corporation', deny=True)
        rules = [
            {'entity_id': 99000001, 'entity_type': 'alliance', 'deny': False},
        ]
        resp = _post_acl_sync(self.client, rules)
        data = resp.json()
        self.assertEqual(data['created'], 0)
        self.assertEqual(data['updated'], 1)
        self.assertEqual(data['deleted'], 2)
        self.assertEqual(data['total'], 1)
        self.assertEqual(AccessRule.objects.count(), 1)
        self.assertTrue(AccessRule.objects.filter(entity_id=99000001).exists())

    def test_sync_empty_rules_clears_all(self):
        AccessRule.objects.create(entity_id=99000001, entity_type='alliance', deny=False)
        AccessRule.objects.create(entity_id=98000001, entity_type='corporation', deny=True)
        resp = _post_acl_sync(self.client, [])
        data = resp.json()
        self.assertEqual(data['deleted'], 2)
        self.assertEqual(data['total'], 0)
        self.assertEqual(AccessRule.objects.count(), 0)

    def test_synced_at_is_set(self):
        rules = [
            {'entity_id': 99000001, 'entity_type': 'alliance', 'deny': False},
        ]
        _post_acl_sync(self.client, rules)
        rule = AccessRule.objects.get(entity_id=99000001)
        self.assertIsNotNone(rule.synced_at)


class AccessRulesSyncFieldMappingTest(TestCase):
    """Test deny field storage end-to-end."""

    def setUp(self):
        self.client = Client()

    def test_block_false_means_allow(self):
        rules = [{'entity_id': 99000001, 'entity_type': 'alliance', 'deny': False}]
        _post_acl_sync(self.client, rules)
        rule = AccessRule.objects.get(entity_id=99000001)
        self.assertFalse(rule.deny)

    def test_block_true_means_deny(self):
        rules = [{'entity_id': 99000001, 'entity_type': 'alliance', 'deny': True}]
        _post_acl_sync(self.client, rules)
        rule = AccessRule.objects.get(entity_id=99000001)
        self.assertTrue(rule.deny)

    def test_block_defaults_to_false(self):
        rules = [{'entity_id': 99000001, 'entity_type': 'alliance'}]
        _post_acl_sync(self.client, rules)
        rule = AccessRule.objects.get(entity_id=99000001)
        self.assertFalse(rule.deny)

    def test_all_entity_types_accepted(self):
        rules = [
            {'entity_id': 99000001, 'entity_type': 'alliance', 'deny': False},
            {'entity_id': 98000001, 'entity_type': 'corporation', 'deny': True},
            {'entity_id': 90000001, 'entity_type': 'pilot', 'deny': False},
        ]
        resp = _post_acl_sync(self.client, rules)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            set(AccessRule.objects.values_list('entity_type', flat=True)),
            {'alliance', 'corporation', 'pilot'},
        )

    def test_note_and_created_by_stored(self):
        rules = [{
            'entity_id': 99000001,
            'entity_type': 'alliance',
            'deny': False,
            'note': 'Main alliance',
            'created_by': 'admin_user',
        }]
        _post_acl_sync(self.client, rules)
        rule = AccessRule.objects.get(entity_id=99000001)
        self.assertEqual(rule.note, 'Main alliance')
        self.assertEqual(rule.created_by, 'admin_user')


class AccessRulesSyncValidationTest(TestCase):
    """Test validation and error handling."""

    def setUp(self):
        self.client = Client()

    def test_missing_rules_field(self):
        payload = {
            'request_id': 'test',
            'requested_by': 'test-user',
            'is_super': True,
            'payload': {},
        }
        resp = self.client.post(
            '/v1/access-rules/sync',
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['status'], 'rejected')

    def test_missing_entity_id(self):
        rules = [{'entity_type': 'alliance', 'deny': False}]
        resp = _post_acl_sync(self.client, rules)
        self.assertEqual(resp.status_code, 400)

    def test_invalid_entity_type(self):
        rules = [{'entity_id': 99000001, 'entity_type': 'invalid'}]
        resp = _post_acl_sync(self.client, rules)
        self.assertEqual(resp.status_code, 400)

    def test_duplicate_entity_ids(self):
        rules = [
            {'entity_id': 99000001, 'entity_type': 'alliance', 'deny': False},
            {'entity_id': 99000001, 'entity_type': 'alliance', 'deny': True},
        ]
        resp = _post_acl_sync(self.client, rules)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('duplicated', resp.json()['message'])

    def test_block_must_be_bool(self):
        rules = [{'entity_id': 99000001, 'entity_type': 'alliance', 'deny': 'yes'}]
        resp = _post_acl_sync(self.client, rules)
        self.assertEqual(resp.status_code, 400)

    def test_requires_is_super(self):
        rules = [{'entity_id': 99000001, 'entity_type': 'alliance', 'deny': False}]
        resp = _post_acl_sync(self.client, rules, is_super=False)
        self.assertEqual(resp.status_code, 403)

    def test_requires_requested_by(self):
        payload = {
            'request_id': 'test',
            'is_super': True,
            'payload': {
                'rules': [{'entity_id': 99000001, 'entity_type': 'alliance', 'deny': False}],
            },
        }
        resp = self.client.post(
            '/v1/access-rules/sync',
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_get_method_not_allowed(self):
        resp = self.client.get('/v1/access-rules/sync')
        self.assertEqual(resp.status_code, 405)


class AccessRulesSyncIdempotencyTest(TestCase):
    """Test that repeated syncs with the same payload are idempotent."""

    def setUp(self):
        self.client = Client()

    def test_double_sync_same_rules(self):
        rules = [
            {'entity_id': 99000001, 'entity_type': 'alliance', 'deny': False, 'note': 'Test'},
        ]
        resp1 = _post_acl_sync(self.client, rules)
        resp2 = _post_acl_sync(self.client, rules)
        data1 = resp1.json()
        data2 = resp2.json()
        self.assertEqual(data1['created'], 1)
        self.assertEqual(data2['created'], 0)
        self.assertEqual(data2['updated'], 1)
        self.assertEqual(data2['deleted'], 0)
        self.assertEqual(AccessRule.objects.count(), 1)

    def test_full_replace_cycle(self):
        """Simulate a real FG lifecycle: add rules, change them, remove some."""
        rules_v1 = [
            {'entity_id': 99000001, 'entity_type': 'alliance', 'deny': False},
            {'entity_id': 99000002, 'entity_type': 'alliance', 'deny': False},
        ]
        _post_acl_sync(self.client, rules_v1)
        self.assertEqual(AccessRule.objects.count(), 2)

        # v2: remove one alliance, add a corp deny, flip the other alliance to deny
        rules_v2 = [
            {'entity_id': 99000001, 'entity_type': 'alliance', 'deny': True},
            {'entity_id': 98000001, 'entity_type': 'corporation', 'deny': True},
        ]
        resp = _post_acl_sync(self.client, rules_v2)
        data = resp.json()
        self.assertEqual(data['created'], 1)   # corp
        self.assertEqual(data['updated'], 1)   # alliance flip
        self.assertEqual(data['deleted'], 1)   # 99000002 removed
        self.assertEqual(AccessRule.objects.count(), 2)
        self.assertTrue(AccessRule.objects.get(entity_id=99000001).deny)

        # v3: clear everything
        resp = _post_acl_sync(self.client, [])
        self.assertEqual(resp.json()['deleted'], 2)
        self.assertEqual(AccessRule.objects.count(), 0)


class AccessRulesReadEndpointTest(TestCase):
    """Test the GET /v1/access-rules read endpoint."""

    def setUp(self):
        self.client = Client()

    def test_empty_list(self):
        resp = self.client.get('/v1/access-rules')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'completed')
        self.assertEqual(data['rules'], [])

    def test_returns_stored_rules(self):
        AccessRule.objects.create(entity_id=99000001, entity_type='alliance', deny=False, note='Test')
        AccessRule.objects.create(entity_id=98000001, entity_type='corporation', deny=True)
        resp = self.client.get('/v1/access-rules')
        data = resp.json()
        self.assertEqual(len(data['rules']), 2)
        rule_map = {r['entity_id']: r for r in data['rules']}
        self.assertFalse(rule_map[99000001]['deny'])
        self.assertTrue(rule_map[98000001]['deny'])
