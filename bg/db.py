"""Database adapters for mumble-bg runtime and pilot-source read access."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os


class PilotDBError(RuntimeError):
    """Raised when a mumble-bg database adapter or DB config cannot be used."""


@dataclass(frozen=True)
class DBAdapterObject:
    name: str
    host: str
    user: str
    password: str
    engine: str = ''


def db_config_from_env(
    env_var: str,
    key: str,
    *,
    default_database: str,
    default_host: str,
    default_username: str,
    default_password: str = '',
):
    """
    Load a JSON DB config from one env var containing keyed DB objects.

    Expected top-level shape:
    - {"pilot": {...}, "bg": {...}}

    Expected nested object keys:
    - host
    - username
    - database
    - password
    - optional name
    - optional engine
    """
    raw = (os.environ.get(env_var) or '').strip()
    if not raw:
        return DBAdapterObject(
            name=default_database,
            host=default_host,
            user=default_username,
            password=default_password,
            engine='',
        )

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PilotDBError(f'{env_var} must be valid JSON') from exc

    if not isinstance(payload, dict):
        raise PilotDBError(f'{env_var} must be a JSON object')

    payload = payload.get(key)
    if payload is None:
        raise PilotDBError(f'{env_var} is missing required object: {key}')
    if not isinstance(payload, dict):
        raise PilotDBError(f'{env_var}.{key} must be a JSON object')

    required = ['host', 'username', 'database', 'password']
    missing = [field for field in required if field not in payload or payload[field] in {None, ''}]
    if missing:
        raise PilotDBError(
            f"{env_var} is missing required fields: {', '.join(missing)}"
        )

    return DBAdapterObject(
        name=str(payload['database']),
        host=str(payload['host']),
        user=str(payload['username']),
        password=str(payload['password']),
        engine=str(payload.get('engine', '') or ''),
    )


class BaseDBA:
    """Small base used by auth/runtime paths to avoid DB logic in auth handlers."""

    def __init__(self, config: DBAdapterObject):
        self._config = config

    def connect(self):
        raise NotImplementedError


class PilotDBA(BaseDBA):
    """Read-only adapter for pilot-source data (auto-detect SQL backend)."""

    def _candidate_hosts(self):
        requested = (self._config.host or '').strip() or '127.0.0.1'
        if requested.lower() == 'localhost':
            # Prefer TCP loopback first; localhost can trigger socket semantics
            # that differ between PostgreSQL and MySQL clients.
            return ['127.0.0.1', 'localhost']
        return [requested]

    def _connect_postgresql(self, host: str):
        import psycopg2

        return psycopg2.connect(
            dbname=self._config.name,
            host=host,
            port='5432',
            user=self._config.user,
            password=self._config.password,
        )

    def _connect_mysql(self, host: str):
        try:
            import MySQLdb
        except Exception:
            try:
                import mysql.connector
            except Exception as exc:  # pragma: no cover - runtime dependency optional until needed
                raise PilotDBError(
                    'mysql client is not installed for pilot-source mysql fallback'
                ) from exc

            return mysql.connector.connect(
                host=host,
                port='3306',
                database=self._config.name,
                user=self._config.user,
                password=self._config.password,
            )

        return MySQLdb.connect(
            host=host,
            port=3306,
            db=self._config.name,
            user=self._config.user,
            passwd=self._config.password,
        )

    def connect(self):
        errors = []
        for engine in ['postgresql', 'mysql']:
            for host in self._candidate_hosts():
                try:
                    if engine == 'mysql':
                        return self._connect_mysql(host)
                    return self._connect_postgresql(host)
                except Exception as exc:  # pragma: no cover - defensive runtime fallback
                    errors.append((engine, host, exc))
                    continue
        if not errors:
            raise PilotDBError('Could not connect to pilot source via postgresql or mysql')
        attempted = '; '.join(
            f'{engine}@{host}: {exc}'
            for engine, host, exc in errors
        )
        raise PilotDBError(
            f'Could not connect to pilot source via postgresql or mysql. Attempts: {attempted}'
        ) from errors[-1][2]


class MmblBgDBA(BaseDBA):
    """Read-write adapter for mumble-bg local runtime schema."""

    def _candidate_hosts(self):
        requested = (self._config.host or '').strip() or '127.0.0.1'
        if requested.lower() == 'localhost':
            return ['127.0.0.1', 'localhost']
        return [requested]

    def connect(self):
        requested = (self._config.engine or '').strip().lower()
        if requested == 'mysql':
            candidates = ['mysql']
        elif requested in {'postgresql', 'postgres'}:
            candidates = ['postgresql']
        elif requested == '':
            candidates = ['postgresql', 'mysql']
        else:
            raise PilotDBError(f'Unsupported mumble-bg database engine={requested}')

        errors = []
        for engine in candidates:
            for host in self._candidate_hosts():
                try:
                    if engine == 'mysql':
                        return self._connect_mysql(host)
                    return self._connect_postgresql(host)
                except Exception as exc:  # pragma: no cover - defensive runtime fallback
                    errors.append((engine, host, exc))
                    continue
        if not errors:
            raise PilotDBError('Could not connect to mumble-bg via postgresql or mysql')
        attempted = '; '.join(
            f'{engine}@{host}: {exc}'
            for engine, host, exc in errors
        )
        raise PilotDBError(
            f'Could not connect to mumble-bg via postgresql or mysql. Attempts: {attempted}'
        ) from errors[-1][2]

    def _connect_postgresql(self, host: str):
        import psycopg2

        return psycopg2.connect(
            dbname=self._config.name,
            host=host,
            port='5432',
            user=self._config.user,
            password=self._config.password,
        )

    def _connect_mysql(self, host: str):
        try:
            import MySQLdb
        except Exception:
            try:
                import mysql.connector
            except Exception as exc:  # pragma: no cover - runtime dependency optional until needed
                raise PilotDBError(
                    'mysql client is not installed for the mumble-bg mysql backend'
                ) from exc

            return mysql.connector.connect(
                host=host,
                port='3306',
                database=self._config.name,
                user=self._config.user,
                password=self._config.password,
            )

        return MySQLdb.connect(
            host=host,
            port=3306,
            db=self._config.name,
            user=self._config.user,
            passwd=self._config.password,
        )
