from __future__ import annotations

import logging
import argparse
import importlib
from importlib.metadata import PackageNotFoundError, version as package_version
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import threading

import django
from django.apps import apps as django_apps
from django.conf import settings

from .services.local_settings import configure_django_from_local_settings
from .services.logging_config import configure_logging
from .services.env import detect_environment
from .services.eve_repository import get_repository
from .checks import collect_connection_status, verify_connections
from .services.ice_client import ICEClient, normalize_server_id, resolve_ice_connections
from django.core.exceptions import ImproperlyConfigured
from django.db.utils import OperationalError

STATUS_HOST = "127.0.0.1"
STATUS_PORT = 38450
STATUS_PID_FILE = Path("/tmp/monitor-status-server.pid")
STATUS_FILE = Path("/tmp/monitor-status.json")
_DAEMON_ENV = "DAEMONIZED"
_SENSITIVE_KEY_PARTS = ("SECRET", "PASSWORD", "PWD", "API_KEY", "TOKEN")


def _monitor_version() -> str:
    try:
        return package_version("monitor")
    except PackageNotFoundError:
        return "unknown"


def _status_server_running() -> bool:
    try:
        with socket.create_connection((STATUS_HOST, STATUS_PORT), timeout=0.5):
            return True
    except OSError:
        return False


