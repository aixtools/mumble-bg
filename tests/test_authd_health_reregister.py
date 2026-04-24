"""Tests for authd health-tick re-registration behavior (Murmur restart survival)."""

from unittest.mock import MagicMock

import pytest

from bg.authd import service as authd
from tests.conftest import IceOwnedInvalidUserException


class _FakeSrv:
    def __init__(self, virtual_id=1, uptime_seq=None):
        self._virtual_id = virtual_id
        self._uptime_seq = list(uptime_seq or [0])
        self.set_auth_calls = []
        self.set_auth_raise = None

    def id(self):
        return self._virtual_id

    def getUptime(self):
        if len(self._uptime_seq) > 1:
            return self._uptime_seq.pop(0)
        return self._uptime_seq[0]

    def ice_invocationTimeout(self, _ms):
        return self

    def setAuthenticator(self, auth_proxy):
        if self.set_auth_raise is not None:
            raise self.set_auth_raise
        self.set_auth_calls.append(auth_proxy)


class _FakeAuthProxy:
    def ice_getIdentity(self):
        return object()


class _FakeAdapter:
    def __init__(self):
        self.removed = []

    def remove(self, identity):
        self.removed.append(identity)


def _make_state(srv, pairs=None, last_uptime=None, config=None):
    auth_proxy = _FakeAuthProxy()
    pairs = pairs if pairs is not None else [(srv, auth_proxy)]
    return {
        'config': config or (42, '127.0.0.1', 6502, '', None),
        'pairs': pairs,
        'last_uptime': last_uptime if last_uptime is not None else {srv.id(): 3600},
        'failures': 0,
    }


def test_detect_restart_returns_true_when_uptime_regresses():
    srv = _FakeSrv(virtual_id=1, uptime_seq=[30])
    assert authd._detect_restart([(srv, _FakeAuthProxy())], {1: 3600}, 60) is True


def test_detect_restart_false_when_uptime_advances_steadily():
    srv = _FakeSrv(virtual_id=1, uptime_seq=[3660])
    assert authd._detect_restart([(srv, _FakeAuthProxy())], {1: 3600}, 60) is False


def test_detect_restart_true_when_uptime_advances_less_than_interval():
    # uptime moved forward by 2s in a 60s window -> likely restart
    srv = _FakeSrv(virtual_id=1, uptime_seq=[3602])
    assert authd._detect_restart([(srv, _FakeAuthProxy())], {1: 3600}, 60) is True


def test_health_tick_rearms_every_call(monkeypatch):
    srv = _FakeSrv(virtual_id=1, uptime_seq=[3700])
    state = _make_state(srv)
    live = {42: state}

    # The happy path should not touch the DB cleanup helpers.
    cleared = []
    monkeypatch.setattr(authd, '_clear_server_mumble_userids', lambda sid: cleared.append(sid))

    adapter = _FakeAdapter()
    authd._run_health_tick(
        communicator=object(), adapter=adapter, M=object(), ScopedAuthenticator=object(),
        server_id=42, state=state, live_servers=live,
    )

    assert len(srv.set_auth_calls) == 1
    assert state['last_uptime'] == {1: 3700}
    assert state['failures'] == 0
    assert cleared == []
    # No full reconnect — adapter.remove not called.
    assert adapter.removed == []


def test_health_tick_clears_caches_on_uptime_regression(monkeypatch):
    srv = _FakeSrv(virtual_id=1, uptime_seq=[30])
    state = _make_state(srv)
    live = {42: state}

    cleared_servers = []
    monkeypatch.setattr(authd, '_clear_server_mumble_userids', lambda sid: cleared_servers.append(sid))
    authd._validated_ids[999] = 1.0  # seed cache

    adapter = _FakeAdapter()
    authd._run_health_tick(
        communicator=object(), adapter=adapter, M=object(), ScopedAuthenticator=object(),
        server_id=42, state=state, live_servers=live,
    )

    assert cleared_servers == [42]
    assert 999 not in authd._validated_ids
    # Re-arm still happened without a full reconnect.
    assert len(srv.set_auth_calls) == 1
    assert adapter.removed == []
    assert state['last_uptime'] == {1: 30}


def test_health_tick_full_reconnect_when_rearm_raises(monkeypatch):
    srv = _FakeSrv(virtual_id=1, uptime_seq=[3700])
    srv.set_auth_raise = RuntimeError('ICE pipe broken')
    state = _make_state(srv)
    live = {42: state}

    new_srv = _FakeSrv(virtual_id=1, uptime_seq=[5])
    new_pair = (new_srv, _FakeAuthProxy())

    monkeypatch.setattr(authd, '_register_authenticator', lambda *a, **kw: [new_pair])
    cleared_servers = []
    monkeypatch.setattr(authd, '_clear_server_mumble_userids', lambda sid: cleared_servers.append(sid))

    adapter = _FakeAdapter()
    authd._run_health_tick(
        communicator=object(), adapter=adapter, M=object(), ScopedAuthenticator=object(),
        server_id=42, state=state, live_servers=live,
    )

    assert live[42]['pairs'] == [new_pair]
    assert live[42]['failures'] == 0
    assert cleared_servers == [42]
    assert len(adapter.removed) == 1  # old servant was removed from adapter


def test_health_tick_counts_consecutive_reconnect_failures(monkeypatch):
    srv = _FakeSrv(virtual_id=1, uptime_seq=[3700])
    srv.set_auth_raise = RuntimeError('ICE pipe broken')
    state = _make_state(srv)
    state['failures'] = 4  # next failure should escalate to ERROR
    live = {42: state}

    monkeypatch.setattr(authd, '_register_authenticator', MagicMock(side_effect=RuntimeError('meta down')))

    adapter = _FakeAdapter()
    authd._run_health_tick(
        communicator=object(), adapter=adapter, M=object(), ScopedAuthenticator=object(),
        server_id=42, state=state, live_servers=live,
    )

    assert state['failures'] == 5
    # Pairs untouched — reconnect failed.
    assert state['pairs'][0][0] is srv


def test_provision_uses_existing_registration(monkeypatch):
    class _Srv:
        def __init__(self):
            self.register_calls = 0

        def getRegisteredUsers(self, _filter):
            return {77: 'Alice'}

        def registerUser(self, info):  # pragma: no cover - should not be reached
            self.register_calls += 1
            return -1

    stored = []
    monkeypatch.setattr(authd, '_store_mumble_userid', lambda bg_id, mid: stored.append((bg_id, mid)))

    class _M:
        class UserInfo:
            UserName = 'name'
            UserPassword = 'pw'
            UserComment = 'comment'

        InvalidUserException = IceOwnedInvalidUserException

    srv = _Srv()
    result = authd._provision_murmur_registration(
        bg_row_id=101, username='alice', display_name='Alice', M=_M, srv=srv,
    )

    assert result == 77
    assert stored == [(101, 77)]
    assert srv.register_calls == 0


def test_provision_swallows_invalid_user_exception(monkeypatch):
    class _M:
        class UserInfo:
            UserName = 'name'
            UserPassword = 'pw'
            UserComment = 'comment'

        InvalidUserException = IceOwnedInvalidUserException

    class _Srv:
        def getRegisteredUsers(self, _filter):
            return {}

        def registerUser(self, info):
            raise _M.InvalidUserException()

    stored = []
    monkeypatch.setattr(authd, '_store_mumble_userid', lambda bg_id, mid: stored.append((bg_id, mid)))

    result = authd._provision_murmur_registration(
        bg_row_id=101, username='bob', display_name='Bob', M=_M, srv=_Srv(),
    )

    assert result is None
    assert stored == []
