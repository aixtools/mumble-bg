from unittest.mock import patch

from django.test import Client, TestCase

from bg.control import _Unauthorized
from bg.state.models import MumbleServer, MurmurServerInventorySnapshot


class ServerInventoryEndpointTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.server = MumbleServer.objects.create(
            name='Inventory Server',
            address='inventory.example.com:64738',
            ice_host='127.0.0.1',
            ice_port=6502,
        )

    @patch('bg.control._require_control_auth', side_effect=_Unauthorized('Missing control authentication secret'))
    def test_requires_control_auth(self, _mock_auth):
        response = self.client.get(f'/v1/servers/{self.server.server_key}/inventory')
        self.assertEqual(response.status_code, 401)

    @patch('bg.control.warm_other_server_inventories_async', return_value=True)
    @patch('bg.control.get_server_inventory_snapshot')
    @patch('bg.control._require_control_auth', return_value=('env', None))
    def test_returns_cached_inventory_payload(self, _mock_auth, mock_get_snapshot, _mock_warm):
        snapshot = MurmurServerInventorySnapshot(
            server=self.server,
            payload={'root_groups': [{'name': 'ops'}]},
            fetch_status='ok',
            protocol='ssl',
        )
        snapshot.fetched_at = None
        mock_get_snapshot.return_value = type(
            'Envelope',
            (),
            {
                'snapshot': snapshot,
                'source': 'cache',
                'freshness_seconds': 600,
                'is_real_time': True,
            },
        )()

        response = self.client.get(f'/v1/servers/{self.server.server_key}/inventory')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'completed')
        self.assertEqual(payload['server_id'], self.server.pk)
        self.assertEqual(payload['server_key'], self.server.server_key)
        self.assertEqual(payload['inventory']['root_groups'][0]['name'], 'ops')
        self.assertEqual(payload['source'], 'cache')
        self.assertTrue(payload['cache_warm_started'])

    @patch('bg.control.warm_other_server_inventories_async', return_value=False)
    @patch('bg.control.get_server_inventory_snapshot')
    @patch('bg.control._require_control_auth', return_value=('env', None))
    def test_refresh_flag_forces_refresh(self, _mock_auth, mock_get_snapshot, _mock_warm):
        snapshot = MurmurServerInventorySnapshot(
            server=self.server,
            payload={'root_groups': []},
            fetch_status='ok',
            protocol='tcp',
        )
        snapshot.fetched_at = None
        mock_get_snapshot.return_value = type(
            'Envelope',
            (),
            {
                'snapshot': snapshot,
                'source': 'live',
                'freshness_seconds': 600,
                'is_real_time': True,
            },
        )()

        response = self.client.get(f'/v1/servers/{self.server.server_key}/inventory?refresh=1')

        self.assertEqual(response.status_code, 200)
        mock_get_snapshot.assert_called_once_with(self.server, force_refresh=True)

    def test_servers_payload_includes_stable_server_key(self):
        response = self.client.get('/v1/servers')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['servers'][0]['id'], self.server.pk)
        self.assertEqual(payload['servers'][0]['server_key'], self.server.server_key)
