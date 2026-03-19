from __future__ import annotations

import getpass
import grp
import os
import sys
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


def _detect_venv_dir() -> Path:
    prefix = Path(sys.prefix).resolve()
    if (prefix / "bin" / "python").exists():
        return prefix
    py = Path(sys.executable).resolve()
    if py.parent.name == "bin":
        return py.parent.parent
    return prefix


class Command(BaseCommand):
    help = "Print a systemd unit file for mumble-bg authd."

    def add_arguments(self, parser):
        parser.add_argument("--env-file", required=True, help="Path to BG environment file.")
        parser.add_argument(
            "--working-dir",
            default=str(Path.cwd()),
            help="WorkingDirectory for systemd service.",
        )
        parser.add_argument("--user", default=getpass.getuser(), help="systemd User value.")
        parser.add_argument(
            "--group",
            default=grp.getgrgid(os.getgid()).gr_name,
            help="systemd Group value.",
        )

    def handle(self, *args, **options):
        env_file = Path(options["env_file"]).expanduser()
        if not env_file.exists():
            raise CommandError(f"--env-file not found: {env_file}")

        venv_dir = _detect_venv_dir()
        py = venv_dir / "bin" / "python"
        if not py.exists():
            py = Path(sys.executable).resolve()

        unit = f"""[Unit]
Description=mumble-bg ICE authenticator
After=network.target postgresql.service mumble-server.service

[Service]
User={options["user"]}
Group={options["group"]}
WorkingDirectory={options["working_dir"]}
EnvironmentFile={env_file}
Environment=DJANGO_SETTINGS_MODULE=bg.settings
ExecStart={py} -m bg.authd
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
        self.stdout.write(unit.rstrip("\n"))
