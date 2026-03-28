#!/usr/bin/env python3
"""
Standalone ICE authenticator daemon for Mumble (multi-server).

Reads active MumbleServer configs from the database and connects to each
server's ICE endpoint, registering a scoped authenticator per server.

Configuration via environment variables:
    BG_DBMS (flat JSON DB object; legacy DATABASES values are still accepted)
"""

import os
import sys
import time
import logging
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from bg.contracts import PilotIdentity

from bg.db import (
    PilotDBError,
    MmblBgDBA,
    db_config_from_env,
)
from bg.ice_inventory import sync_ice_inventory_from_env
from bg.ice import load_ice_module
from bg.ice_meta import build_ice_client_props, connect_meta_with_fallback
from bg.passwords import verify_murmur_password

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


BG_DB_ADAPTER = MmblBgDBA(
    db_config_from_env(
        'BG_DBMS',
        'bg',
        default_database='mumble',
        default_host='localhost',
        default_username='cube',
        legacy_env_var='DATABASES',
    )
)

SERVERS_QUERY = """
    SELECT id, ice_host, ice_port, ice_secret, virtual_server_id
    FROM mumble_server
    WHERE is_active = true
"""

LEGACY_SERVERS_QUERY = """
    SELECT id, ice_host, ice_port, ice_secret, 1 AS virtual_server_id
    FROM mumble_server
    WHERE is_active = true
"""

AUTH_QUERY = """
    SELECT
        mu.id,
        mu.user_id,
        mu.mumble_userid,
        mu.pwhash,
        mu.hashfn,
        mu.pw_salt,
        mu.kdf_iterations,
        mu.certhash,
        mu.groups,
        mu.display_name
    FROM mumble_user mu
    WHERE (
        LOWER(mu.username) = LOWER(%s)
        OR LOWER(mu.display_name) = LOWER(%s)
    )
      AND mu.is_active = true
      AND mu.server_id = %s
"""

NAME_TO_ID_QUERY = """
    SELECT COALESCE(mu.mumble_userid, mu.id)
    FROM mumble_user mu
    WHERE (
        LOWER(mu.username) = LOWER(%s)
        OR LOWER(mu.display_name) = LOWER(%s)
    )
      AND mu.is_active = true
      AND mu.server_id = %s
"""

LEGACY_AUTH_QUERY = """
    SELECT
        mu.id,
        mu.user_id,
        mu.mumble_userid,
        mu.pwhash,
        mu.hashfn,
        mu.pw_salt,
        mu.kdf_iterations,
        mu.certhash,
        mu.groups,
        mu.display_name
    FROM mumble_user mu
    JOIN bg_pilot_account pa
      ON pa.pkid = mu.user_id
    WHERE LOWER(pa.account_username) = LOWER(%s)
      AND mu.is_active = true
      AND mu.server_id = %s
"""

LEGACY_NAME_TO_ID_QUERY = """
    SELECT COALESCE(mu.mumble_userid, mu.id)
    FROM mumble_user mu
    JOIN bg_pilot_account pa
      ON pa.pkid = mu.user_id
    WHERE LOWER(pa.account_username) = LOWER(%s)
      AND mu.is_active = true
      AND mu.server_id = %s
"""

ID_TO_NAME_QUERY = """
    SELECT mu.username
    FROM mumble_user mu
    WHERE mu.server_id = %s
      AND (
        mu.mumble_userid = %s
        OR (mu.mumble_userid IS NULL AND mu.id = %s)
      )
      AND mu.is_active = true
"""

SERVER_NAME_QUERY = """
    SELECT name
    FROM mumble_server
    WHERE id = %s
"""

PILOT_IDENTITY_QUERY = """
    SELECT
        pc.character_id,
        pc.character_name,
        pc.corporation_id,
        pc.alliance_id,
        COALESCE(pc.corporation_name, '') AS corporation_name,
        COALESCE(pc.alliance_name, '') AS alliance_name,
        '' AS corporation_ticker,
        '' AS alliance_ticker
    FROM bg_pilot_character pc
    JOIN bg_pilot_account pa ON pa.id = pc.account_id
    WHERE pc.is_main = true
    ORDER BY pa.pkid, pc.character_name
"""

