"""Tests for the ShitSpeak driver branch of the registrations funnel and the
ShitSpeakControlClient HTTP adapter."""

import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils.timezone import now

from bg import shitspeak_control
from bg.murmur_inventory import get_server_inventory_snapshot
from bg.pilot import registrations
from bg.pilot.registrations import (
    MurmurSyncError,
    disable_murmur_registration,
    disconnect_live_sessions,
    sync_live_admin_membership,
    sync_murmur_registration,
    unregister_murmur_registration,
)
from bg.shitspeak_control import ShitSpeakControlClient, ShitSpeakControlError
from bg.state.models import MumbleServer, MumbleSession, MumbleUser


class _ServerConfig:
    """Duck-typed MumbleServer stand-in for pure client tests."""

    pk = 1
    name = 'mumble-beta'
    driver = 'shitspeak'
    control_url = 'https://voice1.example.com:64750'
    control_tls_cert = '/etc/bg/control.crt'
    control_tls_key = '/etc/bg/control.key'
    control_tls_ca = '/etc/bg/control-ca.pem'


def _client(monkeypatch, config=None):
    monkeypatch.setattr(
        ShitSpeakControlClient, '_build_ssl_context', staticmethod(lambda *a: None)
    )
    return ShitSpeakControlClient(config or _ServerConfig())


class _FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode('utf-8')

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_client_requires_https_control_url(monkeypatch):
    monkeypatch.setattr(
        ShitSpeakControlClient, '_build_ssl_context', staticmethod(lambda *a: None)
    )

    class _PlainHttp(_ServerConfig):
        control_url = 'http://voice1.example.com:64750'

    with pytest.raises(ShitSpeakControlError, match='https'):
        ShitSpeakControlClient(_PlainHttp())

    class _NoUrl(_ServerConfig):
        control_url = ''

    with pytest.raises(ShitSpeakControlError, match='control_url'):
        ShitSpeakControlClient(_NoUrl())

    class _NoClientCert(_ServerConfig):
        control_tls_cert = ''

    with pytest.raises(ShitSpeakControlError, match='client certificate'):
        ShitSpeakControlClient(_NoClientCert())


def test_kick_user_posts_to_admin_kick(monkeypatch):
    client = _client(monkeypatch)
    captured = {}

    def fake_urlopen(request, timeout=None, context=None):
        captured['url'] = request.full_url
        captured['method'] = request.get_method()
        captured['body'] = json.loads(request.data.decode('utf-8'))
        return _FakeResponse({'affected': 1, 'session': 7})

    monkeypatch.setattr(shitspeak_control.urllib.request, 'urlopen', fake_urlopen)

    result = client.kick_user(7, 'bye')

    assert captured['url'] == 'https://voice1.example.com:64750/admin/v1/kick'
    assert captured['method'] == 'POST'
    assert captured['body'] == {'session': 7, 'reason': 'bye'}
    assert result == {'affected': 1, 'session': 7}


def test_ban_builds_selector_payload(monkeypatch):
    client = _client(monkeypatch)
    captured = {}

    def fake_urlopen(request, timeout=None, context=None):
        captured['url'] = request.full_url
        captured['body'] = json.loads(request.data.decode('utf-8'))
        return _FakeResponse({'affected': 1})

    monkeypatch.setattr(shitspeak_control.urllib.request, 'urlopen', fake_urlopen)

    client.ban(cert_hash='aabb', reason='rule violation', duration_secs=3600)

    assert captured['url'] == 'https://voice1.example.com:64750/admin/v1/ban'
    assert captured['body'] == {
        'cert_hash': 'aabb',
        'reason': 'rule violation',
        'duration_secs': 3600,
    }


def test_http_error_surfaces_status_and_body(monkeypatch):
    client = _client(monkeypatch)

    def fake_urlopen(request, timeout=None, context=None):
        raise urllib.error.HTTPError(
            request.full_url, 409, 'Conflict', {}, io.BytesIO(b'{"error":"ambiguous"}')
        )

    monkeypatch.setattr(shitspeak_control.urllib.request, 'urlopen', fake_urlopen)

    with pytest.raises(ShitSpeakControlError, match='HTTP 409'):
        client.kick_user(7, 'bye')


def test_connection_error_wraps_into_control_error(monkeypatch):
    client = _client(monkeypatch)

    def fake_urlopen(request, timeout=None, context=None):
        raise urllib.error.URLError('connection refused')

    monkeypatch.setattr(shitspeak_control.urllib.request, 'urlopen', fake_urlopen)

    with pytest.raises(ShitSpeakControlError, match='connection refused'):
        client.list_online()


class ShitSpeakRegistrationFunnelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='pilot1', password='x')
        self.server = MumbleServer.objects.create(
            name='mumble-beta',
            address='voice-beta.example.com:64738',
            ice_host='',
            ice_port=6502,
            driver=MumbleServer.DRIVER_SHITSPEAK,
            control_url='https://voice1.example.com:64750',
            control_tls_cert='/etc/bg/control.crt',
            control_tls_key='/etc/bg/control.key',
            is_active=True,
        )
        self.mumble_user = MumbleUser.objects.create(
            user=self.user,
            server=self.server,
            username='pilot1',
            display_name='Pilot One',
            is_active=True,
        )

    def test_sync_murmur_registration_is_noop(self):
        assert sync_murmur_registration(self.mumble_user, password='pw') is None
        details = sync_murmur_registration(self.mumble_user, password='pw', return_details=True)
        assert details == {'murmur_userid': None, 'created': False, 'reenabled': False}

    def test_disable_and_unregister_are_noops(self):
        assert disable_murmur_registration(self.mumble_user) == {
            'changed': False,
            'murmur_userid': None,
            'already_disabled': False,
        }
        assert unregister_murmur_registration(self.mumble_user) is False

    def test_open_target_server_refuses_shitspeak_rows(self):
        with pytest.raises(MurmurSyncError, match='no Ice endpoint'):
            registrations._open_target_server(self.server)

    def test_ice_only_loops_exclude_shitspeak_rows(self):
        """The Ice-driving service loops (reconciler + pulse service) must skip
        shitspeak-driven servers — they have no ice_host and would otherwise
        fail every cycle trying to open an Ice connection to ':6502'."""
        from bg.pulse.reconciler import MurmurRegistrationReconciler
        from bg.pulse.service import MurmurPulseService

        ice_server = MumbleServer.objects.create(
            name='voice.example.com:64738',
            address='voice.example.com:64738',
            ice_host='127.0.0.1',
            ice_port=6502,
            driver=MumbleServer.DRIVER_ICE,
            is_active=True,
        )
        recon_servers = MurmurRegistrationReconciler()._load_servers()
        pulse_servers = MurmurPulseService()._load_server_configs()
        assert recon_servers == [ice_server]
        assert pulse_servers == [ice_server]
        assert self.server not in recon_servers
        assert self.server not in pulse_servers

    def test_sync_live_admin_membership_reports_zero_live_mutations(self):
        MumbleSession.objects.create(
            server=self.server,
            mumble_user=self.mumble_user,
            session_id=1048577,
            username='pilot1',
            is_active=True,
            connected_at=now(),
            last_seen=now(),
            last_state=now(),
        )
        assert sync_live_admin_membership(self.mumble_user) == 0

    def test_disconnect_live_sessions_kicks_via_control_client(self):
        MumbleSession.objects.create(
            server=self.server,
            mumble_user=self.mumble_user,
            session_id=1048577,
            username='pilot1',
            is_active=True,
            connected_at=now(),
            last_seen=now(),
            last_state=now(),
        )
        fake_client = MagicMock()
        with (
            patch('bg.shitspeak_control.ShitSpeakControlClient', return_value=fake_client),
            patch('bg.pulse.service.mark_session_disconnected') as marked,
        ):
            result = disconnect_live_sessions(self.mumble_user, reason='updated')

        assert result == {'requested': 1, 'kicked': 1, 'errors': []}
        fake_client.kick_user.assert_called_once_with(1048577, 'updated')
        marked.assert_called_once_with(self.server, 1048577)

    def test_disconnect_live_sessions_collects_kick_errors(self):
        MumbleSession.objects.create(
            server=self.server,
            mumble_user=self.mumble_user,
            session_id=1048577,
            username='pilot1',
            is_active=True,
            connected_at=now(),
            last_seen=now(),
            last_state=now(),
        )
        fake_client = MagicMock()
        fake_client.kick_user.side_effect = ShitSpeakControlError('HTTP 404 not on this node')
        with patch('bg.shitspeak_control.ShitSpeakControlClient', return_value=fake_client):
            result = disconnect_live_sessions(self.mumble_user)

        assert result['requested'] == 1
        assert result['kicked'] == 0
        assert len(result['errors']) == 1
        assert '404' in result['errors'][0]

    def test_disconnect_live_sessions_wraps_misconfiguration(self):
        MumbleSession.objects.create(
            server=self.server,
            mumble_user=self.mumble_user,
            session_id=1048577,
            username='pilot1',
            is_active=True,
            connected_at=now(),
            last_seen=now(),
            last_state=now(),
        )
        self.server.control_url = ''
        self.server.save(update_fields=['control_url'])
        with pytest.raises(MurmurSyncError, match='control_url'):
            disconnect_live_sessions(self.mumble_user)

    def test_inventory_snapshot_is_skipped_not_ice_dialed(self):
        envelope = get_server_inventory_snapshot(self.server)
        assert envelope.source == 'skipped'
        assert envelope.snapshot.fetch_status == 'skipped'
        # Idempotent on repeat.
        envelope = get_server_inventory_snapshot(self.server, force_refresh=True)
        assert envelope.snapshot.fetch_status == 'skipped'
