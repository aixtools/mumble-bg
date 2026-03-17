from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from bg.probe.murmur_sql import SqliteMurmurProbe, SqliteMurmurProbeError


class Command(BaseCommand):
    help = "Inspect a Murmur SQLite database and print registered-user state."

    def add_arguments(self, parser):
        parser.add_argument("--sqlite-path", required=True)
        parser.add_argument("--server-id", type=int, default=1)
        parser.add_argument("--username")
        parser.add_argument("--user-id", type=int)
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **options):
        probe = SqliteMurmurProbe(options["sqlite_path"])
        try:
            if options.get("username") or options.get("user_id") is not None:
                row = probe.get_registered_user(
                    server_id=options["server_id"],
                    username=options.get("username"),
                    user_id=options.get("user_id"),
                )
                payload = None if row is None else row.__dict__
            else:
                payload = [row.__dict__ for row in probe.list_registered_users(server_id=options["server_id"])]
        except SqliteMurmurProbeError as exc:
            raise CommandError(str(exc)) from exc

        if options["json"]:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return

        self.stdout.write(str(payload))
