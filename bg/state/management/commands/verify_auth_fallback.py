from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from bg.ice import load_ice_module
from bg.state.models import BgAudit, MumbleServer


@dataclass
class LoginAttempt:
    ok: bool
    returncode: int
    output: str


def _run_login(*, tool_python: str, tool_script: str, host: str, port: int, username: str, password: str, timeout: int) -> LoginAttempt:
    cmd = [
        tool_python,
        tool_script,
        "--server",
        host,
        "--port",
        str(port),
        "--username",
        username,
        "--password",
        password,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    output = "\n".join([proc.stdout.strip(), proc.stderr.strip()]).strip()
    return LoginAttempt(ok=(proc.returncode == 0), returncode=int(proc.returncode), output=output)


def _start_authd(*, bg_use_sqlite: str, pass_through: bool) -> subprocess.Popen:
    env = os.environ.copy()
    env["BG_USE_SQLITE"] = bg_use_sqlite
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[4])
    if pass_through:
        env["BG_AUTHD_ALWAYS_PASS_THROUGH"] = "1"
    cmd = ["/home/michael/.venv/mumble-bg/bin/python", "-m", "bg.authd"]
    return subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        start_new_session=True,
    )


def _stop_process(proc: subprocess.Popen | None):
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _connect_server_proxy(server: MumbleServer):
    try:
        import Ice
    except ImportError as exc:  # pragma: no cover
        raise CommandError("ZeroC ICE is not installed") from exc

    M = load_ice_module()
    communicator = Ice.initialize(["--Ice.ImplicitContext=Shared", "--Ice.Default.EncodingVersion=1.0"])
    try:
        if server.ice_secret:
            communicator.getImplicitContext().put("secret", server.ice_secret)
        proxy = communicator.stringToProxy(f"Meta:tcp -h {server.ice_host} -p {server.ice_port}")
        meta = M.MetaPrx.checkedCast(proxy)
        if not meta:
            raise CommandError(f"Failed to connect to ICE meta at {server.ice_host}:{server.ice_port}")
        servers = meta.getBootedServers()
        if not servers:
            raise CommandError("No booted Murmur servers found")
        target = None
        if server.virtual_server_id is not None:
            for srv in servers:
                if int(srv.id()) == int(server.virtual_server_id):
                    target = srv
                    break
        else:
            if len(servers) == 1:
                target = servers[0]
        if target is None:
            raise CommandError("Could not select target Murmur virtual server")
        return communicator, M, target
    except Exception:
        communicator.destroy()
        raise


def _ice_snapshot(server: MumbleServer, username: str) -> dict[str, Any]:
    communicator, M, proxy = _connect_server_proxy(server)
    try:
        users = proxy.getRegisteredUsers("") or {}
        target_userid = None
        for user_id, name in users.items():
            if str(name or "").strip().lower() == str(username or "").strip().lower():
                target_userid = int(user_id)
                break
        payload: dict[str, Any] = {
            "registered_count": len(users),
            "target_userid": target_userid,
            "target_name": None,
            "last_active": None,
            "last_disconnect": None,
        }
        if target_userid is not None:
            reg = proxy.getRegistration(int(target_userid)) or {}
            payload["target_name"] = str(reg.get(M.UserInfo.UserName, "") or "")
            last_active_key = getattr(M.UserInfo, "UserLastActive", None)
            last_disconnect_key = getattr(M.UserInfo, "UserLastDisconnect", None)
            if last_active_key is not None:
                payload["last_active"] = reg.get(last_active_key)
            if last_disconnect_key is not None:
                payload["last_disconnect"] = reg.get(last_disconnect_key)
        return payload
    finally:
        communicator.destroy()


