from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from bg.envtools import read_env_values_with_bash, shell_single_quote


ASSIGN_RE = re.compile(r"^[ \t]*(?:export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)[ \t]*=")
SENSITIVE_KEY_RE = re.compile(r"(pass|secret|key|token)", re.IGNORECASE)
RAW_RISK_TOKENS = ("\\'", '\\"', '"\'', '\'"')


@dataclass
class AssignmentBlock:
    key: str
    start: int
    end: int
    lines: list[str]
    parsed_value: str
    reason: str
    replacement: str


def _parse_blocks(lines: list[str]) -> list[tuple[str, int, int]]:
    starts: list[tuple[str, int]] = []
    for i, line in enumerate(lines):
        m = ASSIGN_RE.match(line)
        if m:
            starts.append((m.group(1), i))
    blocks: list[tuple[str, int, int]] = []
    for idx, (key, start) in enumerate(starts):
        end = starts[idx + 1][1] if idx + 1 < len(starts) else len(lines)
        blocks.append((key, start, end))
    return blocks


def _has_raw_risk(raw_block: str) -> bool:
    if any(tok in raw_block for tok in RAW_RISK_TOKENS):
        return True
    if re.search(r'"\'[^"\n]+\'"', raw_block):
        return True
    return False


def _json_suggest(value: str) -> str | None:
    try:
        payload = json.loads(value)
    except Exception:
        return None

    changed = False

    def walk(node):
        nonlocal changed
        if isinstance(node, dict):
            out = {}
            for k, v in node.items():
                if isinstance(v, str):
                    nv = v.replace("'", "\\u0027")
                    if nv != v:
                        changed = True
                    out[k] = nv
                else:
                    out[k] = walk(v)
            return out
        if isinstance(node, list):
            return [walk(item) for item in node]
        return node

    escaped = walk(payload)
    if not changed:
        return None
    return json.dumps(escaped, indent=2)


class Command(BaseCommand):
    help = (
        "Scan env file for potentially unsafe quote/escape patterns and optionally "
        "rewrite in place by commenting original blocks and appending corrected assignments."
    )

    def add_arguments(self, parser):
        parser.add_argument("--file", default="~/.env/mumble-bg", help="Path to env file")
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Apply updates without confirmation prompt.",
        )

    def handle(self, *args, **options):
        env_file = Path(options["file"]).expanduser()
        if not env_file.is_file():
            raise CommandError(f"Missing env file: {env_file}")

        text = env_file.read_text(encoding="utf-8")
        lines = text.splitlines()
        blocks = _parse_blocks(lines)
        if not blocks:
            self.stdout.write(f"OK: no KEY=VALUE assignments found in {env_file}")
            return

        keys = [key for key, _, _ in blocks]
        try:
            values = read_env_values_with_bash(env_file, keys)
        except Exception as exc:
            raise CommandError(f"Failed to parse env file via shell: {exc}") from exc

        findings: list[AssignmentBlock] = []
        for key, start, end in blocks:
            block_lines = lines[start:end]
            raw_block = "\n".join(block_lines)
            parsed_value = values.get(key, "")
            raw_risk = _has_raw_risk(raw_block)
            json_suggestion = _json_suggest(parsed_value)

            if json_suggestion is not None:
                reason = "json quote/escape normalization suggested"
                replacement = f"{key}={shell_single_quote(json_suggestion)}"
            elif raw_risk:
                reason = "raw quote/backslash pattern may be interpreted unexpectedly"
                replacement = f"{key}={shell_single_quote(parsed_value)}"
            elif SENSITIVE_KEY_RE.search(key) and any(ch in parsed_value for ch in "'\"\\"):
                reason = "sensitive key with quote/backslash characters"
                replacement = f"{key}={shell_single_quote(parsed_value)}"
            else:
                continue

            findings.append(
                AssignmentBlock(
                    key=key,
                    start=start,
                    end=end,
                    lines=block_lines,
                    parsed_value=parsed_value,
                    reason=reason,
                    replacement=replacement,
                )
            )

        if not findings:
            self.stdout.write("OK: no potential issues detected")
            return

        self.stdout.write("Potential issues:")
        for item in findings:
            self.stdout.write("")
            self.stdout.write(f"KEY: {item.key}")
            self.stdout.write(f"REASON: {item.reason}")
            self.stdout.write("CURRENT:")
            if item.parsed_value:
                self.stdout.write(item.parsed_value)
            else:
                self.stdout.write("<empty>")
            self.stdout.write("PROPOSED:")
            self.stdout.write(item.replacement)

        self.stdout.write("")
        apply_updates = bool(options["yes"])
        if not apply_updates:
            answer = input("Apply inline fixes to file? [y/N]: ").strip().lower()
            apply_updates = answer in {"y", "yes"}

        if not apply_updates:
            self.stdout.write("No changes applied.")
            return

        out_lines = list(lines)
        for item in reversed(findings):
            commented_original = [f"# ORIGINAL {item.key} (kept by scan_env_values):"]
            commented_original.extend([f"# {line}" for line in item.lines])
            replacement_block = [
                f"# UPDATED {item.key}: {item.reason}",
                item.replacement,
            ]
            out_lines[item.start:item.end] = [*commented_original, *replacement_block]

        env_file.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        self.stdout.write(f"Updated: {env_file}")
        self.stdout.write(f"Applied {len(findings)} fix block(s).")
