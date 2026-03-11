"""Database adapters for mumble-bg runtime and pilot-source read access."""

from __future__ import annotations

from dataclasses import dataclass


class CubeDatabaseError(RuntimeError):
    """Raised when a mumble-bg database adapter cannot connect."""


@dataclass(frozen=True)
class DBAdapterObject:
    name: str
    host: str
    user: str
    password: str
    engine: str = ''


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
                raise CubeDatabaseError(
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
            raise CubeDatabaseError('Could not connect to pilot source via postgresql or mysql')
        attempted = '; '.join(
            f'{engine}@{host}: {exc}'
            for engine, host, exc in errors
        )
        raise CubeDatabaseError(
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
            raise CubeDatabaseError(f'Unsupported mumble-bg database engine={requested}')

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
            raise CubeDatabaseError('Could not connect to mumble-bg via postgresql or mysql')
        attempted = '; '.join(
            f'{engine}@{host}: {exc}'
            for engine, host, exc in errors
        )
        raise CubeDatabaseError(
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
                raise CubeDatabaseError(
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
