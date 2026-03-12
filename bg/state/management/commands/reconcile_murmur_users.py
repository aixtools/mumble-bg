from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from bg.pulse.reconciler import MurmurReconcileError, MurmurRegistrationReconciler


class Command(BaseCommand):
    help = "Build a Murmur reconciliation plan from active MumbleUser rows"

    def add_arguments(self, parser):
        parser.add_argument(
            "--server-id",
            type=int,
            help="Only reconcile one mumble-bg MumbleServer row",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply plan changes. Without this flag, the command runs in dry-run mode.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit reconciliation summaries as JSON.",
        )

    def handle(self, *args, **options):
        reconciler = MurmurRegistrationReconciler(server_id=options.get("server_id"))
        try:
            results = reconciler.reconcile(dry_run=not options["apply"])
        except MurmurReconcileError as exc:
            raise CommandError(str(exc)) from exc

        payload = [result.to_dict() for result in results]
        if options["json"]:
            self.stdout.write(json.dumps(payload, indent=2))
            return

        mode = "DRY RUN" if not options["apply"] else "APPLY"
        for result in payload:
            self.stdout.write(
                f"{mode} server={result['server_name']} "
                f"create={result['planned_create_count']} "
                f"delete={result['planned_delete_count']} "
                f"applied={result['changed_count']} "
                f"failed={result['failed_count']}"
            )
            for error in result["errors"]:
                self.stderr.write(f"  ERROR: {error}")
