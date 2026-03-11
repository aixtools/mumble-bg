from types import ModuleType, SimpleNamespace
import sys

import pytest

from bg.db import (
    PilotDBError,
    DBAdapterObject,
    MmblBgDBA,
    PilotDBA,
    db_config_from_env,
)


def test_db_config_from_env_loads_json_object(monkeypatch):
    monkeypatch.setenv(
        "DATABASES",
        '{"pilot":{"name":"pilot","host":"127.0.0.1","username":"pilot_user","database":"pilot_db","password":"secret"}}',
    )

    config = db_config_from_env(
        "DATABASES",
        "pilot",
        default_database="pilot",
        default_host="localhost",
        default_username="pilot",
    )

    assert config.name == "pilot_db"
    assert config.host == "127.0.0.1"
    assert config.user == "pilot_user"
    assert config.password == "secret"


def test_db_config_from_env_rejects_missing_required_fields(monkeypatch):
    monkeypatch.setenv(
        "DATABASES",
        '{"bg":{"host":"127.0.0.1","username":"bg_user","database":"bg_data"}}',
    )

    with pytest.raises(PilotDBError) as exc_info:
        db_config_from_env(
            "DATABASES",
            "bg",
            default_database="mumble",
            default_host="localhost",
            default_username="cube",
        )

    assert "password" in str(exc_info.value)


def test_db_config_from_env_rejects_missing_named_object(monkeypatch):
    monkeypatch.setenv(
        "DATABASES",
        '{"pilot":{"host":"127.0.0.1","username":"pilot_user","database":"pilot_db","password":"secret"}}',
    )

    with pytest.raises(PilotDBError) as exc_info:
        db_config_from_env(
            "DATABASES",
            "bg",
            default_database="mumble",
            default_host="localhost",
            default_username="cube",
        )

    assert "missing required object: bg" in str(exc_info.value)


def test_pilot_dba_autodetect_prefers_postgresql_first(monkeypatch):
    config = DBAdapterObject(name="pilot", host="localhost", user="u", password="p", engine="")
    adapter = PilotDBA(config)

    called = []

    def fake_connect(dbname=None, host=None, port=None, user=None, password=None):
        called.append((dbname, host, port, user, password))
        return object()

    monkeypatch.setitem(sys.modules, "psycopg2", SimpleNamespace(connect=fake_connect))
    if "mysql" in sys.modules:
        del sys.modules["mysql"]
    if "mysql.connector" in sys.modules:
        del sys.modules["mysql.connector"]

    conn = adapter.connect()
    assert conn is not None
    assert called == [("pilot", "127.0.0.1", "5432", "u", "p")]


def test_pilot_dba_autodetect_falls_back_to_mysql(monkeypatch):
    config = DBAdapterObject(name="pilot", host="localhost", user="u", password="p", engine="")
    adapter = PilotDBA(config)

    class PsyException(Exception):
        pass

    def fake_connect_raise(**kwargs):
        raise PsyException("postgres down")

    def fake_mysql_connect(*, host=None, port=None, db=None, user=None, passwd=None):
        return object()

    psycopg2 = SimpleNamespace(connect=fake_connect_raise)
    monkeypatch.setitem(sys.modules, "psycopg2", psycopg2)
    monkeypatch.setitem(sys.modules, "MySQLdb", SimpleNamespace(connect=fake_mysql_connect))

    conn = adapter.connect()
    assert conn is not None


def test_pilot_dba_raises_when_no_connector_and_autodetect_needed(monkeypatch):
    config = DBAdapterObject(name="pilot", host="localhost", user="u", password="p", engine="")
    adapter = PilotDBA(config)

    def fake_connect_raise(**kwargs):
        raise Exception("psyc down")

    psycopg2 = SimpleNamespace(connect=fake_connect_raise)
    monkeypatch.setitem(sys.modules, "psycopg2", psycopg2)
    if "MySQLdb" in sys.modules:
        del sys.modules["MySQLdb"]
    monkeypatch.setitem(sys.modules, "mysql", ModuleType("mysql"))
    monkeypatch.setitem(sys.modules, "mysql.connector", ModuleType("mysql.connector"))

    with pytest.raises(PilotDBError) as exc_info:
        adapter.connect()
    assert "postgresql@127.0.0.1" in str(exc_info.value)
    assert "mysql@127.0.0.1" in str(exc_info.value)


def test_mbll_dba_supports_explicit_postgresql_and_mysql(monkeypatch):
    config = DBAdapterObject(name="mumble", host="localhost", user="u", password="p", engine="postgresql")
    adapter = MmblBgDBA(config)
    monkeypatch.setitem(sys.modules, "psycopg2", SimpleNamespace(connect=lambda **kwargs: "ok-psql"))
    assert adapter.connect() == "ok-psql"

    config_mysql = DBAdapterObject(name="mumble", host="localhost", user="u", password="p", engine="mysql")
    adapter_mysql = MmblBgDBA(config_mysql)
    monkeypatch.setitem(sys.modules, "MySQLdb", SimpleNamespace(connect=lambda **kwargs: "ok-mysql"))
    assert adapter_mysql.connect() == "ok-mysql"


def test_mbll_dba_autodetect_falls_back_to_mysql(monkeypatch):
    config = DBAdapterObject(name="mumble", host="localhost", user="u", password="p", engine="")
    adapter = MmblBgDBA(config)

    class PsyException(Exception):
        pass

    def fake_connect_raise(**kwargs):
        raise PsyException("postgres down")

    def fake_mysql_connect(*, host=None, port=None, db=None, user=None, passwd=None):
        return object()

    monkeypatch.setitem(sys.modules, "psycopg2", SimpleNamespace(connect=fake_connect_raise))
    monkeypatch.setitem(sys.modules, "MySQLdb", SimpleNamespace(connect=fake_mysql_connect))

    conn = adapter.connect()
    assert conn is not None


def test_mbll_dba_invalid_engine():
    config = DBAdapterObject(name="mumble", host="localhost", user="u", password="p", engine="sqlite")
    adapter = MmblBgDBA(config)
    with pytest.raises(PilotDBError):
        adapter.connect()
