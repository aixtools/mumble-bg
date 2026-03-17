"""Read-only helpers for inspecting a Murmur backing store."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3


USER_INFO_NAME = 0
USER_INFO_EMAIL = 1
USER_INFO_COMMENT = 2
USER_INFO_HASH = 3
USER_INFO_PASSWORD = 4
USER_INFO_LAST_ACTIVE = 5
USER_INFO_KDF_ITERATIONS = 6

USER_INFO_KEYS = {
    USER_INFO_NAME: "username",
    USER_INFO_EMAIL: "email",
    USER_INFO_COMMENT: "comment",
    USER_INFO_HASH: "certhash",
    USER_INFO_PASSWORD: "password",
    USER_INFO_LAST_ACTIVE: "last_active_info",
    USER_INFO_KDF_ITERATIONS: "kdfiterations_info",
}


@dataclass(frozen=True)
class MurmurRegisteredUser:
    server_id: int
    user_id: int
    username: str
    pw: str
    salt: str
    kdfiterations: int | None
    lastchannel: int | None
    last_active: str | None
    last_disconnect: str | None
    user_info: dict[str, str]

    @property
    def certhash(self) -> str:
        return self.user_info.get("certhash", "")


class SqliteMurmurProbeError(RuntimeError):
    """Raised when a SQLite-backed Murmur probe cannot operate."""


class SqliteMurmurProbe:
    """Read-only view over a Murmur SQLite database."""

    def __init__(self, sqlite_path: str | Path):
        self._path = Path(sqlite_path)

    @property
    def path(self) -> Path:
        return self._path

    def _connect(self) -> sqlite3.Connection:
        if not self._path.exists():
            raise SqliteMurmurProbeError(f"Murmur SQLite database does not exist: {self._path}")
        return sqlite3.connect(f"file:{self._path}?mode=ro", uri=True)

    def list_registered_users(self, *, server_id: int = 1) -> list[MurmurRegisteredUser]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    server_id,
                    user_id,
                    name,
                    COALESCE(pw, ''),
                    COALESCE(salt, ''),
                    kdfiterations,
                    lastchannel,
                    last_active,
                    last_disconnect
                FROM users
                WHERE server_id = ?
                ORDER BY user_id
                """,
                (server_id,),
            )
            rows = cur.fetchall()
            info = self._load_user_info(cur, server_id=server_id)
            return [
                MurmurRegisteredUser(
                    server_id=int(row[0]),
                    user_id=int(row[1]),
                    username=str(row[2] or ""),
                    pw=str(row[3] or ""),
                    salt=str(row[4] or ""),
                    kdfiterations=int(row[5]) if row[5] is not None else None,
                    lastchannel=int(row[6]) if row[6] is not None else None,
                    last_active=str(row[7]) if row[7] is not None else None,
                    last_disconnect=str(row[8]) if row[8] is not None else None,
                    user_info=info.get(int(row[1]), {}),
                )
                for row in rows
            ]
        except sqlite3.Error as exc:
            raise SqliteMurmurProbeError(f"Failed to query Murmur SQLite database {self._path}: {exc}") from exc
        finally:
            conn.close()

    def get_registered_user(
        self,
        *,
        server_id: int = 1,
        username: str | None = None,
        user_id: int | None = None,
    ) -> MurmurRegisteredUser | None:
        for row in self.list_registered_users(server_id=server_id):
            if username is not None and row.username.lower() == username.lower():
                return row
            if user_id is not None and row.user_id == user_id:
                return row
        return None

    def _load_user_info(self, cur: sqlite3.Cursor, *, server_id: int) -> dict[int, dict[str, str]]:
        cur.execute(
            """
            SELECT user_id, key, COALESCE(value, '')
            FROM user_info
            WHERE server_id = ?
            ORDER BY user_id, key
            """,
            (server_id,),
        )
        rows = cur.fetchall()
        results: dict[int, dict[str, str]] = {}
        for user_id, key, value in rows:
            bucket = results.setdefault(int(user_id), {})
            bucket[USER_INFO_KEYS.get(int(key), f"key_{int(key)}")] = str(value or "")
        return results
