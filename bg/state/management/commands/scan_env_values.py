from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from bg.envtools import parse_assigned_keys, read_env_values_with_bash, shell_single_quote


class Command(BaseCommand):
    help = "Scan env file values and print shell-safe export rewrites for tricky values."

    def add_arguments(self, parser):
        parser.add_argument("--file", default="~/.env/mumble-bg", help="Path to env file")

    def handle(self, *args, **options):
        env_file = Path(options["file"]).expanduser()
        if not env_file.is_file():
            raise CommandError(f"Missing env file: {env_file}")
        text = env_file.read_text(encoding="utf-8")
        keys = parse_assigned_keys(text)
        if not keys:
            self.stdout.write(f"No KEY=VALUE assignments found in: {env_file}")
            return
        try:
            values = read_env_values_with_bash(env_file, keys)
        except Exception as exc:
            raise CommandError(f"Failed to parse env file via shell: {exc}") from exc

        self.stdout.write(f"Scanning: {env_file}")
        self.stdout.write("")
        self.stdout.write("Only variables with tricky characters are shown.")
        self.stdout.write("")
        shown = 0
        for key in keys:
            value = values.get(key, "")
            if any(ch.isspace() for ch in value) or any(ch in value for ch in "'\"\\$#"):
                shown += 1
                self.stdout.write(f"KEY: {key}")
                self.stdout.write(f"VALUE: {value}")
                self.stdout.write(f"SAFE : export {key}={shell_single_quote(value)}")
                self.stdout.write("")
        if shown == 0:
            self.stdout.write("No tricky values detected.")
