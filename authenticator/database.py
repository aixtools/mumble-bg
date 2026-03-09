"""Database adapters for cube-mumble runtime and cube-core read access."""

from __future__ import annotations

from dataclasses import dataclass


class CubeDatabaseError(RuntimeError):
    """Raised when a cube-mumble database adapter cannot connect."""


@dataclass(frozen=True)
class DBAdapterObject:
    name: str
    host: str
    user: str
    password: str
    engine: str = ''


class CubeCoreBaseDBA:
    """Small base used by auth/runtime paths to avoid DB logic in auth handlers."""

    def __init__(self, config: DBAdapterObject):
        self._config = config

    def connect(self):
        raise NotImplementedError


class CubeCoreDBA(CubeCoreBaseDBA):
    """Read-only adapter for cube-core source data (prefer SQL-compatible backends)."""

    def __init__(self, config: DBAdapterObject):
        super().__init__(config=config)
        self._candidates = self._build_candidates(config.engine)

    def _build_candidates(self, engine: str):
        requested = (engine or '').strip().lower()
        if requested in {'postgresql', 'mysql'}:
            return [requested]
        return ['postgresql', 'mysql']

    def _connect_postgresql(self):
        import psycopg2

        return psycopg2.connect(
            dbname=self._config.name,
            host=self._config.host,
            port='5432',
            user=self._config.user,
            password=self._config.password,
        )

    def _connect_mysql(self):
        try:
            import mysql.connector
        except Exception as exc:  # pragma: no cover - runtime dependency optional until needed
            raise CubeDatabaseError(
                'mysql connector is not installed for cube-core mysql fallback'
            ) from exc

        return mysql.connector.connect(
            host=self._config.host,
            port='3306',
            database=self._config.name,
            user=self._config.user,
            password=self._config.password,
        )

    def connect(self):
        last_error = None
        for engine in self._candidates:
            try:
                if engine == 'mysql':
                    return self._connect_mysql()
                return self._connect_postgresql()
            except Exception as exc:  # pragma: no cover - defensive runtime fallback
                last_error = exc
                continue
        raise CubeDatabaseError('Could not connect to cube-core via postgresql or mysql') from last_error


class CubeMmbleAuthDatabaseAdapter(CubeCoreBaseDBA):
    """Read-write adapter for cube-mmble local runtime schema."""

    def connect(self):
        requested = (self._config.engine or '').strip().lower()
        if requested == 'mysql':
            return self._connect_mysql()
        if requested in {'', 'postgresql', 'postgres'}:
            return self._connect_postgresql()
        raise CubeDatabaseError(f'Unsupported CUBE_MMBL_AUTH_DATABASE_ENGINE={requested}')

    def _connect_postgresql(self):
        import psycopg2

        return psycopg2.connect(
            dbname=self._config.name,
            host=self._config.host,
            port='5432',
            user=self._config.user,
            password=self._config.password,
        )

    def _connect_mysql(self):
        try:
            import mysql.connector
        except Exception as exc:  # pragma: no cover - runtime dependency optional until needed
            raise CubeDatabaseError(
                'mysql connector is not installed for CUBE_MMBL_AUTH_DATABASE_ENGINE=mysql'
            ) from exc

        return mysql.connector.connect(
            host=self._config.host,
            port='3306',
            database=self._config.name,
            user=self._config.user,
            password=self._config.password,
        )
