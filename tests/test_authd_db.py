from bg.authd import main as authd
from bg.db import CubeDatabaseError


class _Cursor:
    def __init__(self, rows):
        self._rows = rows
        self.executed = []

    def execute(self, *_args, **_kwargs):
        self.executed.append(_args[0] if _args else None)
        return None

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def __enter__(self):
        return self

    def __exit__(self, *exc):  # noqa: ARG002
        return False


class _Conn:
    def __init__(self, rows):
        self._rows = rows
        self.closed = False
        self.cursor_obj = _Cursor(self._rows)

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True

    def commit(self):
        return None


def test_get_db_connection_wraps_errors():
    class _BadAdapter:
        def connect(self):
            raise RuntimeError("bad")

    original = authd.BG_DB_ADAPTER
    try:
        authd.BG_DB_ADAPTER = _BadAdapter()
        try:
            authd.get_db_connection()
            raise AssertionError("expected CubeDatabaseError")
        except CubeDatabaseError:
            pass
    finally:
        authd.BG_DB_ADAPTER = original


def test_list_pilot_identities_loads_from_query(monkeypatch):
    def fake_connection():
        return _Conn([
            (1234, "Pilot One", 77, 88, "Corp Name", "Alliance Name", "", ""),
        ])

    monkeypatch.setattr(authd, "get_pilot_db_connection", fake_connection)

    identities = authd.list_pilot_identities()
    assert identities
    identity = identities[0]
    assert identity.character_id == 1234
    assert identity.character_name == "Pilot One"
    assert identity.corporation_id == 77
    assert identity.alliance_id == 88
    assert identity.corporation_name == "Corp Name"
    assert identity.alliance_name == "Alliance Name"


def test_list_pilot_identities_normalizes_optional_identity_fields(monkeypatch):
    def fake_connection():
        return _Conn([
            (1234, "Pilot One", None, None, None, None, None, None),
        ])

    monkeypatch.setattr(authd, "get_pilot_db_connection", fake_connection)

    identities = authd.list_pilot_identities()
    identity = identities[0]
    assert identity.corporation_id is None
    assert identity.alliance_id is None
    assert identity.corporation_name == ""
    assert identity.alliance_name == ""
    assert identity.corporation_ticker == ""
    assert identity.alliance_ticker == ""


def test_list_pilot_identities_returns_empty_on_query_error(monkeypatch):
    def failing_connection():
        raise RuntimeError("db down")

    monkeypatch.setattr(authd, "get_pilot_db_connection", failing_connection)

    assert authd.list_pilot_identities() == []


def test_get_active_servers_uses_primary_query(monkeypatch):
    conn = _Conn([
        (1, "127.0.0.1", 6502, "secret", 7),
    ])

    monkeypatch.setattr(authd, "get_db_connection", lambda: conn)

    servers = authd.get_active_servers()

    assert servers == [(1, "127.0.0.1", 6502, "secret", 7)]
    assert conn.cursor_obj.executed == [authd.SERVERS_QUERY]
    assert conn.closed is True


def test_get_active_servers_falls_back_when_virtual_server_id_column_is_missing(monkeypatch):
    class MissingVirtualServerId(Exception):
        pgcode = "42703"

    class _LegacyCursor(_Cursor):
        def __init__(self, rows):
            super().__init__(rows)
            self.calls = 0

        def execute(self, query, *_args, **_kwargs):
            self.executed.append(query)
            self.calls += 1
            if self.calls == 1:
                raise MissingVirtualServerId('column "virtual_server_id" does not exist')
            return None

    class _LegacyConn(_Conn):
        def __init__(self, rows):
            super().__init__(rows)
            self.cursor_obj = _LegacyCursor(self._rows)

    conn = _LegacyConn([
        (1, "127.0.0.1", 6502, "secret", 1),
    ])

    monkeypatch.setattr(authd, "get_db_connection", lambda: conn)

    servers = authd.get_active_servers()

    assert servers == [(1, "127.0.0.1", 6502, "secret", 1)]
    assert conn.cursor_obj.executed == [
        authd.SERVERS_QUERY,
        authd.LEGACY_SERVERS_QUERY,
    ]
    assert conn.closed is True


def test_wait_for_server_configs_sleeps_until_data_exists(monkeypatch):
    calls = []
    sleep_calls = []

    def fake_get_active_servers():
        calls.append(True)
        if len(calls) == 1:
            return []
        return [(1, "127.0.0.1", 6502, "secret", 1)]

    monkeypatch.setattr(authd, "get_active_servers", fake_get_active_servers)
    monkeypatch.setattr(authd.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    servers = authd.wait_for_server_configs(retry_interval=7)

    assert servers == [(1, "127.0.0.1", 6502, "secret", 1)]
    assert len(calls) == 2
    assert sleep_calls == [7]
