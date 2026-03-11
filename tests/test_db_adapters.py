from types import ModuleType, SimpleNamespace
import sys

import pytest

from bg.db import (
    CubeCoreDBA,
    CubeDatabaseError,
    DBAdapterObject,
    MmblBgDBA,
)


def test_core_dba_prefers_postgresql_when_requested(monkeypatch):
    config = DBAdapterObject(name="cube", host="localhost", user="u", password="p", engine="postgresql")
    adapter = CubeCoreDBA(config)

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
    assert called == [("cube", "127.0.0.1", "5432", "u", "p")]


def test_core_dba_autodetect_falls_back_to_postgresql(monkeypatch):
    config = DBAdapterObject(name="cube", host="localhost", user="u", password="p", engine="")
    adapter = CubeCoreDBA(config)

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


def test_core_dba_raises_when_no_connector_and_autodetect_needed(monkeypatch):
    config = DBAdapterObject(name="cube", host="localhost", user="u", password="p", engine="")
    adapter = CubeCoreDBA(config)

    def fake_connect_raise(**kwargs):
        raise Exception("psyc down")

    psycopg2 = SimpleNamespace(connect=fake_connect_raise)
    monkeypatch.setitem(sys.modules, "psycopg2", psycopg2)
    if "MySQLdb" in sys.modules:
        del sys.modules["MySQLdb"]
    monkeypatch.setitem(sys.modules, "mysql", ModuleType("mysql"))
    monkeypatch.setitem(sys.modules, "mysql.connector", ModuleType("mysql.connector"))

    with pytest.raises(CubeDatabaseError) as exc_info:
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
    with pytest.raises(CubeDatabaseError):
        adapter.connect()
