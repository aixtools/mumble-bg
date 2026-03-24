from __future__ import annotations

from collections import defaultdict
import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from bg.eligibility import account_acl_state_by_pkid
from bg.pilot_snapshot import current_pilot_snapshot
from bg.state.models import AccessRule, MumbleServer, MumbleUser
from bg.pulse.reconciler import MurmurReconcileError, _MurmurServerAdapter


def _load_access_rules() -> list[dict[str, Any]]:
    return list(AccessRule.objects.values("entity_id", "entity_type", "deny"))


def _acl_by_pkid() -> dict[int, str]:
    """
    Return ACL state per pkid from shared FG/BG eligibility logic.
    Values: permit | block
    """
    try:
        from fgbg_common.eligibility import build_rule_sets
    except Exception:
        return {}
    snapshot = current_pilot_snapshot()
    if not snapshot.accounts:
        return {}
    states = account_acl_state_by_pkid(snapshot, build_rule_sets(_load_access_rules()))
    return {
        int(pkid): ("block" if state == "deny" else "permit")
        for pkid, state in states.items()
    }


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
