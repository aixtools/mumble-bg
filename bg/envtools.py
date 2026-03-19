from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ENV_KEYS = [
    "DJANGO_SETTINGS_MODULE",
    "BG_KEY_PASSPHRASE",
    "MURMUR_CONTROL_PSK",
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
