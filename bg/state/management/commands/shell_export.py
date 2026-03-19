from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from bg.envtools import shell_single_quote


class Command(BaseCommand):
    help = "Emit a shell-safe export line: export KEY='value'"

    def add_arguments(self, parser):
        parser.add_argument("key")
        parser.add_argument("value", nargs="+")

    def handle(self, *args, **options):
        key = str(options["key"]).strip()
        if not key or not (key[0].isalpha() or key[0] == "_") or not all(
            ch.isalnum() or ch == "_" for ch in key
        ):
            raise CommandError(f"Invalid shell variable name: {key!r}")
        value = " ".join(options["value"])
        self.stdout.write(f"export {key}={shell_single_quote(value)}")
