"""Regression tests: the ICE env inventory sync must stay compatible with
non-Ice (ShitSpeak) MumbleServer rows and with the post-0005 schema."""

import json

from bg import ice_inventory

# Column order of the SELECT in sync_ice_inventory_from_env:
# id, name, address, ice_host, ice_port, ice_secret, virtual_server_id,
# is_active, display_order, ice_tls_cert, ice_tls_key, ice_tls_ca
_MATCHED_ICE_ROW = (
    1, "Main", "localhost:64738", "127.0.0.1", 6502, None, 1, True, 1, None, None, None,
)
_STALE_ICE_ROW = (
    2, "Stale", "localhost:64739", "10.0.0.9", 6502, None, 1, True, 2, None, None, None,
)
_SHITSPEAK_ROW = (
    3, "mumble-beta", "localhost:64740", "", 6502, None, None, True, 3, None, None, None,
)

_ICE_ENV = json.dumps(
    [
        {
            "icehost": "127.0.0.1",
            "iceport": 6502,
            "address": "localhost:64738",
            "name": "Main",
            "virtual_server_id": 1,
        }
    ]
)


class _MissingDriverColumn(Exception):
    pgcode = "42703"


class _Cursor:
    def __init__(self, rows, *, driver_column=True):
        self._rows = rows
        self._driver_column = driver_column
        self.executed = []

    def execute(self, query, params=()):
        self.executed.append((query, tuple(params)))
        if "SELECT driver" in query and not self._driver_column:
            raise _MissingDriverColumn('column "driver" does not exist')

    def fetchall(self):
        last_query = self.executed[-1][0] if self.executed else ""
        if "SELECT driver" in last_query:
            return []
        return self._rows

    def close(self):
        return None


class _Conn:
    def __init__(self, rows, *, driver_column=True):
        self.cursor_obj = _Cursor(rows, driver_column=driver_column)
        self.committed = False
        self.closed = False
        self.rollbacks = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def test_replace_mode_does_not_disable_non_ice_rows(monkeypatch):
    conn = _Conn([_MATCHED_ICE_ROW, _STALE_ICE_ROW, _SHITSPEAK_ROW])
    monkeypatch.setattr(ice_inventory, "_get_bg_connection", lambda: conn)
    monkeypatch.setenv("ICE", _ICE_ENV)

    result = ice_inventory.sync_ice_inventory_from_env(additive=False, dry_run=False)

    assert result["disabled"] == 1
    disabled_ids = [row["id"] for row in result["rows"] if row["action"] == "disable"]
    assert disabled_ids == [2], "only the stale Ice row may be disabled"

    disable_updates = [
        params
        for query, params in conn.cursor_obj.executed
        if query.startswith("UPDATE mumble_server SET is_active")
    ]
    assert disable_updates == [(False, 2)]
    assert conn.committed is True


def test_replace_mode_still_disables_stale_ice_rows(monkeypatch):
    conn = _Conn([_MATCHED_ICE_ROW, _STALE_ICE_ROW])
    monkeypatch.setattr(ice_inventory, "_get_bg_connection", lambda: conn)
    monkeypatch.setenv("ICE", _ICE_ENV)

    result = ice_inventory.sync_ice_inventory_from_env(additive=False, dry_run=False)

    assert result["disabled"] == 1
    assert result["unchanged"] == 1


def test_created_rows_name_the_shitspeak_columns_explicitly(monkeypatch):
    """The env-sync INSERT must set the post-0005 NOT NULL columns itself —
    not every backend retains a database-level default."""
    conn = _Conn([])
    monkeypatch.setattr(ice_inventory, "_get_bg_connection", lambda: conn)
    monkeypatch.setenv("ICE", _ICE_ENV)

    result = ice_inventory.sync_ice_inventory_from_env(additive=True, dry_run=False)

    assert result["created"] == 1
    inserts = [
        query
        for query, _params in conn.cursor_obj.executed
        if query.lstrip().startswith("INSERT INTO mumble_server")
    ]
    assert len(inserts) == 1
    for column in ("driver", "control_url", "auth_token"):
        assert column in inserts[0], f"INSERT must name {column}"


def test_created_rows_fall_back_to_legacy_insert_before_migration(monkeypatch):
    """On a schema that predates the driver column, the probe selects the
    pre-0005 column list instead of failing every insert."""
    conn = _Conn([], driver_column=False)
    monkeypatch.setattr(ice_inventory, "_get_bg_connection", lambda: conn)
    monkeypatch.setenv("ICE", _ICE_ENV)

    result = ice_inventory.sync_ice_inventory_from_env(additive=True, dry_run=False)

    assert result["created"] == 1
    inserts = [
        query
        for query, _params in conn.cursor_obj.executed
        if query.lstrip().startswith("INSERT INTO mumble_server")
    ]
    assert len(inserts) == 1
    assert "driver" not in inserts[0]
    assert conn.rollbacks == 1, "failed probe must be rolled back before writes"
