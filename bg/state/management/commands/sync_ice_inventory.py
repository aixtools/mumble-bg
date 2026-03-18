"""Sync ICE env config into bg-owned mumble_server rows."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from bg.db import PilotDBError
from bg.ice_inventory import (
    list_current_ice_inventory,
    parse_ice_env,
    sync_ice_inventory_from_env,
)


class Command(BaseCommand):
    help = "Sync ICE env inventory into MumbleServer rows (additive by default)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Compute and print changes but do not write to DB.",
        )
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Disable active DB rows not present in ICE env.",
        )
        parser.add_argument(
            "--show-current",
            action="store_true",
            help="Print current mumble_server inventory after sync.",
        )
        parser.add_argument(
            "--show-env",
            action="store_true",
            help="Print parsed ICE env entries.",
        )
        parser.add_argument(
            "--no-sync",
            action="store_true",
            help="Skip sync and only print requested info (--show-env/--show-current).",
        )

    def handle(self, **options):
        show_env = bool(options["show_env"])
        show_current = bool(options["show_current"])
        no_sync = bool(options["no_sync"])
        dry_run = bool(options["dry_run"])
        additive = not bool(options["replace"])

        if show_env:
            try:
                env_entries = [entry.__dict__ for entry in parse_ice_env()]
            except PilotDBError as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(json.dumps({"ice_env_entries": env_entries}, indent=2))

        if not no_sync:
            try:
                result = sync_ice_inventory_from_env(additive=additive, dry_run=dry_run)
            except PilotDBError as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(json.dumps(result, indent=2))

        if show_current:
            try:
                rows = list_current_ice_inventory()
            except PilotDBError as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(json.dumps({"mumble_server_inventory": rows}, indent=2))
