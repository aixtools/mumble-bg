#!/usr/bin/env python3
"""
Standalone ICE authenticator daemon for Mumble (multi-server).

Reads active MumbleServer configs from the database and connects to each
server's ICE endpoint, registering a scoped CubeAuthenticator per server.

Configuration via environment variables:
    CUBE_CORE_DATABASE_NAME, CUBE_CORE_DATABASE_HOST,
    CUBE_CORE_DATABASE_USER, CUBE_CORE_DATABASE_PASSWORD,
    optional CUBE_CORE_DATABASE_ENGINE (postgresql|mysql, default auto-detect)
"""

import os
import sys
import time
import logging
from datetime import datetime, timezone

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from bg.db import (
    DBAdapterObject,
    CubeCoreDBA,
    CubeDatabaseError,
    MmblBgDBA,
)
from bg.ice import load_ice_module
from bg.passwords import LEGACY_BCRYPT_SHA256, verify_murmur_password

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


class PilotIdentity:
    """
    Read-only cube-core pilot projection consumed by mumble-bg.

    Important: PKID does not bind to a fixed alliance.
    A pilot can only change corporation, and a corporation can change alliance,
    so alliance_id must be treated as part of the current membership snapshot.
    """

    __slots__ = (
        'character_id',
        'character_name',
        'corporation_id',
        'alliance_id',
        'corporation_name',
        'alliance_name',
        'corporation_ticker',
        'alliance_ticker',
    )

    def __init__(
        self,
        character_id,
        character_name,
        corporation_id,
        alliance_id,
        corporation_name='',
        alliance_name='',
        corporation_ticker='',
        alliance_ticker='',
    ):
        self.character_id = int(character_id) if character_id is not None else None
        self.character_name = character_name or ''
        self.corporation_id = int(corporation_id) if corporation_id is not None else None
        self.alliance_id = int(alliance_id) if alliance_id is not None else None
        self.corporation_name = (corporation_name or '').strip()
        self.alliance_name = (alliance_name or '').strip()
        self.corporation_ticker = corporation_ticker or ''
        self.alliance_ticker = alliance_ticker or ''

    def as_dict(self):
        """Return a plain-object payload for downstream adapters."""
        return {
            'character_id': self.character_id,
            'character_name': self.character_name,
            'corporation_id': self.corporation_id,
            'alliance_id': self.alliance_id,
            'corporation_name': self.corporation_name,
            'alliance_name': self.alliance_name,
            'corporation_ticker': self.corporation_ticker,
            'alliance_ticker': self.alliance_ticker,
        }

    def __iter__(self):
        return iter(self.as_dict().items())


CORE_DB_ADAPTER = CubeCoreDBA(
    DBAdapterObject(
        name=os.environ.get('CUBE_CORE_DATABASE_NAME', 'cube'),
        host=os.environ.get('CUBE_CORE_DATABASE_HOST', 'localhost'),
        user=os.environ.get('CUBE_CORE_DATABASE_USER', 'cube'),
        password=os.environ.get('CUBE_CORE_DATABASE_PASSWORD', ''),
        engine=os.environ.get('CUBE_CORE_DATABASE_ENGINE', ''),
    )
)

