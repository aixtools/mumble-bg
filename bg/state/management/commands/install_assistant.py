"""No-arg install/deployment assistant checks for mumble-bg."""

from __future__ import annotations

import json
import socket
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

        for key in ("pilot_db", "bg_db"):
            if report["checks"][key]["status"] != "ok":
                report["status"] = "error"

        ice_status = report["checks"]["ice"]["status"]
        if ice_status not in {"ok", "none_defined"}:
            report["status"] = "error"

        if options["json"]:
            self.stdout.write(json.dumps(report, indent=2))
            return

        self.stdout.write(f"overall: {report['status']}")
        self.stdout.write(
            f"control_psk: {report['checks']['control_psk']['status']} "
            f"({report['checks']['control_psk']['message']})"
        )
        self.stdout.write(
            f"pilot_db: {report['checks']['pilot_db']['status']} "
            f"({report['checks']['pilot_db']['message']})"
        )
        self.stdout.write(
            f"bg_db: {report['checks']['bg_db']['status']} "
            f"({report['checks']['bg_db']['message']})"
        )
        self.stdout.write(
            f"ice: {report['checks']['ice']['status']} "
            f"({report['checks']['ice']['message']})"
        )
        for endpoint in report["checks"]["ice"].get("endpoints", []):
            self.stdout.write(
                f"  - {endpoint['name']} [{endpoint['source']}] "
                f"{endpoint['ice_host']}:{endpoint['ice_port']} -> {endpoint['status']}"
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