MUMBLE_PILOT_IDENTITY_SOURCE = "bg cached pilot snapshot contract"


def list_pilot_identities():
    """
    Return read-only pilot identities from BG's cached pilot snapshot.

    Returns a list of PilotIdentity objects.
    """
    try:
        conn = get_db_connection()
        try:
            with _cursor(conn) as cur:
                _execute(cur, conn, PILOT_IDENTITY_QUERY)
                rows = cur.fetchall()
        finally:
            conn.close()
    except Exception:
        logger.exception(
            'Database error fetching pilot identities for source=%s',
            MUMBLE_PILOT_IDENTITY_SOURCE,
        )
        return []

    return [
        PilotIdentity.from_record(
            'allianceauth',
            character_id=row[0],
            character_name=row[1],
            corporation_id=row[2],
            alliance_id=row[3],
            corporation_name=row[4] or '',
            alliance_name=row[5] or '',
            corporation_ticker=row[6] or '',
            alliance_ticker=row[7] or '',
        )
        for row in rows
    ]


def _is_sqlite_connection(conn):
    return isinstance(conn, sqlite3.Connection)


def _adapt_query_for_connection(conn, query):
    if _is_sqlite_connection(conn):
        return query.replace('%s', '?')
    return query


def _execute(cur, conn, query, params=()):
    cur.execute(_adapt_query_for_connection(conn, query), params)


@contextmanager
def _cursor(conn):
    cur = conn.cursor()
    try:
        yield cur
    finally:
        try:
            cur.close()
        except Exception:
            pass


def get_db_connection():
    sqlite_path = (os.environ.get('BG_USE_SQLITE') or '').strip()
    if sqlite_path:
        return sqlite3.connect(sqlite_path)
    try:
        return BG_DB_ADAPTER.connect()
    except Exception as exc:
        raise PilotDBError('Could not connect to mumble-bg DB') from exc


def get_active_servers():
    """Fetch all active MumbleServer configs from the database."""
    conn = get_db_connection()
    try:
        with _cursor(conn) as cur:
            try:
                _execute(cur, conn, SERVERS_QUERY)
            except Exception as exc:
                if not _is_missing_virtual_server_id_column(exc):
                    raise
                logger.warning(
                    'mumble_server.virtual_server_id is missing; '
                    'falling back to legacy compatibility mode with default virtual_server_id=1'
                )
                _execute(cur, conn, LEGACY_SERVERS_QUERY)
            return cur.fetchall()
    finally:
        conn.close()


def _is_missing_virtual_server_id_column(exc):
    message = str(exc).lower()
    if 'virtual_server_id' not in message:
        return False
    return (
        'does not exist' in message
        or 'unknown column' in message
        or getattr(exc, 'pgcode', None) == '42703'
    )


def select_target_servers(booted_servers, virtual_server_id):
    if virtual_server_id is not None:
        matched = [srv for srv in booted_servers if srv.id() == virtual_server_id]
        if not matched:
            raise ValueError(f'Configured virtual server ID {virtual_server_id} was not found')
        return matched
    if len(booted_servers) == 1:
        return booted_servers
    raise ValueError(
        'Multiple Murmur virtual servers are booted on this ICE endpoint; configure virtual_server_id in bg inventory'
    )


# Sentinel returned by authenticate() when the user has no record in the cube
# DB.  Distinct from None, which means the user exists but the password failed.
_USER_NOT_FOUND = object()