class Command(BaseCommand):
    help = "Verify authd auth + Murmur fallback auth behavior with before/after ICE and audit snapshots."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--password", required=True)
        parser.add_argument("--bg-sqlite", default=os.environ.get("BG_USE_SQLITE", "/tmp/mumble-bg-test.sqlite3"))
        parser.add_argument("--server-id", type=int)
        parser.add_argument("--murmur-host", default="127.0.0.1")
        parser.add_argument("--murmur-port", type=int, default=64738)
        parser.add_argument("--login-tool-python", default="/home/michael/prj/murmur_tools/.venv/tools/bin/python")
        parser.add_argument("--login-tool-script", default="/home/michael/prj/murmur_tools/mumble-login")
        parser.add_argument("--timeout", type=int, default=12)
        parser.add_argument(
            "--fallback-mode",
            choices=["stop-authd", "pass-through"],
            default="stop-authd",
            help="stop-authd: kill authd for fallback attempt. pass-through: keep authd up but force return -2.",
        )
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]
        bg_sqlite = str(options["bg_sqlite"])

        if not Path(options["login_tool_python"]).exists():
            raise CommandError(f"Missing login tool python: {options['login_tool_python']}")
        if not Path(options["login_tool_script"]).exists():
            raise CommandError(f"Missing login tool script: {options['login_tool_script']}")
        if not Path(bg_sqlite).exists():
            raise CommandError(f"Missing BG sqlite database: {bg_sqlite}")

        server_qs = MumbleServer.objects.filter(is_active=True).order_by("id")
        if options.get("server_id") is not None:
            server_qs = server_qs.filter(pk=int(options["server_id"]))
        server = server_qs.first()
        if server is None:
            raise CommandError("No active MumbleServer found")

        authd_proc: subprocess.Popen | None = None
        try:
            before = _ice_snapshot(server, username)
            audit_before = BgAudit.objects.filter(action="pilot_login").count()

            authd_proc = _start_authd(bg_use_sqlite=bg_sqlite, pass_through=False)
            time.sleep(2)
            login_authd = _run_login(
                tool_python=options["login_tool_python"],
                tool_script=options["login_tool_script"],
                host=options["murmur_host"],
                port=int(options["murmur_port"]),
                username=username,
                password=password,
                timeout=int(options["timeout"]),
            )
            time.sleep(1)
            after_authd = _ice_snapshot(server, username)
            audit_after_authd = BgAudit.objects.filter(action="pilot_login").count()

            fallback_mode = str(options["fallback_mode"])
            if fallback_mode == "stop-authd":
                _stop_process(authd_proc)
                authd_proc = None
            else:
                _stop_process(authd_proc)
                authd_proc = _start_authd(bg_use_sqlite=bg_sqlite, pass_through=True)
                time.sleep(2)

            login_fallback = _run_login(
                tool_python=options["login_tool_python"],
                tool_script=options["login_tool_script"],
                host=options["murmur_host"],
                port=int(options["murmur_port"]),
                username=username,
                password=password,
                timeout=int(options["timeout"]),
            )
            time.sleep(1)
            after_fallback = _ice_snapshot(server, username)
            audit_after_fallback = BgAudit.objects.filter(action="pilot_login").count()

            payload = {
                "server": {
                    "id": int(server.pk),
                    "name": server.name,
                    "address": server.address,
                    "ice_host": server.ice_host,
                    "ice_port": int(server.ice_port),
                    "virtual_server_id": server.virtual_server_id,
                },
                "fallback_mode": fallback_mode,
                "before": before,
                "after_authd": after_authd,
                "after_fallback": after_fallback,
                "login_authd": asdict(login_authd),
                "login_fallback": asdict(login_fallback),
                "audit_counts": {
                    "pilot_login_before": int(audit_before),
                    "pilot_login_after_authd": int(audit_after_authd),
                    "pilot_login_after_fallback": int(audit_after_fallback),
                },
            }

            if options["json"]:
                self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
                return

            self.stdout.write(f"authd login ok: {login_authd.ok} (rc={login_authd.returncode})")
            self.stdout.write(f"fallback login ok: {login_fallback.ok} (rc={login_fallback.returncode})")
            self.stdout.write(
                "pilot_login audit counts: "
                f"{audit_before} -> {audit_after_authd} -> {audit_after_fallback}"
            )
            self.stdout.write("Use --json for full snapshot payload.")
        finally:
            _stop_process(authd_proc)