def _read_status_pid() -> int | None:
    if not STATUS_PID_FILE.exists():
        return None
    try:
        return int(STATUS_PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def _write_status_pid() -> None:
    STATUS_PID_FILE.write_text(f"{os.getpid()}\n", encoding="utf-8")


def _clear_status_pid() -> None:
    try:
        STATUS_PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def _write_status_snapshot(*, refresh: bool = False) -> None:
    try:
        if refresh:
            try:
                verify_connections(verbose=False)
            except SystemExit:
                pass
        status = collect_connection_status()
        app_ok: dict[str, bool] = {"AUTH": False, "CUBE": False}
        for entry in status.get("databases", []):
            alias = str(entry.get("alias") or "")
            if not alias or not bool(entry.get("ok")):
                continue
            try:
                env = detect_environment(using=alias, log=False)
            except Exception:
                continue
            if env in app_ok:
                app_ok[env] = True
        payload = {
            "timestamp": status.get("timestamp"),
            "applications": {
                "AUTH": "available" if app_ok["AUTH"] else "unavailable",
                "CUBE": "available" if app_ok["CUBE"] else "unavailable",
                "ICE": (
                    "available"
                    if any(bool(entry.get("ok")) for entry in status.get("ice", []))
                    else "unavailable"
                ),
            },
        }
        STATUS_FILE.write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        pass


def _install_status_signal_handler() -> None:
    def _handle_status_signal(_signum: int, _frame) -> None:
        threading.Thread(
            target=_write_status_snapshot,
            kwargs={"refresh": True},
            daemon=True,
        ).start()

    signal.signal(signal.SIGUSR1, _handle_status_signal)


def _read_status_snapshot() -> dict[str, object] | None:
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _request_live_status_snapshot(*, wait_seconds: float = 2.0) -> dict[str, object] | None:
    pid = _read_status_pid()
    if pid is None:
        return _read_status_snapshot()

    before_mtime = STATUS_FILE.stat().st_mtime if STATUS_FILE.exists() else 0.0
    try:
        os.kill(pid, signal.SIGUSR1)
    except Exception:
        return _read_status_snapshot()

    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if STATUS_FILE.exists():
            try:
                if STATUS_FILE.stat().st_mtime > before_mtime:
                    break
            except Exception:
                pass
        time.sleep(0.1)
    return _read_status_snapshot()


def _start_status_monitor_background() -> int:
    argv = [sys.executable, "-m", "monitor", *sys.argv[1:]]
    env = dict(os.environ)
    env[_DAEMON_ENV] = "1"
    with open(os.devnull, "rb") as devnull_in, open(os.devnull, "ab") as devnull_out:
        proc = subprocess.Popen(  # noqa: S603
            argv,
            stdin=devnull_in,
            stdout=devnull_out,
            stderr=devnull_out,
            start_new_session=True,
            close_fds=True,
            env=env,
        )
    print(f"status monitor: started (pid={proc.pid})")
    return 0


def _stop_status_server(*, wait_seconds: float = 5.0) -> bool:
    pid = _read_status_pid()
    if pid is None:
        return not _status_server_running()

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        _clear_status_pid()
        return True
    except PermissionError:
        return False

    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
            time.sleep(0.1)
        except ProcessLookupError:
            _clear_status_pid()
            return True
    return False


def _to_env_string(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


def _obfuscate_env_value(name: str, value: str) -> str:
    upper = name.upper()
    if not any(part in upper for part in _SENSITIVE_KEY_PARTS):
        return value
    if not value:
        return value
    if upper == "JANICE_API_KEY" and value == "FAKE-JANICE-API-KEY-EXAMPLE-0000":
        return value
    if "PASSWORD" in upper or "PASSWD" in upper or upper.endswith("_PWD"):
        return "YourStrongPW"
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"


def _common_env_value(left: object, right: object) -> object:
    left_str = _to_env_string(left).strip()
    right_str = _to_env_string(right).strip()
    if left_str and left_str == right_str:
        return left_str
    return ""


def _preferred_value(*values: object) -> object:
    for value in values:
        text = _to_env_string(value).strip()
        if text:
            return value
    return ""


def _python_literal(value: object) -> str:
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, int):
        return str(value)
    return json.dumps(str(value))


def _python_int_literal(value: object, default: int) -> str:
    if isinstance(value, int):
        return str(value)
    text = _to_env_string(value).strip()
    if not text:
        return str(default)
    try:
        return str(int(text))
    except ValueError:
        return str(default)


def _print_effective_env_config() -> None:
    dbs = getattr(settings, "DATABASES", {}) or {}
    default_db = dbs.get("default", {}) if isinstance(dbs, dict) else {}
    mysql_db = dbs.get("mysql", {}) if isinstance(dbs, dict) else {}
    mumble_mysql_db = dbs.get("mumble_mysql", {}) if isinstance(dbs, dict) else {}
    mumble_psql_db = dbs.get("mumble_psql", {}) if isinstance(dbs, dict) else {}
    eve_name = _preferred_value(
        _common_env_value(mysql_db.get("NAME"), default_db.get("NAME")),
        mysql_db.get("NAME"),
        default_db.get("NAME"),
    )
    eve_user = _preferred_value(
        _common_env_value(mysql_db.get("USER"), default_db.get("USER")),
        mysql_db.get("USER"),
        default_db.get("USER"),
    )
    eve_password = _preferred_value(
        _common_env_value(mysql_db.get("PASSWORD"), default_db.get("PASSWORD")),
        mysql_db.get("PASSWORD"),
        default_db.get("PASSWORD"),
    )
    eve_host = _preferred_value(
        _common_env_value(
            mysql_db.get("HOST") or "127.0.0.1",
            default_db.get("HOST") or "127.0.0.1",
        ),
        mysql_db.get("HOST") or "127.0.0.1",
        default_db.get("HOST") or "127.0.0.1",
    )
    eve_prefix = _preferred_value(
        getattr(settings, "AUTH_DBPREFIX", ""),
        getattr(settings, "CUBE_DBPREFIX", ""),
    )
    mumble_db_name = mumble_mysql_db.get("NAME") or mumble_psql_db.get("NAME")
    mumble_db_host = (
        mumble_mysql_db.get("HOST")
        or mumble_psql_db.get("HOST")
        or "127.0.0.1"
    )
    mumble_db_user = mumble_mysql_db.get("USER") or mumble_psql_db.get("USER")
    mumble_db_password = (
        mumble_mysql_db.get("PASSWORD") or mumble_psql_db.get("PASSWORD")
    )
    db_ssl_connectors = getattr(settings, "DB_SSL_CONNECTORS", None)
    if isinstance(db_ssl_connectors, dict):
        db_ssl_connectors = [dict(db_ssl_connectors)]
    elif isinstance(db_ssl_connectors, (list, tuple)):
        db_ssl_connectors = [
            dict(entry)
            for entry in db_ssl_connectors
            if isinstance(entry, dict)
        ]
    else:
        db_ssl_connectors = []
    if not db_ssl_connectors:
        legacy_db_ssl: list[dict[str, str]] = []
        for candidate in (default_db, mysql_db, mumble_psql_db, mumble_mysql_db):
            if not isinstance(candidate, dict):
                continue
            connector: dict[str, str] = {}
            sslrootcert = str(candidate.get("MONITOR_SSLROOTCERT") or "").strip()
            if sslrootcert:
                connector["ca"] = sslrootcert
            raw_ssl = (
                candidate.get("OPTIONS", {}).get("ssl")
                if isinstance(candidate.get("OPTIONS"), dict)
                else {}
            )
            if isinstance(raw_ssl, dict):
                for key in ("ca", "cert", "key"):
                    value = str(raw_ssl.get(key) or "").strip()
                    if value:
                        connector[key] = value
            if connector:
                legacy_db_ssl.append(connector)
        db_ssl_connectors = legacy_db_ssl
    janice_api_key = getattr(settings, "JANICE_API_KEY", None)

    print("# Python-style settings file for monitor grouped config.")
    print("# Add more EVE_APPS or MUMBLE_ICE entries if needed; see README.md.")
    print()
    print(f"ALLIANCE_ID = {_python_literal(getattr(settings, 'ALLIANCE_ID', None))}")
    print(
        f"ALLIANCE_TICKER = {_python_literal(getattr(settings, 'ALLIANCE_TICKER', None))}"
    )
    print()
    print("EVE_APPS = [")
    print("    {")
    print(f"        \"NAME_DB\": {_python_literal(eve_name)},")
    print(f"        \"USER\": {_python_literal(eve_user)},")
    print(
        f"        \"PASSWORD\": {_python_literal(_obfuscate_env_value('EVE_PASSWORD', _to_env_string(eve_password)))},"
    )
    print(f"        \"HOST\": {_python_literal(eve_host or '127.0.0.1')},")
    print(f"        \"DBPREFIX\": {_python_literal(eve_prefix)},")
    print("    },")
    print("]")
    print()
    print("DB_SSL = [")
    if db_ssl_connectors:
        for connector in db_ssl_connectors:
            print("    {")
            print(f"        \"ca\": {_python_literal(connector.get('ca', ''))},")
            print(f"        \"cert\": {_python_literal(connector.get('cert', ''))},")
            print(f"        \"key\": {_python_literal(connector.get('key', ''))},")
            print("    },")
    else:
        print("    {")
        print("        \"ca\": \"\",")
        print("        \"cert\": \"\",")
        print("        \"key\": \"\",")
        print("    },")
    print("]")
    print()
    print("MUMBLE_ICE = [")
    print("    {")
    print(
        f"        \"HOST\": {_python_literal(getattr(settings, 'ICE_HOST', '127.0.0.1'))},"
    )
    print(
        f"        \"PORT\": {_python_int_literal(getattr(settings, 'ICE_PORT', 6502), 6502)},"
    )
    print(
        f"        \"SECRET\": {_python_literal(_obfuscate_env_value('ICE_SECRET', _to_env_string(getattr(settings, 'ICE_SECRET', None))))},"
    )
    print(
        f"        \"INI_PATH\": {_python_literal(getattr(settings, 'ICE_INI_PATH', None))},"
    )
    print(
        f"        \"SERVER_ID\": {_python_int_literal(getattr(settings, 'PYMUMBLE_SERVER_ID', None), 1)},"
    )
    print("    },")
    print("]")
    print()
    print("MUMBLE_DB = {")
    print(f"    \"NAME_DB\": {_python_literal(mumble_db_name)},")
    print(f"    \"USER\": {_python_literal(mumble_db_user)},")
    print(
        f"    \"PASSWORD\": {_python_literal(_obfuscate_env_value('MUMBLE_DB_PASSWORD', _to_env_string(mumble_db_password)))},"
    )
    print(f"    \"HOST\": {_python_literal(mumble_db_host)},")
    print("}")
    print()
    print("PYMUMBLE = {")
    print(
        f"    \"SERVER\": {_python_literal(getattr(settings, 'PYMUMBLE_SERVER', '127.0.0.1'))},"
    )
    print(
        f"    \"PORT\": {_python_int_literal(getattr(settings, 'PYMUMBLE_PORT', 64738), 64738)},"
    )
    print(
        f"    \"USER\": {_python_literal(getattr(settings, 'PYMUMBLE_USER', None))},"
    )
    print(
        f"    \"PASSWD\": {_python_literal(_obfuscate_env_value('PYMUMBLE_PASSWD', _to_env_string(getattr(settings, 'PYMUMBLE_PASSWD', None))))},"
    )
    print(
        f"    \"CERT_FILE\": {_python_literal(getattr(settings, 'PYMUMBLE_CERT_FILE', None))},"
    )
    print(
        f"    \"KEY_FILE\": {_python_literal(getattr(settings, 'PYMUMBLE_KEY_FILE', None))},"
    )
    print(
        f"    \"SERVER_ID\": {_python_int_literal(getattr(settings, 'PYMUMBLE_SERVER_ID', None), 1)},"
    )
    print("}")
    print()
    print(f"LOG_LEVEL = {_python_literal(getattr(settings, 'LOG_LEVEL', 'INFO'))}")
    print(f"LOG_FILE = {_python_literal(getattr(settings, 'LOG_FILE', None))}")
    print()
    print(f"JANICE_API_KEY = {_python_literal(_obfuscate_env_value('JANICE_API_KEY', _to_env_string(janice_api_key)))}")
    print(f"JANICE_MARKET = {_python_int_literal(getattr(settings, 'JANICE_MARKET', '2'), 2)}")
    print(f"JANICE_PRICING = {_python_literal(getattr(settings, 'JANICE_PRICING', 'sell'))}")
    print(f"JANICE_VARIANT = {_python_literal(getattr(settings, 'JANICE_VARIANT', 'immediate'))}")
    print(f"JANICE_DAYS = {_python_int_literal(getattr(settings, 'JANICE_DAYS', '0'), 0)}")
    print()
    print(
        f"ITEM_PRICE_CACHE_BACKEND = {_python_literal(getattr(settings, 'ITEM_PRICE_CACHE_BACKEND', 'json'))}"
    )
    print(
        f"ITEM_PRICE_CACHE_FILE = {_python_literal(getattr(settings, 'ITEM_PRICE_CACHE_FILE', '/var/tmp/monitor-item-price-cache.json'))}"
    )
    print(
        f"ITEM_PRICE_CACHE_TTL_SECONDS = {_python_int_literal(getattr(settings, 'ITEM_PRICE_CACHE_TTL_SECONDS', 3600), 3600)}"
    )


def main() -> int:
    """
    Command-line entry point for the mumble monitor.

    Loads settings, configures logging, verifies connections, and runs a
    single sync iteration (or listing operation).
    """
    parser = argparse.ArgumentParser(description="Run the monitor utility.")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_monitor_version()}",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging for this run.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose verify output for this run.",
    )
    parser.add_argument(
        "--list-servers",
        action="store_true",
        help="List available Murmur server IDs from ICE Meta and exit.",
    )
    parser.add_argument(
        "--list-pilots-by-app",
        action="store_true",
        help="List main pilots grouped by detected app (AUTH/CUBE) and exit.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Return status monitor state and exit (0=running, 1=stopped).",
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="Stop the status monitor and exit.",
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Restart the status monitor.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify configured connections and exit.",
    )
    parser.add_argument(
        "--config",
        action="store_true",
        help="Print effective runtime configuration as export statements and exit.",
    )
    parser.add_argument(
        "--clear-market-cache",
        action="store_true",
        help="Clear cached item market prices before running.",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--fg",
        action="store_true",
        help="Run in foreground (default).",
    )
    mode_group.add_argument(
        "--bg",
        action="store_true",
        help="Run in background and exit.",
    )
    args = parser.parse_args()

    is_default_start = not any(
        (
            args.verify,
            args.list_servers,
            args.list_pilots_by_app,
            args.status,
            args.stop,
            args.restart,
            args.config,
        )
    )
    if is_default_start and args.bg and os.environ.get(_DAEMON_ENV) != "1":
        return _start_status_monitor_background()

    configure_django_from_local_settings()
    if args.debug:
        setattr(settings, "LOG_LEVEL", "DEBUG")
    configure_logging(fg=not args.bg)
    logger = logging.getLogger(__name__)

    if not django_apps.ready:
        django.setup()
        logger.debug("Django setup complete")

    if args.clear_market_cache:
        from .services.item_pricing import clear_item_price_caches

        configured_cache_file = str(
            getattr(
                settings,
                "ITEM_PRICE_CACHE_FILE",
                "/var/tmp/monitor-item-price-cache.json",
            )
        )
        clear_item_price_caches(cache_file=configured_cache_file)
        logger.info("Cleared item price cache: %s", configured_cache_file)

    if args.verify:
        try:
            verify_connections(verbose=(args.debug or args.verbose))
        except SystemExit:
            logger.error("Verification failed")
            return 1
        return 0
    if args.config:
        _print_effective_env_config()
        return 0

    if args.stop:
        if _stop_status_server():
            print("status monitor: stopped")
            return 0
        print("status monitor: failed to stop", file=sys.stderr)
        return 1
    if args.status:
        if _status_server_running():
            print("status monitor: running")
            snapshot = _request_live_status_snapshot()
            if snapshot and isinstance(snapshot.get("applications"), dict):
                apps = snapshot["applications"]
                auth = str(apps.get("AUTH", "unknown"))
                cube = str(apps.get("CUBE", "unknown"))
                ice = str(apps.get("ICE", "unknown"))
                print(f"AUTH: {auth}")
                print(f"CUBE: {cube}")
                print(f"ICE: {ice}")
            return 0
        print("status monitor: stopped")
        return 1
    if args.restart:
        if not _stop_status_server():
            logger.error("Failed to stop status server for restart")
            return 1

    if args.list_servers:
        bundled_ice = Path(__file__).resolve().parents[1] / "ice"
        if str(bundled_ice) not in sys.path:
            # Ensure bundled ICE bindings are importable as a fallback.
            sys.path.insert(0, str(bundled_ice))
        connections = resolve_ice_connections()
        selected = connections[0] if connections else {}
        server_id = normalize_server_id(selected.get("SERVER_ID", 1))
        ice = ICEClient(
            server_id=server_id,
            host=selected.get("HOST"),
            port=selected.get("PORT"),
            secret=selected.get("SECRET"),
            ini_path=selected.get("INI_PATH"),
        )
        try:
            try:
                Ice = importlib.import_module("Ice")
                MumbleServer = importlib.import_module("MumbleServer")
            except ModuleNotFoundError:
                importlib.invalidate_caches()
                try:
                    MumbleServer = importlib.import_module("MumbleServer")
                except ModuleNotFoundError:
                    MumbleServer = importlib.import_module("monitor.ice.MumbleServer")
                Ice = importlib.import_module("Ice")
            _ = Ice
            _ = MumbleServer
            meta = ice._meta
            if meta is None:
                ice._get_server()
                meta = ice._meta
            booted = meta.getBootedServers()
            all_servers = meta.getAllServers()
            logger.info("booted: %s", booted)
            logger.info("all: %s", all_servers)
        finally:
            ice.close()
        return 0
    if args.list_pilots_by_app:
        _list_mains_by_app()
        return 0
    if args.list_servers or args.list_pilots_by_app:
        return 0

    # Default: run the status server
    def _background_verify() -> None:
        try:
            verify_connections(verbose=(args.debug or args.verbose))
        except SystemExit:
            logger.error(
                "Startup verification failed; continuing to serve status page."
            )

    threading.Thread(target=_background_verify, daemon=True).start()

    from .services.status_server import main as status_main

    try:
        _write_status_pid()
        _install_status_signal_handler()
        _write_status_snapshot()
        status_main()
        return 0
    finally:
        _clear_status_pid()


