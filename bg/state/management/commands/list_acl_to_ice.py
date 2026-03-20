"""Compare ACL decisions to ICE registrations, grouped by pilot.

Usage:
    python manage.py list_acl_to_ice [--json]
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from django.core.management.base import BaseCommand

from bg.pulse.reconciler import MurmurReconcileError, _MurmurServerAdapter
from bg.state.models import AccessRule, MumbleServer, MumbleUser


def _load_access_rules() -> list[dict[str, Any]]:
    return list(AccessRule.objects.values("entity_id", "entity_type", "deny"))


def _query_character_rows(pilot_db_conn, all_referenced_ids, rule_sets) -> list[dict[str, Any]]:
    ids = all_referenced_ids(rule_sets)
    if not ids["alliance_ids"] and not ids["corporation_ids"] and not ids["pilot_ids"]:
        return []

    conditions: list[str] = []
    params: list[int] = []
    if ids["alliance_ids"]:
        placeholders = ",".join(["%s"] * len(ids["alliance_ids"]))
        conditions.append(f"ec.alliance_id IN ({placeholders})")
        params.extend(ids["alliance_ids"])
    if ids["corporation_ids"]:
        placeholders = ",".join(["%s"] * len(ids["corporation_ids"]))
        conditions.append(f"ec.corporation_id IN ({placeholders})")
        params.extend(ids["corporation_ids"])
    if ids["pilot_ids"]:
        placeholders = ",".join(["%s"] * len(ids["pilot_ids"]))
        conditions.append(f"ec.character_id IN ({placeholders})")
        params.extend(ids["pilot_ids"])

    where = " OR ".join(conditions)
    query = f"""
        SELECT
            ec.user_id,
            ec.character_id,
            ec.character_name,
            ec.corporation_id,
            COALESCE(ec.corporation_name, '') AS corporation_name,
            ec.alliance_id,
            COALESCE(ec.alliance_name, '') AS alliance_name
        FROM accounts_evecharacter ec
        WHERE ec.pending_delete = false
          AND ({where})
        ORDER BY ec.user_id, ec.character_name
    """
    with pilot_db_conn.cursor() as cur:
        cur.execute(query, params)
        columns = [col[0] for col in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def _query_main_rows(pilot_db_conn, ids: list[int]) -> dict[int, dict[str, Any]]:
    if not ids:
        return {}
    placeholders = ",".join(["%s"] * len(ids))
    query = f"""
        SELECT
            ec.user_id,
            ec.character_name,
            ec.is_main
        FROM accounts_evecharacter ec
        WHERE ec.user_id IN ({placeholders})
          AND ec.pending_delete = false
        ORDER BY ec.user_id, ec.is_main DESC, ec.character_name
    """
    mains: dict[int, dict[str, Any]] = {}
    with pilot_db_conn.cursor() as cur:
        cur.execute(query, list(ids))
        columns = [col[0] for col in cur.description]
        for row_tuple in cur.fetchall():
            row = dict(zip(columns, row_tuple))
            mains.setdefault(int(row["user_id"]), row)
    return mains


def _map_eval_entries(entries: list[dict[str, Any]], main_rows: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    char_to_ids: dict[str, list[int]] = defaultdict(list)
    for id_value, main in main_rows.items():
        char_name = str(main.get("character_name") or "")
        if char_name:
            char_to_ids[char_name].append(int(id_value))

    normalized: list[dict[str, Any]] = []
    for entry in entries:
        pilot_name = str(entry.get("character_name") or "")
        ids = sorted(char_to_ids.get(pilot_name, []))
        if not ids:
            normalized.append({"id": None, "pilot_name": pilot_name})
            continue
        for id_value in ids:
            normalized.append({"id": id_value, "pilot_name": pilot_name})

    seen: set[tuple[int | None, str]] = set()
    deduped: list[dict[str, Any]] = []
    for row in normalized:
        key = (row["id"], row["pilot_name"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _acl_from_sets(*, has_permit: bool, has_deny: bool) -> str:
    if has_permit and has_deny:
        return "mixed"
    if has_permit:
        return "permit"
    if has_deny:
        return "deny"
    return "missing"


def _safe(text: str, *, limit: int = 80) -> str:
    txt = str(text or "")
    return txt if len(txt) <= limit else txt[: limit - 3] + "..."


class Command(BaseCommand):
    help = (
        "List ACL decision vs ICE registration state per pilot. "
        "Rows are grouped by pilot id (pkid) with one line per vsid:server."
    )

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Output results as JSON.")

    def handle(self, **options):
        report: dict[str, Any] = {
            "fg_status": "unknown",
            "fg_message": "",
            "pilots": [],
        }

        fg_allow_by_id: dict[int, set[str]] = defaultdict(set)
        fg_deny_by_id: dict[int, set[str]] = defaultdict(set)
        fg_unresolved_allow: set[str] = set()
        fg_unresolved_deny: set[str] = set()

        try:
            from fgbg_common.eligibility import (
                all_referenced_ids,
                blocked_main_list,
                build_rule_sets,
                eligible_account_list,
            )
        except Exception:
            report["fg_status"] = "unavailable"
            report["fg_message"] = "fg not configured/installed"
        else:
            from bg.authd.service import get_pilot_db_connection
            from bg.db import PilotDBError

            try:
                conn = get_pilot_db_connection()
            except PilotDBError:
                report["fg_status"] = "no_data"
                report["fg_message"] = "no data to evaluate (no local copy, and no access to pilot database)"
            else:
                try:
                    rules = _load_access_rules()
                    rule_sets = build_rule_sets(rules)
                    char_rows = _query_character_rows(conn, all_referenced_ids, rule_sets)
                    if not char_rows:
                        report["fg_status"] = "no_data"
                        report["fg_message"] = "no data to evaluate (no matching rules/characters)"
                    else:
                        ids = sorted({int(row["user_id"]) for row in char_rows if row.get("user_id") is not None})
                        main_rows = _query_main_rows(conn, ids)
                        allowed = _map_eval_entries(eligible_account_list(char_rows, main_rows, rule_sets), main_rows)
                        denied = _map_eval_entries(blocked_main_list(char_rows, main_rows, rule_sets), main_rows)
                        for row in allowed:
                            if row["id"] is None:
                                fg_unresolved_allow.add(str(row["pilot_name"] or ""))
                            else:
                                fg_allow_by_id[int(row["id"])].add(str(row["pilot_name"] or ""))
                        for row in denied:
                            if row["id"] is None:
                                fg_unresolved_deny.add(str(row["pilot_name"] or ""))
                            else:
                                fg_deny_by_id[int(row["id"])].add(str(row["pilot_name"] or ""))
                        report["fg_status"] = "ok"
                        report["fg_message"] = "evaluated via fgbg_common"
                finally:
                    conn.close()

        bg_rows = list(
            MumbleUser.objects.select_related("user", "server")
            .order_by("user_id", "server__display_order", "server__name")
        )
        bg_by_id: dict[int, list[MumbleUser]] = defaultdict(list)
        for row in bg_rows:
            bg_by_id[int(row.user_id)].append(row)

        ice_users_by_server: dict[int, set[str]] = {}
        ice_error_by_server: dict[int, str] = {}
        servers = list(MumbleServer.objects.filter(is_active=True).order_by("display_order", "name", "id"))
        for server in servers:
            try:
                with _MurmurServerAdapter(server) as adapter:
                    users = adapter._server_proxy.getRegisteredUsers("") or {}
                ice_users_by_server[int(server.id)] = {str(name or "") for name in users.values()}
            except (MurmurReconcileError, Exception) as exc:  # noqa: BLE001
                ice_error_by_server[int(server.id)] = str(exc)
                ice_users_by_server[int(server.id)] = set()

        all_ids = sorted(set(fg_allow_by_id) | set(fg_deny_by_id) | set(bg_by_id))
        pilots: list[dict[str, Any]] = []
        for id_value in all_ids:
            fg_acl = _acl_from_sets(
                has_permit=bool(fg_allow_by_id.get(id_value)),
                has_deny=bool(fg_deny_by_id.get(id_value)),
            )
            bg_active = any(row.is_active for row in bg_by_id.get(id_value, []))
            bg_deny = any(not row.is_active for row in bg_by_id.get(id_value, []))
            bg_acl = _acl_from_sets(has_permit=bg_active, has_deny=bg_deny)

            pilot_names = sorted(fg_allow_by_id.get(id_value, set()) | fg_deny_by_id.get(id_value, set()))
            if not pilot_names:
                pilot_names = sorted(
                    {
                        str(row.display_name or row.username or row.user.username or "")
                        for row in bg_by_id.get(id_value, [])
                    }
                )
            name_value = ", ".join([name for name in pilot_names if name]) or "-"

            acl_rows: list[dict[str, str]] = []
            if fg_acl == bg_acl:
                acl_rows.append({"db": "pilot_data,bg_control_data", "acl": fg_acl})
            else:
                acl_rows.append({"db": "pilot_data", "acl": fg_acl})
                acl_rows.append({"db": "bg_control_data", "acl": bg_acl})

            ice_rows: list[dict[str, str]] = []
            for row in bg_by_id.get(id_value, []):
                server = row.server
                vsid = server.virtual_server_id if server.virtual_server_id is not None else "-"
                vsid_server = f"{vsid}:{server.name}"
                if int(server.id) in ice_error_by_server:
                    reg = f"ice_error:{_safe(ice_error_by_server[int(server.id)], limit=40)}"
                else:
                    reg = "registered" if row.username in ice_users_by_server[int(server.id)] else "not_registered"
                ice_rows.append({"vsid_server": vsid_server, "registered": reg})

            if not ice_rows:
                ice_rows.append({"vsid_server": "-", "registered": "no_bg_control_row"})

            pilots.append(
                {
                    "id": str(id_value),
                    "name": name_value,
                    "acl_rows": acl_rows,
                    "ice_rows": ice_rows,
                }
            )

        for unresolved in sorted(name for name in fg_unresolved_allow if name):
            pilots.append(
                {
                    "id": "-",
                    "name": unresolved,
                    "acl_rows": [{"db": "pilot_data", "acl": "permit"}],
                    "ice_rows": [{"vsid_server": "-", "registered": "no_bg_control_row"}],
                }
            )
        for unresolved in sorted(name for name in fg_unresolved_deny if name):
            pilots.append(
                {
                    "id": "-",
                    "name": unresolved,
                    "acl_rows": [{"db": "pilot_data", "acl": "deny"}],
                    "ice_rows": [{"vsid_server": "-", "registered": "no_bg_control_row"}],
                }
            )

        report["pilots"] = pilots

        if options["json"]:
            self.stdout.write(json.dumps(report, indent=2))
            return

        self.stdout.write("id is the pkid contract identity")
        self.stdout.write(f"FG evaluation status: {report['fg_status']}")
        if report["fg_message"]:
            self.stdout.write(f"FG message: {report['fg_message']}")
        self.stdout.write("")

        headers = ["id", "name", "db", "acl", "vsid:server", "registered"]
        widths = {header: len(header) for header in headers}
        for pilot in pilots:
            max_lines = max(len(pilot["acl_rows"]), len(pilot["ice_rows"]))
            for idx in range(max_lines):
                acl_row = pilot["acl_rows"][idx] if idx < len(pilot["acl_rows"]) else {"db": "", "acl": ""}
                ice_row = pilot["ice_rows"][idx] if idx < len(pilot["ice_rows"]) else {"vsid_server": "", "registered": ""}
                row_values = {
                    "id": pilot["id"] if idx == 0 else "",
                    "name": pilot["name"] if idx == 0 else "",
                    "db": acl_row["db"],
                    "acl": acl_row["acl"],
                    "vsid:server": ice_row["vsid_server"],
                    "registered": ice_row["registered"],
                }
                for header in headers:
                    widths[header] = max(widths[header], len(str(row_values[header])))

        def _row(values: dict[str, str]) -> str:
            return (
                f"{values['id'].ljust(widths['id'])} | "
                f"{values['name'].ljust(widths['name'])} | "
                f"{values['db'].ljust(widths['db'])} | "
                f"{values['acl'].ljust(widths['acl'])} | "
                f"{values['vsid:server'].ljust(widths['vsid:server'])} | "
                f"{values['registered'].ljust(widths['registered'])}"
            )

        self.stdout.write(_row({h: h for h in headers}))
        self.stdout.write(
            f"{'-' * widths['id']}-+-"
            f"{'-' * widths['name']}-+-"
            f"{'-' * widths['db']}-+-"
            f"{'-' * widths['acl']}-+-"
            f"{'-' * widths['vsid:server']}-+-"
            f"{'-' * widths['registered']}"
        )

        for pilot in pilots:
            max_lines = max(len(pilot["acl_rows"]), len(pilot["ice_rows"]))
            self.stdout.write(
                f"{'=' * widths['id']}=+="
                f"{'=' * widths['name']}=+="
                f"{'=' * widths['db']}=+="
                f"{'=' * widths['acl']}=+="
                f"{'=' * widths['vsid:server']}=+="
                f"{'=' * widths['registered']}"
            )
            for idx in range(max_lines):
                acl_row = pilot["acl_rows"][idx] if idx < len(pilot["acl_rows"]) else {"db": "", "acl": ""}
                ice_row = pilot["ice_rows"][idx] if idx < len(pilot["ice_rows"]) else {"vsid_server": "", "registered": ""}
                self.stdout.write(
                    _row(
                        {
                            "id": pilot["id"] if idx == 0 else "",
                            "name": pilot["name"] if idx == 0 else "",
                            "db": acl_row["db"],
                            "acl": acl_row["acl"],
                            "vsid:server": ice_row["vsid_server"],
                            "registered": ice_row["registered"],
                        }
                    )
                )
