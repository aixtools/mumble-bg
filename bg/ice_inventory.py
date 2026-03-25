"""Helpers to map ICE env config to bg-owned MumbleServer inventory rows."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import sqlite3
import socket
from urllib.parse import urlparse

from bg.db import MmblBgDBA, PilotDBError, db_config_from_env


@dataclass(frozen=True)
class IceInventoryEntry:
    name: str
    address: str
    ice_host: str
    ice_port: int
    ice_secret: str | None
    virtual_server_id: int | None
    is_active: bool = True
    ice_tls_cert: str | None = None
    ice_tls_key: str | None = None
    ice_tls_ca: str | None = None


BG_DB_ADAPTER = MmblBgDBA(
    db_config_from_env(
        "BG_DBMS",
        "bg",
        default_database="mumble",
        default_host="localhost",
        default_username="cube",
        legacy_env_var="DATABASES",
    )
)


def _get_bg_connection():
    sqlite_path = (os.environ.get("BG_USE_SQLITE") or "").strip()
    if sqlite_path:
        return sqlite3.connect(sqlite_path)
    return BG_DB_ADAPTER.connect()


def _is_sqlite_connection(conn) -> bool:
    return isinstance(conn, sqlite3.Connection)


def _adapt_query_for_connection(conn, query: str) -> str:
    if _is_sqlite_connection(conn):
        return query.replace("%s", "?")
    return query


def _execute(cur, conn, query: str, params=()):
    cur.execute(_adapt_query_for_connection(conn, query), params)


def _first_nonempty(item: dict, keys: tuple[str, ...], default: str = "") -> str:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def _parse_bool(value, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_optional_int(raw: str) -> int | None:
    text = (raw or "").strip()
    if not text:
        return None
    return int(text)


def _looks_like_ip_literal(value: str) -> bool:
    import ipaddress

    try:
        ipaddress.ip_address(str(value).strip())
        return True
    except ValueError:
        return False


def _extract_address_host(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    if "://" in text:
        parsed = urlparse(text)
        return str(parsed.hostname or "").strip()
    if text.startswith("[") and "]" in text:
        return text[1:text.index("]")].strip()
    if text.count(":") == 1:
        host, port = text.rsplit(":", 1)
        if port.isdigit():
            return host.strip()
    return text


def _validate_network_name(value: str, *, field_name: str, idx: int) -> None:
    text = str(value or "").strip()
    if not text:
        raise PilotDBError(f"ICE[{idx}] is missing required {field_name}")
    if _looks_like_ip_literal(text):
        return
    try:
        infos = socket.getaddrinfo(text, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise PilotDBError(
            f"ICE[{idx}] {field_name}={text!r} is not a valid IP and did not resolve: {exc}"
        ) from exc
    if not infos:
        raise PilotDBError(f"ICE[{idx}] {field_name}={text!r} did not resolve")


def parse_ice_env(raw: str | None = None) -> list[IceInventoryEntry]:
    """Parse ICE JSON env payload into canonical inventory entries."""
    payload_raw = (raw if raw is not None else os.environ.get("ICE", "")).strip()
    if not payload_raw:
        return []

    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError as exc:
        raise PilotDBError("ICE must be valid JSON") from exc

    if not isinstance(payload, list):
        raise PilotDBError("ICE must be a JSON list")

    entries: list[IceInventoryEntry] = []
    for idx, row in enumerate(payload):
        if not isinstance(row, dict):
            raise PilotDBError(f"ICE[{idx}] must be a JSON object")

        ice_host = _first_nonempty(row, ("ice_host", "icehost"))
        if not ice_host:
            raise PilotDBError(f"ICE[{idx}] is missing required icehost/ice_host")
        _validate_network_name(ice_host, field_name="icehost", idx=idx)

        ice_port_raw = _first_nonempty(row, ("ice_port", "iceport", "port"), default="6502")
        try:
            ice_port = int(ice_port_raw)
        except ValueError as exc:
            raise PilotDBError(f"ICE[{idx}] has invalid ice_port/iceport/port={ice_port_raw!r}") from exc
        if ice_port <= 0:
            raise PilotDBError(f"ICE[{idx}] has invalid non-positive port={ice_port}")

        virtual_server_raw = _first_nonempty(
            row,
            ("virtual_server_id", "virtualserverid", "server_id"),
            default="",
        )
        try:
            virtual_server_id = _parse_optional_int(virtual_server_raw)
        except ValueError as exc:
            raise PilotDBError(
                f"ICE[{idx}] has invalid virtual_server_id/server_id={virtual_server_raw!r}"
            ) from exc

        ice_secret = _first_nonempty(row, ("ice_secret", "icewrite", "iceread", "secret"), default="")
        if not ice_secret:
            ice_secret = None

        def _tls_value(*keys: str) -> str | None:
            val = _first_nonempty(row, keys, default="")
            return val if val else None

        ice_tls_cert = _tls_value("ice_tls_cert", "ice_ssl_cert", "ssl_cert", "server_cert")
        ice_tls_key = _tls_value("ice_tls_key", "ice_ssl_key", "ssl_key", "key_cert")
        ice_tls_ca = _tls_value("ice_tls_ca", "ice_ssl_ca", "ca_cert")

        address = _first_nonempty(row, ("address", "mumble_address"), default="")
        if not address:
            raise PilotDBError(f"ICE[{idx}] is missing required address")
        _validate_network_name(_extract_address_host(address), field_name="address", idx=idx)

        # `name` is the user-facing server title FG renders on profile pages.
        # Keep `label` as a fallback so older env payloads still import cleanly.
        display_name = _first_nonempty(row, ("name", "label"), default="")
        if not display_name:
            display_name = str(address)

            entries.append(
                IceInventoryEntry(
                    name=display_name,
                    address=address,
                    ice_host=ice_host,
                    ice_port=ice_port,
                    ice_secret=ice_secret,
                    virtual_server_id=virtual_server_id,
                    is_active=_parse_bool(row.get("is_active"), default=True),
                    ice_tls_cert=ice_tls_cert,
                    ice_tls_key=ice_tls_key,
                    ice_tls_ca=ice_tls_ca,
                )
            )

    return entries


def list_current_ice_inventory() -> list[dict]:
    """Return current mumble_server rows in a JSON-serializable format."""
    conn = _get_bg_connection()
    try:
        cur = conn.cursor()
        _execute(
            cur,
            conn,
            """
            SELECT
                id,
                name,
                address,
                ice_host,
                ice_port,
                ice_secret,
                virtual_server_id,
                is_active,
                display_order,
                ice_tls_cert,
                ice_tls_key,
                ice_tls_ca
            FROM mumble_server
            ORDER BY display_order, id
            """,
        )
        rows = cur.fetchall()
        return [
            {
                "id": int(row[0]),
                "name": row[1] or "",
                "address": row[2] or "",
                "ice_host": row[3] or "",
                "ice_port": int(row[4]),
                "ice_secret": row[5] if row[5] else None,
                "virtual_server_id": int(row[6]) if row[6] is not None else None,
                "is_active": bool(row[7]),
                "display_order": int(row[8]),
                "ice_tls_cert": row[9] or None,
                "ice_tls_key": row[10] or None,
                "ice_tls_ca": row[11] or None,
            }
            for row in rows
        ]
    finally:
        conn.close()


def sync_ice_inventory_from_env(*, additive: bool = True, dry_run: bool = False) -> dict:
    """
    Sync ICE env payload into mumble_server rows.

    Default behavior is additive (create or update matching rows and leave
    unrelated existing rows untouched). Set additive=False to disable rows not
    present in ICE env.
    """
    env_entries = parse_ice_env()
    result = {
        "mode": "dry-run" if dry_run else "apply",
        "additive": bool(additive),
        "env_entries": len(env_entries),
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "disabled": 0,
        "rows": [],
    }
    if not env_entries:
        result["message"] = "ICE env is empty; no inventory changes applied"
        return result

    conn = _get_bg_connection()
    try:
        cur = conn.cursor()
        _execute(
            cur,
            conn,
            """
            SELECT
                id,
                name,
                address,
                ice_host,
                ice_port,
                ice_secret,
                virtual_server_id,
                is_active,
                display_order,
                ice_tls_cert,
                ice_tls_key,
                ice_tls_ca
            FROM mumble_server
            ORDER BY id
            """,
        )
        existing = cur.fetchall()
        by_key = {}
        max_display_order = 0
        for row in existing:
            key = (str(row[3]), int(row[4]), int(row[6]) if row[6] is not None else None)
            by_key[key] = row
            max_display_order = max(max_display_order, int(row[8]))

        incoming_keys = set()
        for entry in env_entries:
            key = (entry.ice_host, int(entry.ice_port), entry.virtual_server_id)
            incoming_keys.add(key)
            current = by_key.get(key)

            if current is None:
                max_display_order += 1
                result["created"] += 1
                result["rows"].append(
                    {
                        "action": "create",
                        "key": key,
                        "name": entry.name,
                        "address": entry.address,
                    }
                )
                if dry_run:
                    continue
                _execute(
                    cur,
                    conn,
                    """
                    INSERT INTO mumble_server (
                        name,
                        address,
                        ice_host,
                        ice_port,
                        ice_secret,
                        virtual_server_id,
                        is_active,
                        display_order,
                        ice_tls_cert,
                        ice_tls_key,
                        ice_tls_ca
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        entry.name,
                        entry.address,
                        entry.ice_host,
                        int(entry.ice_port),
                        entry.ice_secret,
                        entry.virtual_server_id,
                        bool(entry.is_active),
                        max_display_order,
                        entry.ice_tls_cert,
                        entry.ice_tls_key,
                        entry.ice_tls_ca,
                    ),
                )
                continue

            row_id = int(current[0])
            current_name = current[1] or ""
            current_address = current[2] or ""
            current_secret = current[5] if current[5] else None
            current_active = bool(current[7])
            current_tls_cert = current[9] or None
            current_tls_key = current[10] or None
            current_tls_ca = current[11] or None
            updates = {}
            if current_name != entry.name:
                updates["name"] = entry.name
            if current_address != entry.address:
                updates["address"] = entry.address
            if current_secret != entry.ice_secret:
                updates["ice_secret"] = entry.ice_secret
            if current_active != bool(entry.is_active):
                updates["is_active"] = bool(entry.is_active)
            if current_tls_cert != entry.ice_tls_cert:
                updates["ice_tls_cert"] = entry.ice_tls_cert
            if current_tls_key != entry.ice_tls_key:
                updates["ice_tls_key"] = entry.ice_tls_key
            if current_tls_ca != entry.ice_tls_ca:
                updates["ice_tls_ca"] = entry.ice_tls_ca

            if not updates:
                result["unchanged"] += 1
                result["rows"].append({"action": "unchanged", "id": row_id, "key": key})
                continue

            result["updated"] += 1
            result["rows"].append({"action": "update", "id": row_id, "key": key, "fields": sorted(updates.keys())})
            if dry_run:
                continue

            columns = ", ".join(f"{field} = %s" for field in updates.keys())
            values = list(updates.values()) + [row_id]
            _execute(cur, conn, f"UPDATE mumble_server SET {columns} WHERE id = %s", values)

        if not additive:
            for row in existing:
                key = (str(row[3]), int(row[4]), int(row[6]) if row[6] is not None else None)
                if key in incoming_keys:
                    continue
                if not bool(row[7]):
                    continue
                result["disabled"] += 1
                result["rows"].append({"action": "disable", "id": int(row[0]), "key": key})
                if dry_run:
                    continue
                _execute(cur, conn, "UPDATE mumble_server SET is_active = %s WHERE id = %s", (False, int(row[0])))

        if not dry_run:
            conn.commit()
    finally:
        conn.close()

    return result