def get_configured_alliance_ids() -> frozenset[int]:
    """
    Return configured alliance IDs as an immutable set of ints.
    Reads ALLIANCE_ID, which may be a single integer or a
    comma-separated list (e.g. "12345,67890") for future multi-
    alliance support. Returns empty frozenset if not set.
    """
    raw = getattr(settings, "ALLIANCE_ID", None)
    if raw is None:
        return frozenset()
    ids: set[int] = set()
    for part in str(raw).split(","):
        part = part.strip()
        try:
            ids.add(int(part))
        except ValueError:
            pass
    return frozenset(ids)


def _find_spies(
    mains_with_alts: list["EvePilot"],
    alliance_ids: frozenset[int],
) -> list["EvePilot"]:
    """
    Return mains whose own alliance is not in alliance_ids but who
    have at least one alt with an alliance in alliance_ids.
    """
    if not alliance_ids:
        return []
    return [
        m for m in mains_with_alts
        if m.alliance_id not in alliance_ids
        and any(
            a.alliance_id in alliance_ids
            for a in (m.alts or [])
        )
    ]


def _list_mains_by_app() -> None:
    """
    List mains and orphans grouped by alliance and corp.
    """
    logger = logging.getLogger(__name__)
    identifier = (
        getattr(settings, "ALLIANCE_ID", None)
        or getattr(settings, "ALLIANCE_TICKER", None)
    )
    by_app_mains: dict[str, list["EvePilot"]] = {}
    by_app_orphans: dict[str, list["EvePilot"]] = {}
    for alias in settings.DATABASES.keys():
        try:
            env = detect_environment(using=alias)
            repo = get_repository(env, using=alias)
            if identifier:
                alliance = repo.resolve_alliance(identifier)
                if alliance is None:
                    logger.debug(
                        "Skipping %s: alliance not found", alias
                    )
                    continue
                mains = list(
                    repo.list_mains(alliance_id=alliance.id)
                )
            else:
                mains = list(repo.list_mains())
            pilots = list(repo.list_pilots())
            mains_with_alts, orphan_alts = _attach_alts_to_mains(
                mains, pilots
            )
            by_app_mains.setdefault(env, []).extend(mains_with_alts)
            if orphan_alts:
                by_app_orphans.setdefault(env, []).extend(
                    orphan_alts
                )
        except (ImproperlyConfigured, OperationalError) as exc:
            logger.debug("Skipping %s: %s", alias, exc)
        except Exception as exc:
            logger.debug("Skipping %s: %s", alias, exc)

    envs = sorted(
        set(by_app_mains.keys()) | set(by_app_orphans.keys())
    )
    for env in envs:
        mains = by_app_mains.get(env, [])
        orphans = by_app_orphans.get(env, [])
        alliance_ids = get_configured_alliance_ids()
        spies = _find_spies(mains, alliance_ids)
        spy_ids = {m.character_id for m in spies}
        real_mains = [m for m in mains if m.character_id not in spy_ids]
        total_alts = (
            sum(len(p.alts or []) for p in real_mains) + len(orphans)
        )
        logger.info(
            "%s: %d mains, %d alts",
            env, len(real_mains), total_alts,
        )
        if spies:
            logger.info("  (Spies not listed: %d)", len(spies))
        for alliance_name, corp_groups in (
            _group_pilots_by_alliance_and_corp(real_mains)
        ):
            logger.info("  %s", alliance_name)
            for corp_name, corp_pilots in corp_groups:
                logger.info("    %s", corp_name)
                for pilot in sorted(
                    corp_pilots, key=lambda p: p.name.lower()
                ):
                    logger.info("      - %s", pilot.name)
                    for alt in sorted(
                        pilot.alts or [],
                        key=lambda p: p.name.lower(),
                    ):
                        logger.info(
                            "        - %s", alt.name
                        )
        if orphans:
            logger.info("  Orphans: %d", len(orphans))
            for alliance_name, corp_groups in (
                _group_pilots_by_alliance_and_corp(orphans)
            ):
                logger.info("  %s", alliance_name)
                for corp_name, corp_pilots in corp_groups:
                    logger.info("    %s", corp_name)
                    for pilot in sorted(
                        corp_pilots,
                        key=lambda p: p.name.lower(),
                    ):
                        logger.info("      %s", pilot.name)


