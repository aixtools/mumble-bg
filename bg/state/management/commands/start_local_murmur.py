from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import time

from django.core.management.base import BaseCommand, CommandError

from bg.state.models import MumbleServer


def _pick_free_tcp_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def _wait_for_port(host: str, port: int, *, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.25):
                return True
        except OSError:
            time.sleep(0.1)
    return False


@dataclass(frozen=True)
class LocalMurmurPaths:
    root_dir: str
    ini_path: str
    sqlite_path: str
    cert_path: str
    key_path: str
    log_path: str
    pid_path: str


class LocalMurmurHarness:
    def __init__(
        self,
        *,
        root_dir: Path,
        server_name: str,
        bind_host: str,
        client_port: int,
        ice_port: int,
        ice_secret: str,
        server_id: int,
    ):
        self.root_dir = root_dir
        self.server_name = server_name
        self.bind_host = bind_host
        self.client_port = client_port
        self.ice_port = ice_port
        self.ice_secret = ice_secret
        self.server_id = server_id
        self.paths = LocalMurmurPaths(
            root_dir=str(root_dir),
            ini_path=str(root_dir / "mumble-server.ini"),
            sqlite_path=str(root_dir / "murmur.sqlite"),
            cert_path=str(root_dir / "cert.pem"),
            key_path=str(root_dir / "key.pem"),
            log_path=str(root_dir / "mumble-server.log"),
            pid_path=str(root_dir / "mumble-server.pid"),
        )

    def ensure_layout(self) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_tls_material()
        self._write_ini()

    def _ensure_tls_material(self) -> None:
        cert_path = Path(self.paths.cert_path)
        key_path = Path(self.paths.key_path)
        if cert_path.exists() and key_path.exists():
            return
        openssl_bin = shutil.which("openssl")
        if not openssl_bin:
            raise CommandError("openssl is required to generate a local Murmur TLS certificate")
        subprocess.run(
            [
                openssl_bin,
                "req",
                "-x509",
                "-nodes",
                "-newkey",
                "rsa:2048",
                "-keyout",
                str(key_path),
                "-out",
                str(cert_path),
                "-subj",
                "/CN=localhost",
                "-days",
                "7",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _write_ini(self) -> None:
        ini = "\n".join(
            [
                f"database={self.paths.sqlite_path}",
                f"host={self.bind_host}",
                f"port={self.client_port}",
                f"sslCert={self.paths.cert_path}",
                f"sslKey={self.paths.key_path}",
                "users=32",
                "bonjour=False",
                "sendversion=True",
                f"registerName={self.server_name}",
                f'ice="tcp -h {self.bind_host} -p {self.ice_port}"',
                f"icesecretwrite={self.ice_secret}",
                "",
            ]
        )
        Path(self.paths.ini_path).write_text(ini)

    def start(self, *, timeout: float = 5.0) -> int:
        pid_path = Path(self.paths.pid_path)
        if pid_path.exists():
            existing_pid = int(pid_path.read_text().strip() or "0")
            if existing_pid > 0 and _wait_for_port(self.bind_host, self.client_port, timeout=0.2):
                return existing_pid
            pid_path.unlink(missing_ok=True)

        log_handle = open(self.paths.log_path, "ab")
        try:
            process = subprocess.Popen(
                ["mumble-server", "-fg", "-ini", self.paths.ini_path],
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        finally:
            log_handle.close()
        pid_path.write_text(f"{process.pid}\n")
        if not _wait_for_port(self.bind_host, self.client_port, timeout=timeout):
            process.poll()
            log_tail = Path(self.paths.log_path).read_text(errors="replace")[-2000:]
            raise CommandError(
                "Local mumble-server failed to start or bind in time.\n"
                f"log tail:\n{log_tail}"
            )
        return int(process.pid)


class Command(BaseCommand):
    help = "Start a private local mumble-server instance backed by SQLite and register it in BG state."

    def add_arguments(self, parser):
        parser.add_argument("--name", default="Local BG Test")
        parser.add_argument("--root-dir", default="/tmp/mumble-bg-local-murmur")
        parser.add_argument("--bind-host", default="127.0.0.1")
        parser.add_argument("--client-port", type=int)
        parser.add_argument("--ice-port", type=int)
        parser.add_argument("--ice-secret")
        parser.add_argument("--virtual-server-id", type=int, default=1)
        parser.add_argument("--display-order", type=int, default=0)
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **options):
        bind_host = options["bind_host"]
        client_port = options["client_port"] or _pick_free_tcp_port(bind_host)
        ice_port = options["ice_port"] or _pick_free_tcp_port(bind_host)
        ice_secret = options["ice_secret"] or secrets.token_urlsafe(24)
        harness = LocalMurmurHarness(
            root_dir=Path(options["root_dir"]),
            server_name=options["name"],
            bind_host=bind_host,
            client_port=client_port,
            ice_port=ice_port,
            ice_secret=ice_secret,
            server_id=options["virtual_server_id"],
        )
        harness.ensure_layout()
        pid = harness.start()

        server, _created = MumbleServer.objects.update_or_create(
            name=options["name"],
            defaults={
                "address": f"{bind_host}:{client_port}",
                "ice_host": bind_host,
                "ice_port": ice_port,
                "ice_secret": ice_secret,
                "virtual_server_id": options["virtual_server_id"],
                "display_order": options["display_order"],
                "is_active": True,
            },
        )

        payload = {
            "bg_server_id": server.pk,
            "name": server.name,
            "address": server.address,
            "ice_host": server.ice_host,
            "ice_port": server.ice_port,
            "ice_secret": server.ice_secret,
            "virtual_server_id": server.virtual_server_id,
            "pid": pid,
            "paths": asdict(harness.paths),
        }
        if options["json"]:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return

        self.stdout.write(self.style.SUCCESS(f"Started local mumble-server pid={pid}"))
        self.stdout.write(f"BG MumbleServer row: id={server.pk} name={server.name}")
        self.stdout.write(f"Client endpoint: {server.address}")
        self.stdout.write(f"ICE endpoint: {server.ice_host}:{server.ice_port}")
        self.stdout.write(f"ICE secret: {server.ice_secret}")
        self.stdout.write(f"SQLite DB: {harness.paths.sqlite_path}")
        self.stdout.write(f"Config: {harness.paths.ini_path}")
        self.stdout.write(f"Log: {harness.paths.log_path}")
