"""List ACL allow/deny comparisons across FG-evaluated pilot data and BG control data.

Usage:
    python manage.py list_acls [--json]
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from django.core.management.base import BaseCommand

from bg.state.models import AccessRule, MumbleUser


def _load_access_rules() -> list[dict[str, Any]]:
    return list(
        AccessRule.objects.values(
            "entity_id",
            "entity_type",
            "deny",
        )
    )


def _query_character_rows(pilot_db_conn, all_referenced_ids, rs) -> list[dict[str, Any]]:
    ids = all_referenced_ids(rs)
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
            ec.character_id,
            ec.character_name,
            COALESCE(ec.corporation_name, '') AS corporation_name,
            COALESCE(ec.alliance_name, '') AS alliance_name,
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


def _bg_state_lists() -> dict[str, list[dict[str, Any]]]:
    qs = MumbleUser.objects.select_related("user", "server").order_by("user_id", "server__display_order", "server__name")
    active: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []

    for row in qs:
        pilot_name = row.display_name or row.username or row.user.username or ""
        id_value = int(row.user_id)
        summary = {"id": id_value, "pilot_name": pilot_name}
        if row.is_active:
            active.append(summary)
        else:
            blocked.append(summary)

        rows.append(
            {
                "id": id_value,
                "pilot_name": pilot_name,
                "is_active": bool(row.is_active),
            }
        )

    return {
        "bg_active": active,
        "bg_blocked": blocked,
        "bg_rows": rows,
    }


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

    return sorted(
        deduped,
        key=lambda row: (
            row["id"] is None,
            row["id"] if row["id"] is not None else 0,
            row["pilot_name"],
        ),
    )


def _acl_from_sets(*, has_permit: bool, has_deny: bool) -> str:
    if has_permit and has_deny:
        return "mixed"
    if has_permit:
        return "permit"
    if has_deny:
        return "deny"
    return "missing"


def _build_comparison_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    fg_allow_by_id: dict[int, set[str]] = defaultdict(set)
    fg_deny_by_id: dict[int, set[str]] = defaultdict(set)
    fg_unresolved_allow: set[str] = set()
    fg_unresolved_deny: set[str] = set()

    for row in report["fg_allowed"]:
        if row.get("id") is None:
            fg_unresolved_allow.add(str(row.get("pilot_name") or ""))
            continue
        fg_allow_by_id[int(row["id"])].add(str(row.get("pilot_name") or ""))

    for row in report["fg_denied"]:
        if row.get("id") is None:
            fg_unresolved_deny.add(str(row.get("pilot_name") or ""))
            continue
        fg_deny_by_id[int(row["id"])].add(str(row.get("pilot_name") or ""))

    bg_active_by_id: dict[int, list[dict[str, Any]]] = defaultdict(list)
    bg_blocked_by_id: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in report["bg_rows"]:
        id_value = int(row["id"])
        if row.get("is_active"):
            bg_active_by_id[id_value].append(row)
        else:
            bg_blocked_by_id[id_value].append(row)

    all_ids = sorted(set(fg_allow_by_id) | set(fg_deny_by_id) | set(bg_active_by_id) | set(bg_blocked_by_id))
    comparison: list[dict[str, str]] = []

    for id_value in all_ids:
        fg_acl = _acl_from_sets(
            has_permit=bool(fg_allow_by_id.get(id_value)),
            has_deny=bool(fg_deny_by_id.get(id_value)),
        )
        bg_acl = _acl_from_sets(
            has_permit=bool(bg_active_by_id.get(id_value)),
            has_deny=bool(bg_blocked_by_id.get(id_value)),
        )

        pilot_names = sorted(fg_allow_by_id.get(id_value, set()) | fg_deny_by_id.get(id_value, set()))
        if not pilot_names:
            pilot_names = sorted(
                {
                    str(r.get("pilot_name") or r.get("display_name") or r.get("username") or "")
                    for r in (bg_active_by_id.get(id_value, []) + bg_blocked_by_id.get(id_value, []))
                }
            )

        bg_names = sorted(
            {
                str(r.get("pilot_name") or "")
                for r in (bg_active_by_id.get(id_value, []) + bg_blocked_by_id.get(id_value, []))
                if str(r.get("pilot_name") or "")
            }
        )
        bg_name_value = ", ".join(bg_names) if bg_names else "-"
        bg_control_data = f"name={bg_name_value}; acl={bg_acl}"

        name_value = ", ".join(pilot_names) if pilot_names else bg_name_value
        if fg_acl == bg_acl:
            comparison.append(
                {
                    "id": str(id_value),
                    "name": name_value,
                    "db": "pilot_data,bg_control_data",
                    "acl": fg_acl,
                }
            )
        else:
            comparison.append(
                {
                    "id": str(id_value),
                    "name": name_value,
                    "db": "pilot_data",
                    "acl": fg_acl,
                }
            )
            comparison.append(
                {
                    "id": str(id_value),
                    "name": bg_name_value,
                    "db": "bg_control_data",
                    "acl": bg_acl,
                }
            )

    for pilot_name in sorted(name for name in fg_unresolved_allow if name):
        comparison.append(
            {
                "id": "-",
                "name": pilot_name,
                "db": "pilot_data",
                "acl": "permit",
            }
        )

    for pilot_name in sorted(name for name in fg_unresolved_deny if name):
        comparison.append(
            {
                "id": "-",
                "name": pilot_name,
                "db": "pilot_data",
                "acl": "deny",
            }
        )

    return comparison


class Command(BaseCommand):
    help = (
        "List ACL comparison rows using id (pkid contract identity), combining FG eligibility and BG control data."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="Output results as JSON.",
        )

    def handle(self, **options):
        report: dict[str, Any] = {
            "fg_status": "unknown",
            "fg_message": "",
            "fg_allowed": [],
            "fg_denied": [],
            "comparison_rows": [],
        }
        report.update(_bg_state_lists())

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
                report["fg_message"] = (
                    "no data to evaluate (no local copy, and no access to pilot database)"
                )
            else:
                try:
                    rules = _load_access_rules()
                    rs = build_rule_sets(rules)
                    char_rows = _query_character_rows(conn, all_referenced_ids, rs)
                    if not char_rows:
                        report["fg_status"] = "no_data"
                        report["fg_message"] = "no data to evaluate (no matching rules/characters)"
                    else:
                        ids = sorted(
                            {
                                int(row["user_id"])
                                for row in char_rows
                                if row.get("user_id") is not None
                            }
                        )
                        main_rows = _query_main_rows(conn, ids)
                        allowed = eligible_account_list(char_rows, main_rows, rs)
                        denied = blocked_main_list(char_rows, main_rows, rs)
                        report["fg_allowed"] = _map_eval_entries(allowed, main_rows)
                        report["fg_denied"] = _map_eval_entries(denied, main_rows)
                        report["fg_status"] = "ok"
                        report["fg_message"] = "evaluated via fgbg_common"
                finally:
                    conn.close()

        report["comparison_rows"] = _build_comparison_rows(report)

        if options["json"]:
            self.stdout.write(json.dumps(report, indent=2))
            return

        self.stdout.write("id is the pkid contract identity")
        self.stdout.write(f"FG evaluation status: {report['fg_status']}")
        if report["fg_message"]:
            self.stdout.write(f"FG message: {report['fg_message']}")
        self.stdout.write("")
        self.stdout.write(f"ACL Comparison ({len(report['comparison_rows'])} rows)")

        headers = ["id", "name", "db", "acl"]
        widths = {header: len(header) for header in headers}
        for row in report["comparison_rows"]:
            for header in headers:
                widths[header] = max(widths[header], len(str(row[header])))

        self.stdout.write(
            f"{'id'.ljust(widths['id'])} | "
            f"{'name'.ljust(widths['name'])} | "
            f"{'db'.ljust(widths['db'])} | "
            f"{'acl'.ljust(widths['acl'])}"
        )
        self.stdout.write(
            f"{'-' * widths['id']}-+-"
            f"{'-' * widths['name']}-+-"
            f"{'-' * widths['db']}-+-"
            f"{'-' * widths['acl']}"
        )

        if not report["comparison_rows"]:
            self.stdout.write("(none)")
            return

        for row in report["comparison_rows"]:
            self.stdout.write(
                f"{row['id'].ljust(widths['id'])} | "
                f"{row['name'].ljust(widths['name'])} | "
                f"{row['db'].ljust(widths['db'])} | "
                f"{row['acl'].ljust(widths['acl'])}"
            )
