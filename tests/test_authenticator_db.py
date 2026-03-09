from types import SimpleNamespace

from authenticator import authenticator
from authenticator.database import CubeDatabaseError


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, *_args, **_kwargs):
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

    def cursor(self):
        return _Cursor(self._rows)

    def close(self):
        self.closed = True

    def commit(self):
        return None


def test_get_db_connection_wraps_errors():
    class _BadAdapter:
        def connect(self):
            raise RuntimeError("bad")

    original = authenticator.CORE_DB_ADAPTER
    try:
        authenticator.CORE_DB_ADAPTER = _BadAdapter()
        try:
            authenticator.get_db_connection()
            raise AssertionError("expected CubeDatabaseError")
        except CubeDatabaseError:
            pass
    finally:
        authenticator.CORE_DB_ADAPTER = original


def test_list_cube_pilot_identities_loads_from_query(monkeypatch):
    def fake_connection():
        return _Conn([
            (1234, "Pilot One", 77, 88, "Corp Name", "Alliance Name", "", ""),
        ])

    monkeypatch.setattr(authenticator, "get_db_connection", fake_connection)

    identities = authenticator.list_cube_pilot_identities()
    assert identities
    identity = identities[0]
    assert identity.character_id == 1234
    assert identity.character_name == "Pilot One"
    assert identity.corporation_id == 77
    assert identity.alliance_id == 88
    assert identity.corporation_name == "Corp Name"
    assert identity.alliance_name == "Alliance Name"