def authenticate(username, password, server_id, certhash=''):
    """
    Authenticate a user against the database for a specific server.

    Returns (bg_row_id, auth_user_id, display_name, groups, pilot_user_id, auth_method) or None.
    """
    if os.environ.get('BG_AUTHD_ALWAYS_PASS_THROUGH', '').strip() == '1':
        return _USER_NOT_FOUND

    try:
        conn = get_db_connection()
        try:
            with _cursor(conn) as cur:
                _execute(cur, conn, AUTH_QUERY, (username, username, server_id))
                row = cur.fetchone()
                if row is None:
                    _execute(cur, conn, LEGACY_AUTH_QUERY, (username, server_id))
                    row = cur.fetchone()
        finally:
            conn.close()
    except Exception:
        logger.exception('Database error during authentication')
        return None

    if row is None:
        return _USER_NOT_FOUND

    bg_row_id, pilot_user_id, mumble_userid, pwhash, hashfn, pw_salt, kdf_iterations, stored_certhash, groups, display_name = row
    password_ok = False

    if password:
        try:
            password_ok = verify_murmur_password(
                password,
                pwhash=pwhash,
                hashfn=hashfn,
                pw_salt=pw_salt or '',
                kdf_iterations=kdf_iterations,
            )
        except Exception:
            logger.exception('Hash verification error for user %s', username)
            return None
    cert_ok = bool(stored_certhash and certhash and stored_certhash == certhash)

    if not password_ok and not cert_ok:
        return None

    group_list = [g for g in groups.split(',') if g] if groups else []
    auth_user_id = mumble_userid if mumble_userid is not None else bg_row_id
    if password_ok and cert_ok:
        auth_method = 'password+cert'
    elif password_ok:
        auth_method = 'password'
    else:
        auth_method = 'cert'
    if mumble_userid is None:
        logger.warning(
            'User %s on server_id=%s is missing mumble_userid; returning local row id temporarily',
            username,
            server_id,
        )
    return bg_row_id, auth_user_id, display_name or username, group_list, pilot_user_id, auth_method


def authenticate_user(username, password, server_id, certhash):
    return authenticate(username, password, server_id, certhash=certhash or '')


def name_to_id(name, server_id):
    try:
        conn = get_db_connection()
        try:
            with _cursor(conn) as cur:
                _execute(cur, conn, NAME_TO_ID_QUERY, (name, name, server_id))
                row = cur.fetchone()
                if row is None:
                    _execute(cur, conn, LEGACY_NAME_TO_ID_QUERY, (name, server_id))
                    row = cur.fetchone()
        finally:
            conn.close()
    except Exception:
        logger.exception('Database error during nameToId for user %s', name)
        return -2
    if row is None:
        return -2
    return row[0]


def id_to_name(user_id, server_id):
    try:
        conn = get_db_connection()
        try:
            with _cursor(conn) as cur:
                _execute(cur, conn, ID_TO_NAME_QUERY, (server_id, user_id, user_id))
                row = cur.fetchone()
        finally:
            conn.close()
    except Exception:
        logger.exception('Database error during idToName for id=%s', user_id)
        return ''
    if row is None:
        return ''
    return row[0]


UPDATE_CONNECTION_QUERY = """
    UPDATE mumble_user
    SET certhash = %s, last_authenticated = %s, updated_at = %s
    WHERE id = %s
"""

UPDATE_MUMBLE_USERID_QUERY = """
    UPDATE mumble_user
    SET mumble_userid = %s, updated_at = %s
    WHERE id = %s AND mumble_userid IS NULL
"""

INSERT_AUDIT_QUERY = """
    INSERT INTO bg_audit (action, request_id, requested_by, source, user_id, server_name, metadata, occurred_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
"""

BG_AUDIT_ACTION_PILOT_LOGIN = "pilot_login"


def _schedule_deferred_provision(bg_row_id, username, display_name, M, srv):
    """Schedule Murmur registration in a background thread to avoid ICE callback deadlock."""
    import threading
    t = threading.Thread(
        target=_provision_murmur_registration,
        args=(bg_row_id, username, display_name, M, srv),
        daemon=True,
    )
    t.start()


