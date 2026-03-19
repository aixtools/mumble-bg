from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from bg.pulse.reconciler import MurmurReconcileError, _MurmurServerAdapter
from bg.state.models import MumbleServer


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

            user_rows = [
                {"murmur_userid": int(uid), "username": str(name)}
                for uid, name in sorted(users.items(), key=lambda item: int(item[0]))
            ]
            payload.append(
                {
                    "server_row_id": int(server.id),
                    "server_name": server.name,
                    "ice_host": server.ice_host,
                    "ice_port": int(server.ice_port),
                    "virtual_server_id": server.virtual_server_id,
                    "registered_count": len(user_rows),
                    "users": user_rows,
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
            for user in row["users"]:
                self.stdout.write(f"{user['murmur_userid']:>6}  {user['username']}")
            self.stdout.write("")
