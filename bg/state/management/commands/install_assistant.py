"""No-arg install/deployment assistant checks for mumble-bg."""

from __future__ import annotations

import json
import socket
import textwrap
from typing import Any

from django.core.management.base import BaseCommand

from bg.db import MmblBgDBA, PilotDBA, PilotDBError, db_config_from_env
from bg.ice_inventory import list_current_ice_inventory, parse_ice_env


def _connectivity(host: str, port: int, timeout: float = 1.0) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


class Command(BaseCommand):
    help = (
        "Install/deployment assistant: verify pilot DB, bg DB, and ICE endpoint reachability "
        "without mutating state."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="Output full report as JSON.",
        )

    def handle(self, **options):
        report: dict[str, Any] = {
            "status": "ok",
            "checks": {},
        }

        report["checks"]["control_psk"] = self._check_control_psk()
        report["checks"]["pilot_db"] = self._check_pilot_db()
        report["checks"]["bg_db"] = self._check_bg_db()
        report["checks"]["ice"] = self._check_ice_endpoints()
        report["checks"]["authd_registration"] = self._check_authd_registration()

        for key in ("pilot_db", "bg_db", "authd_registration"):
            if report["checks"][key]["status"] != "ok":
                report["status"] = "error"

        ice_status = report["checks"]["ice"]["status"]
        if ice_status not in {"ok", "none_defined"}:
            report["status"] = "error"

        if options["json"]:
            self.stdout.write(json.dumps(report, indent=2))
            return

        summary_message = "all checks passed" if report["status"] == "ok" else "one or more checks failed"
        rows = [
            ("Overall", report["status"], summary_message),
            (
                "Control PSK",
                report["checks"]["control_psk"]["status"],
                report["checks"]["control_psk"]["message"],
            ),
            (
                "Pilot DB",
                report["checks"]["pilot_db"]["status"],
                report["checks"]["pilot_db"]["message"],
            ),
            (
                "BG DB",
                report["checks"]["bg_db"]["status"],
                report["checks"]["bg_db"]["message"],
            ),
            (
                "ICE",
                report["checks"]["ice"]["status"],
                report["checks"]["ice"]["message"],
            ),
            (
                "Authd Registration",
                report["checks"]["authd_registration"]["status"],
                report["checks"]["authd_registration"]["message"],
            ),
        ]
        self._print_table(
            headers=("Check", "Status", "Details"),
            rows=[(name, self._format_status(status), detail) for name, status, detail in rows],
            max_widths=(16, 10, 90),
        )

        endpoint_rows = report["checks"]["ice"].get("endpoints", [])
        if endpoint_rows:
            self.stdout.write("")
            self._print_table(
                headers=("ICE Source", "Name", "Endpoint", "Status", "Detail"),
                rows=[
                    (
                        endpoint.get("source", ""),
                        endpoint.get("name", ""),
                        f"{endpoint.get('ice_host', '')}:{endpoint.get('ice_port', '')}",
                        self._format_status(endpoint.get("status", "error")),
                        endpoint.get("detail", ""),
                    )
                    for endpoint in endpoint_rows
                ],
                max_widths=(10, 28, 24, 10, 64),
            )

    def _check_control_psk(self) -> dict[str, Any]:
        import os

        value = (os.environ.get("MURMUR_CONTROL_PSK") or "").strip()
        if value:
            return {"status": "ok", "message": "set"}
        return {"status": "warning", "message": "MURMUR_CONTROL_PSK is not set"}

    def _check_pilot_db(self) -> dict[str, Any]:
        adapter = PilotDBA(
            db_config_from_env(
                "DATABASES",
                "pilot",
                default_database="pilot",
                default_host="localhost",
                default_username="pilot",
            )
        )
        try:
            conn = adapter.connect()
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "message": str(exc)}
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            _ = cur.fetchone()
            cur.close()
        finally:
            conn.close()
        return {"status": "ok", "message": "connected"}

    def _check_bg_db(self) -> dict[str, Any]:
        adapter = MmblBgDBA(
            db_config_from_env(
                "DATABASES",
                "bg",
                default_database="mumble",
                default_host="localhost",
                default_username="cube",
            )
        )
        try:
            conn = adapter.connect()
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "message": str(exc)}
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            _ = cur.fetchone()
            cur.close()
        finally:
            conn.close()
        return {"status": "ok", "message": "connected"}

    def _check_ice_endpoints(self) -> dict[str, Any]:
        endpoints: list[dict[str, Any]] = []

        try:
            env_entries = parse_ice_env()
        except PilotDBError as exc:
            return {
                "status": "error",
                "message": f"ICE env parse failed: {exc}",
                "endpoints": [],
            }

        for row in env_entries:
            endpoints.append(
                {
                    "source": "env",
                    "name": row.name,
                    "ice_host": row.ice_host,
                    "ice_port": int(row.ice_port),
                }
            )

        if not endpoints:
            try:
                db_rows = list_current_ice_inventory()
            except Exception as exc:  # noqa: BLE001
                return {
                    "status": "error",
                    "message": f"could not read db inventory: {exc}",
                    "endpoints": [],
                }
            for row in db_rows:
                if not row.get("is_active", True):
                    continue
                endpoints.append(
                    {
                        "source": "db",
                        "name": row.get("name", ""),
                        "ice_host": row["ice_host"],
                        "ice_port": int(row["ice_port"]),
                    }
                )

        if not endpoints:
            return {
                "status": "none_defined",
                "message": "no ICE endpoints defined (env or active DB inventory)",
                "endpoints": [],
            }

        any_failed = False
        for endpoint in endpoints:
            ok, reason = _connectivity(endpoint["ice_host"], endpoint["ice_port"])
            endpoint["status"] = "ok" if ok else "error"
            endpoint["detail"] = reason
            if not ok:
                any_failed = True

        return {
            "status": "error" if any_failed else "ok",
            "message": "one or more ICE endpoints are unreachable" if any_failed else "all endpoints reachable",
            "endpoints": endpoints,
        }

    def _check_authd_registration(self) -> dict[str, Any]:
        try:
            from bg.authd.service import probe_authenticator_registration
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "message": f"failed to load authd probe: {exc}"}

        result = probe_authenticator_registration()
        registered = int(result.get("registered", 0))
        errors = result.get("errors") or []
        if registered > 0 and not errors:
            return {"status": "ok", "message": f"registered on {registered} target server(s)"}
        if registered > 0 and errors:
            return {
                "status": "warning",
                "message": f"partially registered ({registered} success, {len(errors)} error)",
            }
        if errors:
            first = errors[0]
            detail = first.get("error") if isinstance(first, dict) else str(first)
            return {"status": "error", "message": f"registration failed: {detail}"}
        return {"status": "error", "message": "no authenticators registered"}

    def _format_status(self, status: str) -> str:
        value = (status or "").strip().lower()
        label = value.upper() if value else "UNKNOWN"
        if value == "ok":
            return self.style.SUCCESS(label)
        if value in {"warning", "none_defined"}:
            return self.style.WARNING(label)
        return self.style.ERROR(label)

    def _print_table(
        self,
        *,
        headers: tuple[str, ...],
        rows: list[tuple[str, ...]],
        max_widths: tuple[int, ...] | None = None,
    ) -> None:
        all_rows = [headers, *rows]
        widths = [max(len(str(row[idx])) for row in all_rows) for idx in range(len(headers))]
        if max_widths:
            widths = [min(widths[idx], int(max_widths[idx])) for idx in range(len(widths))]

        def border() -> str:
            return "+" + "+".join("-" * (width + 2) for width in widths) + "+"

        def wrap_cell(text: str, width: int) -> list[str]:
            lines = []
            for segment in str(text).splitlines() or [""]:
                wrapped = textwrap.wrap(
                    segment,
                    width=width,
                    break_long_words=True,
                    break_on_hyphens=False,
                    replace_whitespace=False,
                    drop_whitespace=False,
                )
                lines.extend(wrapped or [""])
            return lines or [""]

        def render(row: tuple[str, ...]) -> list[str]:
            wrapped_cells = [wrap_cell(str(row[idx]), widths[idx]) for idx in range(len(widths))]
            height = max(len(cell_lines) for cell_lines in wrapped_cells)
            rendered = []
            for line_idx in range(height):
                rendered.append(
                    "| "
                    + " | ".join(
                        (wrapped_cells[col_idx][line_idx] if line_idx < len(wrapped_cells[col_idx]) else "").ljust(
                            widths[col_idx]
                        )
                        for col_idx in range(len(widths))
                    )
                    + " |"
                )
            return rendered

        self.stdout.write(border())
        for line in render(headers):
            self.stdout.write(line)
        self.stdout.write(border())
        for row in rows:
            for line in render(row):
                self.stdout.write(line)
        self.stdout.write(border())