def _provision_murmur_registration(bg_row_id, username, display_name, M, srv):
    """Register the user in Murmur via ICE and store the mumble_userid in BG."""
    try:
        info = {M.UserInfo.UserName: username}
        if display_name:
            info[M.UserInfo.UserComment] = display_name
        mumble_userid = srv.registerUser(info)
        if mumble_userid is not None and mumble_userid >= 0:
            now = datetime.now(timezone.utc)
            conn = get_db_connection()
            try:
                with _cursor(conn) as cur:
                    _execute(cur, conn, UPDATE_MUMBLE_USERID_QUERY, (mumble_userid, now, bg_row_id))
                conn.commit()
            finally:
                conn.close()
            logger.info('Provisioned Murmur registration for %s: mumble_userid=%d', username, mumble_userid)
            return mumble_userid
    except Exception:
        logger.exception('Failed to provision Murmur registration for %s (bg_row_id=%s)', username, bg_row_id)
    return None


def update_connection_info(bg_row_id, certhash):
    """Store the client certificate hash and last successful auth time."""
    now = datetime.now(timezone.utc)
    try:
        conn = get_db_connection()
        try:
            with _cursor(conn) as cur:
                _execute(cur, conn, UPDATE_CONNECTION_QUERY, (certhash or '', now, now, bg_row_id))
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.exception('Failed to update connection info for bg_row_id=%s', bg_row_id)


def _server_name(server_id):
    try:
        conn = get_db_connection()
        try:
            with _cursor(conn) as cur:
                _execute(cur, conn, SERVER_NAME_QUERY, (server_id,))
                row = cur.fetchone()
        finally:
            conn.close()
    except Exception:
        logger.exception('Failed to resolve server name for server_id=%s', server_id)
        return f'server-{server_id}'
    if not row:
        return f'server-{server_id}'
    return str(row[0] or f'server-{server_id}')


