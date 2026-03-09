from types import ModuleType, SimpleNamespace
import sys

import pytest

from authenticator.database import (
    CubeCoreDBA,
    CubeDatabaseError,
    CubeMbllDBA,
    DBAdapterObject,
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
    assert called == [("cube", "localhost", "5432", "u", "p")]


def test_core_dba_autodetect_falls_back_to_postgresql(monkeypatch):
    config = DBAdapterObject(name="cube", host="localhost", user="u", password="p", engine="")
    adapter = CubeCoreDBA(config)

    class PsyException(Exception):
        pass

    def fake_connect_raise(**kwargs):
        raise PsyException("postgres down")

    def fake_mysql_connect(*, host=None, port=None, database=None, user=None, password=None):
        return object()

    class FakeMysqlConnector:
        connect = staticmethod(fake_mysql_connect)

    psycopg2 = SimpleNamespace(connect=fake_connect_raise)
    mysql = ModuleType("mysql")
    mysql.connector = SimpleNamespace(connect=fake_mysql_connect)
    mysql_connector = ModuleType("mysql.connector")
    mysql_connector.connect = fake_mysql_connect
    monkeypatch.setitem(sys.modules, "psycopg2", psycopg2)
    monkeypatch.setitem(sys.modules, "mysql", mysql)
    monkeypatch.setitem(sys.modules, "mysql.connector", mysql_connector)

    conn = adapter.connect()
    assert conn is not None


def test_core_dba_raises_when_no_connector_and_autodetect_needed(monkeypatch):
    config = DBAdapterObject(name="cube", host="localhost", user="u", password="p", engine="")
    adapter = CubeCoreDBA(config)

    def fake_connect_raise(**kwargs):
        raise Exception("psyc down")

    missing_mysql_connector = ModuleType("mysql.connector")
    missing_mysql_connector.connect = lambda **kwargs: (_ for _ in ()).throw(CubeDatabaseError("no mysql"))
    psycopg2 = SimpleNamespace(connect=fake_connect_raise)
    monkeypatch.setitem(sys.modules, "psycopg2", psycopg2)
    monkeypatch.setitem(sys.modules, "mysql", ModuleType("mysql"))
    monkeypatch.setitem(sys.modules, "mysql.connector", missing_mysql_connector)

    with pytest.raises(CubeDatabaseError):
        adapter.connect()


def test_mbll_dba_supports_explicit_postgresql_and_mysql(monkeypatch):
    config = DBAdapterObject(name="mumble", host="localhost", user="u", password="p", engine="postgresql")
    adapter = CubeMbllDBA(config)
    monkeypatch.setitem(sys.modules, "psycopg2", SimpleNamespace(connect=lambda **kwargs: "ok-psql"))
    assert adapter.connect() == "ok-psql"

    config_mysql = DBAdapterObject(name="mumble", host="localhost", user="u", password="p", engine="mysql")
    adapter_mysql = CubeMbllDBA(config_mysql)
    mysql = ModuleType("mysql")
    mysql.connector = SimpleNamespace(connect=lambda **kwargs: "ok-mysql")
    mysql_connector = ModuleType("mysql.connector")
    mysql_connector.connect = lambda **kwargs: "ok-mysql"
    monkeypatch.setitem(sys.modules, "mysql", mysql)
    monkeypatch.setitem(sys.modules, "mysql.connector", mysql_connector)
    assert adapter_mysql.connect() == "ok-mysql"


def test_mbll_dba_invalid_engine():
    config = DBAdapterObject(name="mumble", host="localhost", user="u", password="p", engine="sqlite")
    adapter = CubeMbllDBA(config)
    with pytest.raises(CubeDatabaseError):
        adapter.connect()
