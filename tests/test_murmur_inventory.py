from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils.timezone import now

from bg.murmur_inventory import MurmurInventoryError, get_server_inventory_snapshot, inventory_freshness_seconds
from bg.state.models import MumbleServer, MurmurServerInventorySnapshot


class MurmurInventoryFreshnessTest(TestCase):
    def test_default_freshness_is_ten_minutes(self):
        self.assertEqual(inventory_freshness_seconds(), 600)

    @override_settings(BG_MURMUR_INVENTORY_FRESHNESS_SECONDS=120)
    def test_configured_freshness_overrides_default(self):
        self.assertEqual(inventory_freshness_seconds(), 120)


class MurmurInventorySnapshotCacheTest(TestCase):
    def setUp(self):
        self.server = MumbleServer.objects.create(
            name='Inventory Server',
            address='inventory.example.com:64738',
            ice_host='127.0.0.1',
            ice_port=6502,
        )

    @patch('bg.murmur_inventory.fetch_server_inventory')
    def test_returns_cache_when_snapshot_is_fresh(self, mock_fetch):
        snapshot = MurmurServerInventorySnapshot.objects.create(
            server=self.server,
            payload={'summary': {'root_group_count': 1}},
            fetch_status='ok',
            fetched_at=now(),
        )

        envelope = get_server_inventory_snapshot(self.server)

        self.assertEqual(envelope.source, 'cache')
        self.assertEqual(envelope.snapshot.pk, snapshot.pk)
        mock_fetch.assert_not_called()

    @patch('bg.murmur_inventory.fetch_server_inventory')
    def test_refreshes_when_snapshot_is_stale(self, mock_fetch):
        MurmurServerInventorySnapshot.objects.create(
            server=self.server,
            payload={'summary': {'root_group_count': 1}},
            fetch_status='ok',
            fetched_at=now() - timedelta(hours=1),
        )
        mock_fetch.return_value = ({'summary': {'root_group_count': 2}}, 'tcp')

        envelope = get_server_inventory_snapshot(self.server)

        self.assertEqual(envelope.source, 'live')
        self.assertEqual(envelope.snapshot.payload['summary']['root_group_count'], 2)
        self.assertEqual(envelope.snapshot.protocol, 'tcp')

    @patch('bg.murmur_inventory.fetch_server_inventory')
    def test_returns_stale_cache_when_refresh_fails(self, mock_fetch):
        MurmurServerInventorySnapshot.objects.create(
            server=self.server,
            payload={'summary': {'root_group_count': 1}},
            fetch_status='ok',
            fetched_at=now() - timedelta(hours=1),
        )
        mock_fetch.side_effect = RuntimeError('ICE unavailable')

        envelope = get_server_inventory_snapshot(self.server)

        self.assertEqual(envelope.source, 'stale-cache')
        self.assertEqual(envelope.snapshot.fetch_status, 'error')
        self.assertEqual(envelope.snapshot.fetch_error, 'ICE unavailable')

    @patch('bg.murmur_inventory.fetch_server_inventory')
    def test_raises_inventory_error_when_live_fetch_fails_without_cache(self, mock_fetch):
        mock_fetch.side_effect = RuntimeError('ICE unavailable')

        with self.assertRaisesMessage(MurmurInventoryError, 'ICE unavailable'):
            get_server_inventory_snapshot(self.server)
