from __future__ import annotations

import logging
import json
import ipaddress
import os
import re
import socket
import subprocess
from typing import Any, Mapping
from urllib.parse import urlparse
from pathlib import Path


logger = logging.getLogger(__name__)

ENV_KEYS = [
    "DJANGO_SETTINGS_MODULE",
    "BG_ENV_FILE",
    "BG_PKI_PASSPHRASE",
    "BG_BIND",
    "BG_DBMS",
    "BG_PSK",
    "MURMUR_CONTROL_URL",
    "DATABASES",
    "ICE",
    "MURMUR_PROBE",
]


def shell_single_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def read_env_values_with_bash(source_file: Path, keys: list[str]) -> dict[str, str]:
    source_file = source_file.expanduser().resolve()
    proc = subprocess.run(
        [
            "bash",
            "-lc",
            (
                "set -euo pipefail; "
                f"set -a; source {shell_single_quote(str(source_file))}; set +a; "
                + " ".join([f"printf '%s\\0%s\\0' {shell_single_quote(k)} \"${{{k}-}}\";" for k in keys])
            ),
        ],
        check=True,
        capture_output=True,
        text=False,
    )
    parts = proc.stdout.split(b"\0")
    out: dict[str, str] = {}
    for i in range(0, len(parts) - 1, 2):
        key = parts[i].decode("utf-8", errors="replace")
        val = parts[i + 1].decode("utf-8", errors="replace")
        out[key] = val
    return out


def parse_assigned_keys(env_text: str) -> list[str]:
    pattern = re.compile(r"^[ \t]*(?:export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)[ \t]*=", re.MULTILINE)
    seen = set()
    keys: list[str] = []
    for m in pattern.finditer(env_text):
        k = m.group(1)
        if k not in seen:
            seen.add(k)
            keys.append(k)
    return keys


def count_ice_entries(ice_raw: str) -> int:
    try:
        payload = json.loads(ice_raw)
    except Exception:
        return 0
    if isinstance(payload, list):
        return len(payload)
    return 0


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(str(host))
        return True
    except ValueError:
        return False


def _format_bind_host(host: str) -> str:
    return f"[{host}]" if ":" in host else host


def _is_missing_env_value(key: str) -> bool:
    return not str(os.environ.get(key) or "").strip()


def _pick_resolved_address(host: str, port: int) -> str:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not infos:
        raise OSError(f"no DNS records for {host}")

    ipv4 = [info for info in infos if info[0] == socket.AF_INET]
    ipv6 = [info for info in infos if info[0] == socket.AF_INET6]
    chosen = ipv4[0] if ipv4 else (ipv6[0] if ipv6 else infos[0])
    return str(chosen[4][0])


def resolve_bg_bind(
    env: Mapping[str, Any] | None = None,
    *,
    default_bind: str = "127.0.0.1:18080",
) -> dict[str, str]:
    """
    Resolve the runserver bind address from environment contract:
      1) BG_BIND
      2) MURMUR_CONTROL_URL host:port (hostname resolved to concrete IP)
      3) default_bind
    """
    values = env or {}
    bg_bind = str(values.get("BG_BIND") or "").strip()
    if bg_bind:
        return {
            "bind": bg_bind,
            "source": "BG_BIND",
            "detail": "explicit override",
        }

    control_url = str(values.get("MURMUR_CONTROL_URL") or "").strip()
    if not control_url:
        return {
            "bind": default_bind,
            "source": "default",
            "detail": "MURMUR_CONTROL_URL not set",
        }

    parsed = urlparse(control_url)
    host = str(parsed.hostname or "").strip()
    if not host:
        return {
            "bind": default_bind,
            "source": "default",
            "detail": "MURMUR_CONTROL_URL has no hostname",
        }

    if parsed.port is not None:
        port = int(parsed.port)
    elif parsed.scheme == "https":
        port = 443
    else:
        port = 80

    if _is_ip_literal(host):
        bind_host = host
        detail = "MURMUR_CONTROL_URL literal IP"
    else:
        try:
            bind_host = _pick_resolved_address(host, port)
            detail = f"MURMUR_CONTROL_URL host resolved: {host} -> {bind_host}"
        except Exception as exc:  # noqa: BLE001
            return {
                "bind": default_bind,
                "source": "default",
                "detail": f"failed to resolve {host}: {exc}",
            }

    return {
        "bind": f"{_format_bind_host(bind_host)}:{port}",
        "source": "MURMUR_CONTROL_URL",
        "detail": detail,
    }


def load_env_file_into_environment(
    source_file: Path | str,
    *,
    override: bool = False,
) -> dict[str, str]:
    """Load shell-style env assignments into os.environ."""
    env_path = Path(source_file).expanduser().resolve()
    env_text = env_path.read_text(encoding="utf-8")
    env_keys = list(dict.fromkeys([*ENV_KEYS, *parse_assigned_keys(env_text)]))
    env_values = read_env_values_with_bash(env_path, env_keys)

    applied: dict[str, str] = {}
    for key, value in env_values.items():
        if override or key not in os.environ:
            os.environ[key] = value
            applied[key] = value
    if _is_missing_env_value("BG_DBMS") and (
        env_values.get("DATABASES") or os.environ.get("DATABASES")
    ):
        legacy_value = str(env_values.get("DATABASES") or os.environ.get("DATABASES") or "")
        os.environ["BG_DBMS"] = legacy_value
        applied["BG_DBMS"] = legacy_value
    if _is_missing_env_value("BG_PSK") and (
        env_values.get("BG_PSK") or os.environ.get("BG_PSK")
    ):
        current_value = str(env_values.get("BG_PSK") or os.environ.get("BG_PSK") or "")
        os.environ["BG_PSK"] = current_value
        applied["BG_PSK"] = current_value
    if _is_missing_env_value("BG_PKI_PASSPHRASE") and (
        env_values.get("BG_KEY_PASSPHRASE") or os.environ.get("BG_KEY_PASSPHRASE")
    ):
        current_value = str(
            env_values.get("BG_KEY_PASSPHRASE") or os.environ.get("BG_KEY_PASSPHRASE") or ""
        )
        os.environ["BG_PKI_PASSPHRASE"] = current_value
        applied["BG_PKI_PASSPHRASE"] = current_value
        if current_value.strip():
            logger.warning("BG_KEY_PASSPHRASE is deprecated; use BG_PKI_PASSPHRASE instead")
    return applied


def bootstrap_bg_environment(
    *,
    env_file_var: str = "BG_ENV_FILE",
    default_settings_module: str = "bg.settings",
) -> str | None:
    """Load BG env from BG_ENV_FILE or ~/.env/mumble-bg, then ensure settings."""
    env_file = (os.environ.get(env_file_var) or "").strip()
    if not env_file:
        default_env = Path("~/.env/mumble-bg").expanduser()
        if default_env.exists():
            env_file = str(default_env)
            os.environ[env_file_var] = env_file
    if env_file:
        load_env_file_into_environment(env_file, override=False)
    if not str(os.environ.get("DJANGO_SETTINGS_MODULE") or "").strip():
        os.environ["DJANGO_SETTINGS_MODULE"] = default_settings_module
    return env_file or None