BG_DB_ADAPTER = MmblBgDBA(
    DBAdapterObject(
        name=os.environ.get('MMBL_BG_DATABASE_NAME', 'mumble'),
        host=os.environ.get('MMBL_BG_DATABASE_HOST', 'localhost'),
        user=os.environ.get('MMBL_BG_DATABASE_USER', 'cube'),
        password=os.environ.get('MMBL_BG_DATABASE_PASSWORD', ''),
        engine='',
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
        mu.mumble_userid,
        mu.pwhash,
        mu.hashfn,
        mu.pw_salt,
        mu.kdf_iterations,
        mu.certhash,
        mu.groups,
        mu.display_name
    FROM mumble_user mu
    WHERE LOWER(mu.username) = LOWER(%s) AND mu.is_active = true AND mu.server_id = %s
"""

NAME_TO_ID_QUERY = """
    SELECT COALESCE(mu.mumble_userid, mu.id)
    FROM mumble_user mu
    WHERE LOWER(mu.username) = LOWER(%s)
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

PILOT_IDENTITY_QUERY = """
    SELECT
        ec.character_id,
        ec.character_name,
        ec.corporation_id,
        ec.alliance_id,
        COALESCE(ec.corporation_name, '') AS corporation_name,
        COALESCE(ec.alliance_name, '') AS alliance_name,
        '' AS corporation_ticker,
        '' AS alliance_ticker
    FROM accounts_evecharacter ec
    WHERE ec.pending_delete = false
      AND ec.is_main = true
"""

MUMBLE_PILOT_IDENTITY_SOURCE = "cube-core/mumble-bg adapter contract"


def list_cube_pilot_identities():
    """
    Return read-only pilot identities from cube-core for mumble-bg orchestration.

    Returns a list of PilotIdentity objects.
    """
    try:
        conn = get_core_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(PILOT_IDENTITY_QUERY)
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
        PilotIdentity(
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


def get_core_db_connection():
    try:
        return CORE_DB_ADAPTER.connect()
    except Exception as exc:
        raise CubeDatabaseError('Could not connect to cube-core read DB') from exc


def get_db_connection():
    try:
        return BG_DB_ADAPTER.connect()
    except Exception as exc:
        raise CubeDatabaseError('Could not connect to mumble-bg DB') from exc


def get_active_servers():
    """Fetch all active MumbleServer configs from the database."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(SERVERS_QUERY)
            except Exception as exc:
                if not _is_missing_virtual_server_id_column(exc):
                    raise
                logger.warning(
                    'mumble_server.virtual_server_id is missing; '
                    'falling back to legacy compatibility mode with default virtual_server_id=1'
                )
                cur.execute(LEGACY_SERVERS_QUERY)
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
        'Multiple Murmur virtual servers are booted on this ICE endpoint; configure virtual_server_id in Cube'
    )


# Sentinel returned by authenticate() when the user has no record in the cube
# DB.  Distinct from None, which means the user exists but the password failed.
_USER_NOT_FOUND = object()


def authenticate(username, password, server_id, certhash=''):
    """
    Authenticate a user against the database for a specific server.

    Returns (cube_row_id, auth_user_id, display_name, groups) or None.
    """
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(AUTH_QUERY, (username, server_id))
                row = cur.fetchone()
        finally:
            conn.close()
    except Exception:
        logger.exception('Database error during authentication')
        return None

    if row is None:
        return _USER_NOT_FOUND

    cube_row_id, mumble_userid, pwhash, hashfn, pw_salt, kdf_iterations, stored_certhash, groups, display_name = row
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
        if not password_ok and hashfn == LEGACY_BCRYPT_SHA256:
            logger.warning(
                'Legacy bcrypt Mumble password no longer supported for user %s on server_id=%s; password reset required',
                username,
                server_id,
            )

    cert_ok = bool(stored_certhash and certhash and stored_certhash == certhash)

    if not password_ok and not cert_ok:
        return None

    group_list = [g for g in groups.split(',') if g] if groups else []
    auth_user_id = mumble_userid if mumble_userid is not None else cube_row_id
    if mumble_userid is None:
        logger.warning(
            'User %s on server_id=%s is missing mumble_userid; returning Cube row id temporarily',
            username,
            server_id,
        )
    return cube_row_id, auth_user_id, display_name or username, group_list


def authenticate_user(username, password, server_id, certhash):
    return authenticate(username, password, server_id, certhash=certhash or '')


def name_to_id(name, server_id):
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(NAME_TO_ID_QUERY, (name, server_id))
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
            with conn.cursor() as cur:
                cur.execute(ID_TO_NAME_QUERY, (server_id, user_id, user_id))
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


def update_connection_info(cube_row_id, certhash):
    """Store the client certificate hash and last successful auth time."""
    now = datetime.now(timezone.utc)
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(UPDATE_CONNECTION_QUERY, (certhash or '', now, now, cube_row_id))
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.exception('Failed to update connection info for cube_row_id=%s', cube_row_id)


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

    RETRY_INTERVAL = 30
    server_configs = get_active_servers()
    while not server_configs:
        logger.warning('No active MumbleServer configs found in database. Retrying in %ds...', RETRY_INTERVAL)
        time.sleep(RETRY_INTERVAL)
        server_configs = get_active_servers()

    with Ice.initialize(['--Ice.ImplicitContext=Shared', '--Ice.Default.EncodingVersion=1.0']) as communicator:
        adapter = communicator.createObjectAdapterWithEndpoints(
            'CubeAuth', 'tcp -h 0.0.0.0'
        )
        adapter.activate()

        registered = 0
        for server_id, ice_host, ice_port, ice_secret, virtual_server_id in server_configs:
            try:
                # Create a scoped authenticator for this server
                class ScopedAuthenticator(M.ServerAuthenticator):
                    def __init__(self, sid):
                        self._server_id = sid

                    def authenticate(self, name, pw, certificates, certhash, certstrong, current=None):
                        result = authenticate_user(name, pw or '', self._server_id, certhash or '')
                        if result is _USER_NOT_FOUND:
                            # Not in cube DB -- fall through to murmur local
                            # auth (cert hash or PBKDF2 password).
                            return (-2, None, None)
                        if result is None:
                            # Known user, wrong password -- hard reject.
                            return (-1, None, None)
                        cube_row_id, auth_user_id, display_name, groups = result
                        update_connection_info(cube_row_id, certhash)
                        return (auth_user_id, display_name, groups)

                    def getInfo(self, id, current=None):
                        return (False, {})

                    def nameToId(self, name, current=None):
                        return name_to_id(name, self._server_id)

                    def idToName(self, id, current=None):
                        return id_to_name(id, self._server_id)

                    def idToTexture(self, id, current=None):
                        return bytes()

                # Connect to this server's ICE endpoint
                if ice_secret:
                    communicator.getImplicitContext().put('secret', ice_secret)

                proxy = communicator.stringToProxy(
                    f'Meta:tcp -h {ice_host} -p {ice_port}'
                )
                meta = M.MetaPrx.checkedCast(proxy)
                if not meta:
                    logger.error('Failed to connect to ICE on %s:%s (server_id=%d)', ice_host, ice_port, server_id)
                    continue

                servers = meta.getBootedServers()
                if not servers:
                    logger.warning('No booted Mumble servers found on %s:%s (server_id=%d)', ice_host, ice_port, server_id)
                    continue

                auth_obj = ScopedAuthenticator(server_id)
                auth_proxy = adapter.addWithUUID(auth_obj)

                target_servers = select_target_servers(servers, virtual_server_id)

                for srv in target_servers:
                    srv.setAuthenticator(
                        M.ServerAuthenticatorPrx.uncheckedCast(auth_proxy)
                    )
                    logger.info('Authenticator registered for mumble server %d on %s:%s (db server_id=%d)',
                                srv.id(), ice_host, ice_port, server_id)
                    registered += 1

            except Exception:
                logger.exception('Error setting up authenticator for server_id=%d (%s:%s)', server_id, ice_host, ice_port)

        if registered == 0:
            logger.error('No authenticators were registered. Exiting.')
            sys.exit(1)

        logger.info('mumble-bg authd running (%d server(s)). Press Ctrl+C to stop.', registered)
        communicator.waitForShutdown()


if __name__ == '__main__':
    main()