def _group_pilots_by_alliance_and_corp(
    pilots: list["EvePilot"],
) -> list[tuple[str, list[tuple[str, list["EvePilot"]]]]]:
    grouped: dict[str, dict[str, list["EvePilot"]]] = {}
    for pilot in pilots:
        alliance_name = (pilot.alliance_name or "").strip() or "[]"
        corp_name = (pilot.corporation_name or "").strip() or "[]"
        grouped.setdefault(alliance_name, {}).setdefault(corp_name, []).append(
            pilot
        )
    out: list[tuple[str, list[tuple[str, list["EvePilot"]]]]] = []
    for alliance_name in sorted(
        grouped.keys(),
        key=lambda name: (name == "[]", name.lower()),
    ):
        corp_groups = grouped[alliance_name]
        corp_out = [
            (corp_name, corp_groups[corp_name])
            for corp_name in sorted(
                corp_groups.keys(),
                key=lambda name: (name == "[]", name.lower()),
            )
        ]
        out.append((alliance_name, corp_out))
    return out


def _attach_alts_to_mains(
    mains: list["EvePilot"], pilots: list["EvePilot"]
) -> tuple[list["EvePilot"], list["EvePilot"]]:
    mains_by_id: dict[int, EvePilot] = {
        pilot.character_id: pilot.with_alts([])
        for pilot in mains
    }
    mains_order = [pilot.character_id for pilot in mains]
    orphan_alts: list[EvePilot] = []
    if any(pilot.user_id is not None for pilot in pilots):
        grouped: dict[int, list[EvePilot]] = {}
        for pilot in pilots:
            if pilot.user_id is None:
                continue
            grouped.setdefault(pilot.user_id, []).append(pilot)
        for group_pilots in grouped.values():
            main = next(
                (p for p in group_pilots if p.is_main is True),
                None,
            )
            if main is None:
                main = next(
                    (
                        p
                        for p in group_pilots
                        if p.character_id in mains_by_id
                    ),
                    None,
                )
            if main is None:
                orphan_alts.extend(
                    [p for p in group_pilots if p.is_main is not True]
                )
                continue
            if main.character_id not in mains_by_id:
                mains_by_id[main.character_id] = main.with_alts([])
                mains_order.append(main.character_id)
            alts = [
                p
                for p in group_pilots
                if p.character_id != main.character_id
            ]
            mains_by_id[main.character_id] = mains_by_id[
                main.character_id
            ].with_alts(alts)
        # Pilots with no user_id have no AUTH account — not orphans.
    else:
        for pilot in pilots:
            if pilot.character_id in mains_by_id:
                continue
            if pilot.is_main is False or pilot.is_main is None:
                orphan_alts.append(pilot)
    mains_out = [mains_by_id[pilot_id] for pilot_id in mains_order]
    return mains_out, orphan_alts


def _run_monitor() -> None:
    """
    Instantiate Monitor and rely on its logging side effects.
    """
    import logging

    from .models.monitor import Monitor

    logger = logging.getLogger(__name__)
    for app_type in ("AUTH", "CUBE"):
        try:
            logger.info("Monitor test for app_type=%s", app_type)
            Monitor(app_type=app_type)
        except Exception as exc:
            logger.warning(
                "Monitor test failed for app_type=%s: %s",
                app_type,
                exc,
            )
