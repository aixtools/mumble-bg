from __future__ import annotations

from collections import defaultdict
import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from bg.state.models import AccessRule, MumbleServer, MumbleUser
from bg.pulse.reconciler import MurmurReconcileError, _MurmurServerAdapter


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


def _acl_by_pkid() -> dict[int, str]:
    """
    Return ACL state per pkid from shared FG/BG eligibility logic.
    Values: permit | block
    """
    try:
        from fgbg_common.eligibility import (
            all_referenced_ids,
            blocked_main_list,
            build_rule_sets,
            eligible_account_list,
        )
    except Exception:
        return {}

    from bg.authd.service import get_pilot_db_connection
    from bg.db import PilotDBError

    try:
        conn = get_pilot_db_connection()
    except PilotDBError:
        return {}

    try:
        rule_sets = build_rule_sets(_load_access_rules())
        char_rows = _query_character_rows(conn, all_referenced_ids, rule_sets)
        if not char_rows:
            return {}
        ids = sorted({int(row["user_id"]) for row in char_rows if row.get("user_id") is not None})
        main_rows = _query_main_rows(conn, ids)
        char_to_ids: dict[str, list[int]] = defaultdict(list)
        for pkid, main in main_rows.items():
            name = str(main.get("character_name") or "")
            if name:
                char_to_ids[name].append(int(pkid))

        acl_map: dict[int, str] = {}
        for row in eligible_account_list(char_rows, main_rows, rule_sets):
            name = str(row.get("character_name") or "")
            for pkid in char_to_ids.get(name, []):
                acl_map[int(pkid)] = "permit"
        for row in blocked_main_list(char_rows, main_rows, rule_sets):
            name = str(row.get("character_name") or "")
            for pkid in char_to_ids.get(name, []):
                acl_map[int(pkid)] = "block"
        return acl_map
    finally:
        conn.close()


def _pick_registration(rows: list[MumbleUser], username: str) -> MumbleUser | None:
    if not rows:
        return None
    exact = [row for row in rows if str(row.username) == username]
    candidates = exact if exact else rows
    candidates = sorted(candidates, key=lambda row: (not row.is_active, int(row.user_id)))
    return candidates[0]


class Command(BaseCommand):
    help = "List Murmur registered users via ICE from active bg MumbleServer inventory rows"

    def add_arguments(self, parser):
        parser.add_argument(
            "--server-id",
            type=int,
            help="Only query one bg MumbleServer row by primary key.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit results as JSON.",
        )

    def handle(self, *args, **options):
        acl_by_pkid = _acl_by_pkid()
        server_id = options.get("server_id")
        qs = MumbleServer.objects.filter(is_active=True).order_by("display_order", "name", "id")
        if server_id is not None:
            qs = qs.filter(pk=server_id)
        servers = list(qs)
        if not servers:
            raise CommandError("No active MumbleServer rows matched")

        payload: list[dict] = []
        for server in servers:
            try:
                with _MurmurServerAdapter(server) as adapter:
                    users = adapter._server_proxy.getRegisteredUsers("") or {}
            except MurmurReconcileError as exc:
                raise CommandError(
                    f"Failed ICE query for server_row={server.id} ({server.name}): {exc}"
                ) from exc
            except Exception as exc:  # noqa: BLE001
                raise CommandError(
                    f"Failed ICE query for server_row={server.id} ({server.name}): {exc}"
                ) from exc

            ice_entries = [
                {"murmur_userid": int(uid), "username": str(name)}
                for uid, name in sorted(users.items(), key=lambda item: int(item[0]))
            ]
            ice_names = {row["username"] for row in ice_entries}

            registrations = list(
                MumbleUser.objects.select_related("user")
                .filter(server=server)
                .order_by("username", "user_id")
            )
            by_username: dict[str, list[MumbleUser]] = defaultdict(list)
            for reg in registrations:
                by_username[str(reg.username).lower()].append(reg)

            by_pkid: dict[int, MumbleUser] = {}
            for reg in registrations:
                by_pkid[int(reg.user_id)] = reg

            enriched_rows: list[dict[str, Any]] = []
            all_pkids = sorted(set(by_pkid.keys()) | set(acl_by_pkid.keys()))
            for pkid in all_pkids:
                reg = by_pkid.get(int(pkid))
                username = str(reg.username) if reg is not None else ""
                registered = bool(username and username in ice_names)
                acl_state = acl_by_pkid.get(int(pkid), "missing")
                if acl_state == "block":
                    state = "deny"
                else:
                    state = "active" if registered else "missing"
                enriched_rows.append(
                    {
                        "pkid": int(pkid),
                        "username": username,
                        "state": state,
                    }
                )

            mapped_usernames = {str(row.username).lower() for row in registrations}
            for user in ice_entries:
                username = str(user["username"])
                if username.lower() in mapped_usernames:
                    continue
                enriched_rows.append(
                    {
                        "pkid": "",
                        "username": username,
                        "state": "active",
                    }
                )

            enriched_rows.sort(
                key=lambda row: (
                    row["pkid"] != "",
                    int(row["pkid"]) if row["pkid"] != "" else -1,
                    str(row["username"]).lower(),
                )
            )

            payload.append(
                {
                    "server_row_id": int(server.id),
                    "server_name": server.name,
                    "ice_host": server.ice_host,
                    "ice_port": int(server.ice_port),
                    "virtual_server_id": server.virtual_server_id,
                    "registered_count": len(enriched_rows),
                    "users": enriched_rows,
                }
            )

        if options["json"]:
            self.stdout.write(json.dumps(payload, indent=2))
            return

        for row in payload:
            self.stdout.write(
                "== "
                f"server_row={row['server_row_id']} "
                f"name={row['server_name']} "
                f"ice={row['ice_host']}:{row['ice_port']} "
                f"vs={row['virtual_server_id']} "
                f"count={row['registered_count']} "
                "=="
            )
            name_vsid = f"{row['server_name']}:{row['virtual_server_id']}"
            self.stdout.write("name:vsid       pkid   username                 state")
            self.stdout.write("--------------  -----  -----------------------  -------")
            for user in row["users"]:
                pkid = str(user["pkid"]) if user["pkid"] != "" else ""
                self.stdout.write(
                    f"{name_vsid:<14}  "
                    f"{pkid:>5}  "
                    f"{user['username']:<23}  "
                    f"{user['state']:<7}"
                )
            self.stdout.write("")
