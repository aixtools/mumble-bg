from bg.authd import service as authd
from bg.db import PilotDBError


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


def test_get_db_connection_wraps_errors(monkeypatch):
    class _BadAdapter:
        def connect(self):
            raise RuntimeError("bad")

    # get_db_connection short-circuits to sqlite3.connect() when BG_USE_SQLITE
    # is set, bypassing the adapter — clear it so the adapter path runs.
    monkeypatch.delenv("BG_USE_SQLITE", raising=False)

    original = authd.BG_DB_ADAPTER
    try:
        authd.BG_DB_ADAPTER = _BadAdapter()
        try:
            authd.get_db_connection()
            raise AssertionError("expected PilotDBError")
        except PilotDBError:
            pass
    finally:
        authd.BG_DB_ADAPTER = original


def test_list_pilot_identities_loads_from_query(monkeypatch):
    def fake_connection():
        return _Conn([
            (1234, "Pilot One", 77, 88, "Corp Name", "Alliance Name", "", ""),
        ])

    monkeypatch.setattr(authd, "get_db_connection", fake_connection)

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

    monkeypatch.setattr(authd, "get_db_connection", fake_connection)

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

    monkeypatch.setattr(authd, "get_db_connection", failing_connection)

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


def test_authenticate_falls_back_to_legacy_account_username_lookup(monkeypatch):
    class _FallbackCursor:
        def __init__(self):
            self.executed = []
            self.calls = 0

        def execute(self, query, params=()):
            self.executed.append((query, params))
            self.calls += 1

        def fetchone(self):
            if self.calls == 1:
                return None
            return (
                11,            # mu.id
                42,            # mu.user_id
                99,            # mumble_userid
                "hash",        # pwhash
                "algo",        # hashfn
                "",            # pw_salt
                16000,         # kdf_iterations
                "cert-abc",    # certhash
                "admin",       # groups
                "[ALLY CORP] Pilot One",  # display_name
            )

        def close(self):
            return None

    class _FallbackConn:
        def __init__(self):
            self.cursor_obj = _FallbackCursor()
            self.closed = False

        def cursor(self):
            return self.cursor_obj

        def close(self):
            self.closed = True

    conn = _FallbackConn()
    monkeypatch.setattr(authd, "get_db_connection", lambda: conn)

    result = authd.authenticate("legacy_login", "", 1, certhash="cert-abc")

    assert result is not None
    assert conn.cursor_obj.executed[0][0] == authd.AUTH_QUERY
    assert conn.cursor_obj.executed[1][0] == authd.LEGACY_AUTH_QUERY
    assert conn.closed is True


def test_name_to_id_falls_back_to_legacy_account_username_lookup(monkeypatch):
    class _FallbackCursor:
        def __init__(self):
            self.executed = []
            self.calls = 0

        def execute(self, query, params=()):
            self.executed.append((query, params))
            self.calls += 1

        def fetchone(self):
            if self.calls == 1:
                return None
            return (123,)

        def close(self):
            return None

    class _FallbackConn:
        def __init__(self):
            self.cursor_obj = _FallbackCursor()
            self.closed = False

        def cursor(self):
            return self.cursor_obj

        def close(self):
            self.closed = True

    conn = _FallbackConn()
    monkeypatch.setattr(authd, "get_db_connection", lambda: conn)

    result = authd.name_to_id("legacy_login", 1)

    assert result == 123
    assert conn.cursor_obj.executed[0][0] == authd.NAME_TO_ID_QUERY
    assert conn.cursor_obj.executed[1][0] == authd.LEGACY_NAME_TO_ID_QUERY
    assert conn.closed is True
