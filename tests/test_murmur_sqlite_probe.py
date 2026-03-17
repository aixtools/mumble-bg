from __future__ import annotations

import sqlite3

import pytest

from bg.probe.murmur_sql import SqliteMurmurProbe, SqliteMurmurProbeError


def _seed_probe_db(path):
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE users (server_id INTEGER NOT NULL, user_id INTEGER NOT NULL, name TEXT NOT NULL, pw TEXT, salt TEXT, kdfiterations INTEGER, lastchannel INTEGER, texture BLOB, last_active DATE, last_disconnect DATE)")
    cur.execute("CREATE TABLE user_info (server_id INTEGER NOT NULL, user_id INTEGER NOT NULL, key INTEGER, value TEXT)")
    cur.execute(
        "INSERT INTO users (server_id, user_id, name, pw, salt, kdfiterations, lastchannel, last_active, last_disconnect) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (1, 42, "Pilot_One", "pw-record", "salt-record", 16000, 7, "2026-03-17", "2026-03-17"),
    )
    cur.execute(
        "INSERT INTO user_info (server_id, user_id, key, value) VALUES (?, ?, ?, ?)",
        (1, 42, 3, "cert-hash-record"),
    )
    cur.execute(
        "INSERT INTO user_info (server_id, user_id, key, value) VALUES (?, ?, ?, ?)",
        (1, 42, 2, "Display Name"),
    )
    conn.commit()
    conn.close()


def test_sqlite_probe_reads_registered_user(tmp_path):
    db_path = tmp_path / "murmur.sqlite"
    _seed_probe_db(db_path)

    probe = SqliteMurmurProbe(db_path)
    row = probe.get_registered_user(server_id=1, username="pilot_one")

    assert row is not None
    assert row.user_id == 42
    assert row.username == "Pilot_One"
    assert row.pw == "pw-record"
    assert row.salt == "salt-record"
    assert row.kdfiterations == 16000
    assert row.certhash == "cert-hash-record"
    assert row.user_info["comment"] == "Display Name"


def test_sqlite_probe_raises_for_missing_db(tmp_path):
    probe = SqliteMurmurProbe(tmp_path / "missing.sqlite")

    with pytest.raises(SqliteMurmurProbeError):
        probe.list_registered_users()
