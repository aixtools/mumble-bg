from __future__ import annotations

import getpass
import grp
import os
import sys
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from bg.envtools import ENV_KEYS, parse_assigned_keys, read_env_values_with_bash, resolve_bg_bind


def _detect_venv_dir() -> Path:
    prefix = Path(sys.prefix).resolve()
    if (prefix / "bin" / "python").exists():
        return prefix
    py = Path(sys.executable).resolve()
    if py.parent.name == "bin":
        return py.parent.parent
    return prefix


class Command(BaseCommand):
    help = "Print a systemd unit file for mumble-bg HTTP control runserver."

    def add_arguments(self, parser):
        parser.add_argument("--env-file", required=True, help="Path to BG environment file.")
        parser.add_argument(
            "--bind",
            default=None,
            help="runserver bind address. If omitted, resolves from BG_BIND then MURMUR_CONTROL_URL.",
        )
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
        parser.add_argument(
            "--key-dir",
            default="/etc/mumble-bg/keys",
            help="BG key directory for service environment.",
        )

    def handle(self, *args, **options):
        env_file = Path(options["env_file"]).expanduser()
        if not env_file.exists():
            raise CommandError(f"--env-file not found: {env_file}")
        try:
            env_text = env_file.read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"could not read --env-file: {exc}") from exc

        env_keys = list(dict.fromkeys([*ENV_KEYS, *parse_assigned_keys(env_text)]))
        try:
            env_values = read_env_values_with_bash(env_file, env_keys)
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"could not load --env-file with bash: {exc}") from exc

        venv_dir = _detect_venv_dir()
        py = venv_dir / "bin" / "python"
        if not py.exists():
            py = Path(sys.executable).resolve()

        if options.get("bind"):
            bind = str(options["bind"]).strip()
            bind_source = "--bind"
            bind_detail = "explicit command argument"
            exec_start = f"{py} -I -m bg.control_main {bind} --noreload"
        else:
            bind_info = resolve_bg_bind(env_values)
            bind = bind_info["bind"]
            bind_source = bind_info["source"]
            bind_detail = bind_info["detail"]
            exec_start = f"{py} -I -m bg.control_main --noreload"

        unit = f"""# ResolvedBind={bind}
# BindSource={bind_source}
# BindDetail={bind_detail}
[Unit]
Description=mumble-bg HTTP control server
After=network.target postgresql.service

[Service]
User={options["user"]}
Group={options["group"]}
WorkingDirectory={options["working_dir"]}
EnvironmentFile={env_file}
Environment=BG_ENV_FILE={env_file}
Environment=DJANGO_SETTINGS_MODULE=bg.settings
Environment=BG_KEY_DIR={options["key_dir"]}
Environment=PYTHONUNBUFFERED=1
ExecStart={exec_start}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
        self.stdout.write(unit.rstrip("\n"))