def append_auth_success_audit(*, user_id, server_id, username, auth_method, certhash):
    now = datetime.now(timezone.utc)
    metadata = {
        'status': 'completed',
        'username': str(username or ''),
        'auth_method': str(auth_method or ''),
        'certhash_present': bool(certhash),
    }
    request_id = now.strftime('%Y%m%dT%H%M%SZ')
    try:
        conn = get_db_connection()
        try:
            with _cursor(conn) as cur:
                _execute(
                    cur,
                    conn,
                    INSERT_AUDIT_QUERY,
                    (
                        BG_AUDIT_ACTION_PILOT_LOGIN,
                        request_id,
                        'authd',
                        'authd_ice',
                        int(user_id) if user_id is not None else None,
                        _server_name(server_id),
                        json.dumps(metadata),
                        now,
                    ),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.exception('Failed to append auth success audit for user_id=%s server_id=%s', user_id, server_id)


def wait_for_server_configs(retry_interval=30):
    """
    Wait until mumble-fg or another provisioning path creates active bg server configs.

    This keeps authd non-fatal while bg runtime tables exist but have not yet been
    populated with the server inventory it needs to attach to Murmur over ICE.
    """
    try:
        server_configs = get_active_servers()
    except Exception as exc:  # noqa: BLE001
        result['errors'].append({'error': f'Failed to load active server configs: {exc}'})
        return result
    while not server_configs:
        logger.info(
            'No active MumbleServer configs found; waiting for mumble-fg or provisioning '
            'to populate mumble_server. Retrying in %ds...',
            retry_interval,
        )
        time.sleep(retry_interval)
        server_configs = get_active_servers()
    return server_configs


def probe_authenticator_registration():
    """Attempt authenticator registration once and return structured results.

    This verifies the same registration path used by authd (including ICE secret
    validity) without entering the long-running wait loop.
    """
    result = {
        'registered': 0,
        'errors': [],
    }
    try:
        import Ice
    except ImportError as exc:
        result['errors'].append({'error': f'ZeroC ICE is not installed: {exc}'})
        return result

    try:
        M = load_ice_module()
    except Exception as exc:  # noqa: BLE001
        result['errors'].append({'error': f'Failed to load bundled ICE slice: {exc}'})
        return result

    try:
        sync_ice_inventory_from_env(additive=True, dry_run=False)
    except Exception:
        logger.exception('Failed to sync ICE env inventory during authd probe')

    server_configs = get_active_servers()
    if not server_configs:
        result['errors'].append({'error': 'No active MumbleServer configs found'})
        return result

    with Ice.initialize(build_ice_client_props()) as communicator:
        adapter = communicator.createObjectAdapterWithEndpoints('MumbleBgAuthProbe', 'tcp -h 0.0.0.0')
        adapter.activate()

        for server_id, ice_host, ice_port, ice_secret, virtual_server_id in server_configs:
            try:
                class ProbeAuthenticator(M.ServerAuthenticator):
                    def authenticate(self, name, pw, certificates, certhash, certstrong, current=None):
                        return (-2, None, None)

                    def getInfo(self, id, current=None):
                        return (False, {})

                    def nameToId(self, name, current=None):
                        return -2

                    def idToName(self, id, current=None):
                        return ''

                    def idToTexture(self, id, current=None):
                        return bytes()

                meta, _protocol, _attempts = connect_meta_with_fallback(
                    communicator,
                    M,
                    host=ice_host,
                    port=ice_port,
                    secret=ice_secret or '',
                )

                servers = meta.getBootedServers()
                if not servers:
                    result['errors'].append(
                        {
                            'server_id': int(server_id),
                            'endpoint': f'{ice_host}:{ice_port}',
                            'error': 'No booted Murmur servers found',
                        }
                    )
                    continue

                auth_obj = ProbeAuthenticator()
                auth_proxy = adapter.addWithUUID(auth_obj)
                target_servers = select_target_servers(servers, virtual_server_id)
                for srv in target_servers:
                    if ice_secret:
                        srv = srv.ice_context({"secret": ice_secret})
                    srv.setAuthenticator(M.ServerAuthenticatorPrx.uncheckedCast(auth_proxy))
                    result['registered'] += 1
            except Exception as exc:  # noqa: BLE001
                result['errors'].append(
                    {
                        'server_id': int(server_id),
                        'endpoint': f'{ice_host}:{ice_port}',
                        'error': str(exc),
                    }
                )

    return result


def _make_scoped_authenticator(M):
    """Build the ScopedAuthenticator class once, bound to the loaded ICE module."""

    class ScopedAuthenticator(M.ServerAuthenticator):
        def __init__(self, sid, ice_module, server_proxy):
            self._server_id = sid
            self._M = ice_module
            self._srv = server_proxy

        def authenticate(self, name, pw, certificates, certhash, certstrong, current=None):
            result = authenticate_user(name, pw or '', self._server_id, certhash or '')
            if result is _USER_NOT_FOUND:
                return (-2, None, None)
            if result is None:
                return (-1, None, None)
            bg_row_id, auth_user_id, display_name, groups, pilot_user_id, auth_method = result
            if auth_user_id == bg_row_id:
                _schedule_deferred_provision(bg_row_id, name, display_name, self._M, self._srv)
            update_connection_info(bg_row_id, certhash)
            append_auth_success_audit(
                user_id=pilot_user_id,
                server_id=self._server_id,
                username=name,
                auth_method=auth_method,
                certhash=certhash,
            )
            return (auth_user_id, display_name, groups)

        def getInfo(self, id, current=None):
            return (False, {})

        def nameToId(self, name, current=None):
            return name_to_id(name, self._server_id)

        def idToName(self, id, current=None):
            return id_to_name(id, self._server_id)

        def idToTexture(self, id, current=None):
            return bytes()

    return ScopedAuthenticator


def _register_authenticator(communicator, adapter, M, ScopedAuthenticator, *,
                            server_id, ice_host, ice_port, ice_secret, virtual_server_id):
    """Connect to a Murmur server and register a scoped authenticator.

    Returns the server proxy on success so the caller can health-check it later.
    """
    meta, _protocol, _attempts = connect_meta_with_fallback(
        communicator, M, host=ice_host, port=ice_port, secret=ice_secret or '',
    )
    servers = meta.getBootedServers()
    if not servers:
        raise RuntimeError(f'No booted Murmur servers on {ice_host}:{ice_port}')

    if ice_host not in ('127.0.0.1', 'localhost', '::1'):
        from bg.ice_meta import rewrite_proxy_host
        servers = [rewrite_proxy_host(communicator, s, ice_host, ice_port) for s in servers]

    target_servers = select_target_servers(servers, virtual_server_id)
    registered_proxies = []
    for srv in target_servers:
        if ice_secret:
            srv = srv.ice_context({"secret": ice_secret})
        auth_obj = ScopedAuthenticator(server_id, M, srv)
        auth_proxy = adapter.addWithUUID(auth_obj)
        srv.setAuthenticator(M.ServerAuthenticatorPrx.uncheckedCast(auth_proxy))
        logger.info('Authenticator registered for mumble server %d on %s:%s (db server_id=%d)',
                    srv.id(), ice_host, ice_port, server_id)
        registered_proxies.append(srv)
    return registered_proxies


def main():
    """Start the ICE authenticator daemon."""
    try:
        import Ice
    except ImportError:
        logger.error('ZeroC ICE is not installed. Install with: pip install zeroc-ice')
        sys.exit(1)

    try:
        M = load_ice_module()
    except Exception:
        logger.exception('Failed to load bundled ICE slice definition')
        sys.exit(1)

    try:
        sync_result = sync_ice_inventory_from_env(additive=True, dry_run=False)
        if sync_result.get('env_entries', 0):
            logger.info(
                'ICE env sync completed (created=%d updated=%d unchanged=%d disabled=%d)',
                int(sync_result.get('created', 0)),
                int(sync_result.get('updated', 0)),
                int(sync_result.get('unchanged', 0)),
                int(sync_result.get('disabled', 0)),
            )
    except Exception:
        logger.exception('Failed to sync ICE env inventory into mumble_server; continuing with existing DB rows')

    server_configs = wait_for_server_configs(retry_interval=30)
    ScopedAuthenticator = _make_scoped_authenticator(M)

    callback_endpoint = os.environ.get('BG_AUTHD_CALLBACK_ENDPOINT', 'tcp -h 0.0.0.0').strip()
    health_check_interval = int(os.environ.get('BG_AUTHD_HEALTH_INTERVAL', '60'))

    with Ice.initialize(build_ice_client_props()) as communicator:
        adapter = communicator.createObjectAdapterWithEndpoints(
            'MumbleBgAuth', callback_endpoint
        )
        adapter.activate()

        # Initial registration — maps server_id to (config, [server_proxies])
        live_servers: dict[int, tuple[tuple, list]] = {}
        for config in server_configs:
            server_id, ice_host, ice_port, ice_secret, virtual_server_id = config
            try:
                proxies = _register_authenticator(
                    communicator, adapter, M, ScopedAuthenticator,
                    server_id=server_id, ice_host=ice_host, ice_port=ice_port,
                    ice_secret=ice_secret, virtual_server_id=virtual_server_id,
                )
                live_servers[server_id] = (config, proxies)
            except Exception:
                logger.exception('Error setting up authenticator for server_id=%d (%s:%s)', server_id, ice_host, ice_port)

        if not live_servers:
            logger.error('No authenticators were registered. Exiting.')
            sys.exit(1)

        logger.info('mumble-bg authd running (%d server(s)). Health check every %ds.',
                    len(live_servers), health_check_interval)

        # Health-check loop: verify connections, re-register on failure.
        while True:
            time.sleep(health_check_interval)
            for server_id, (config, proxies) in list(live_servers.items()):
                _, ice_host, ice_port, ice_secret, virtual_server_id = config
                for proxy in proxies:
                    try:
                        proxy.ice_invocationTimeout(5000).id()
                    except Exception:
                        logger.warning('Health check failed for server_id=%d (%s:%s), re-registering...',
                                      server_id, ice_host, ice_port)
                        try:
                            new_proxies = _register_authenticator(
                                communicator, adapter, M, ScopedAuthenticator,
                                server_id=server_id, ice_host=ice_host, ice_port=ice_port,
                                ice_secret=ice_secret, virtual_server_id=virtual_server_id,
                            )
                            live_servers[server_id] = (config, new_proxies)
                        except Exception:
                            logger.exception('Re-registration failed for server_id=%d (%s:%s)',
                                           server_id, ice_host, ice_port)
                        break  # Don't check remaining proxies for this server


if __name__ == '__main__':
    main()
