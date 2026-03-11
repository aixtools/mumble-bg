from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import ipaddress
import logging
import time

from django.db import transaction
from django.utils import timezone

from bg.state.ice_sync import _load_slice
from bg.state.models import MumbleServer, MumbleSession, MumbleUser

logger = logging.getLogger(__name__)


class MurmurPulseError(RuntimeError):
    pass


@dataclass(frozen=True)
class PulseUserState:
    session_id: int
    mumble_userid: int | None
    username: str
    channel_id: int | None
    address: str
    cert_hash: str
    tcponly: bool
    mute: bool
    deaf: bool
    suppress: bool
    priority_speaker: bool
    self_mute: bool
    self_deaf: bool
    recording: bool
    onlinesecs: int
    idlesecs: int


def _read_attr(obj, key, default=None):
    value = getattr(obj, key, None)
    if value is not None:
        return value
    if hasattr(obj, 'get'):
        try:
            return obj.get(key, default)
        except Exception:
            return default
    return default


def _coerce_int(value, default=None):
    if value in (None, ''):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_bool(value):
    return bool(value)


def _format_address(value):
    if not value:
        return ''
    if isinstance(value, str):
        return value
    try:
        packed = bytes(value)
    except TypeError:
        return str(value)
    try:
        return str(ipaddress.ip_address(packed))
    except ValueError:
        return packed.hex()


def _normalize_user_state(state):
    session_id = _coerce_int(_read_attr(state, 'session'), default=0) or 0
    mumble_userid = _coerce_int(_read_attr(state, 'userid'))
    if mumble_userid is not None and mumble_userid < 0:
        mumble_userid = None
    return PulseUserState(
        session_id=session_id,
        mumble_userid=mumble_userid,
        username=str(_read_attr(state, 'name', '') or ''),
        channel_id=_coerce_int(_read_attr(state, 'channel')),
        address=_format_address(_read_attr(state, 'address', '')),
        cert_hash=str(_read_attr(state, 'hash', '') or _read_attr(state, 'certhash', '') or ''),
        tcponly=_coerce_bool(_read_attr(state, 'tcponly', False)),
        mute=_coerce_bool(_read_attr(state, 'mute', False)),
        deaf=_coerce_bool(_read_attr(state, 'deaf', False)),
        suppress=_coerce_bool(_read_attr(state, 'suppress', False)),
        priority_speaker=_coerce_bool(_read_attr(state, 'prioritySpeaker', False)),
        self_mute=_coerce_bool(_read_attr(state, 'selfMute', False)),
        self_deaf=_coerce_bool(_read_attr(state, 'selfDeaf', False)),
        recording=_coerce_bool(_read_attr(state, 'recording', False)),
        onlinesecs=max(_coerce_int(_read_attr(state, 'onlinesecs'), default=0) or 0, 0),
        idlesecs=max(_coerce_int(_read_attr(state, 'idlesecs'), default=0) or 0, 0),
    )


def _derive_connected_at(observed_at, onlinesecs):
    if not onlinesecs:
        return observed_at
    return observed_at - timedelta(seconds=max(onlinesecs, 0))


def _derive_last_spoke_at(observed_at, idlesecs):
    if idlesecs is None:
        return None
    return observed_at - timedelta(seconds=max(idlesecs, 0))


def _resolve_mumble_user(server, state):
    qs = MumbleUser.objects.filter(server=server, is_active=True)
    if state.mumble_userid is not None:
        match = qs.filter(mumble_userid=state.mumble_userid).first()
        if match is not None:
            return match
    if state.username:
        return qs.filter(username__iexact=state.username).first()
    return None


def _apply_user_presence(mumble_user, *, authenticated_at=None, connected_at=None, disconnected_at=None, seen_at=None, spoke_at=None):
    if mumble_user is None:
        return

    updates = []
    if authenticated_at and (mumble_user.last_authenticated is None or authenticated_at >= mumble_user.last_authenticated):
        mumble_user.last_authenticated = authenticated_at
        updates.append('last_authenticated')
    if connected_at and (mumble_user.last_connected is None or connected_at >= mumble_user.last_connected):
        mumble_user.last_connected = connected_at
        updates.append('last_connected')
    if disconnected_at and (mumble_user.last_disconnected is None or disconnected_at >= mumble_user.last_disconnected):
        mumble_user.last_disconnected = disconnected_at
        updates.append('last_disconnected')
    if seen_at and (mumble_user.last_seen is None or seen_at >= mumble_user.last_seen):
        mumble_user.last_seen = seen_at
        updates.append('last_seen')
    if spoke_at and (mumble_user.last_spoke is None or spoke_at >= mumble_user.last_spoke):
        mumble_user.last_spoke = spoke_at
        updates.append('last_spoke')

    if updates:
        mumble_user.save(update_fields=updates + ['updated_at'])


def record_successful_authentication(bg_row_id, certhash):
    now = timezone.now()
    try:
        mumble_user = MumbleUser.objects.get(pk=bg_row_id)
    except MumbleUser.DoesNotExist:
        logger.warning('Murmur Pulse auth update skipped for missing MumbleUser pk=%s', bg_row_id)
        return

    updates = ['last_authenticated', 'updated_at']
    mumble_user.last_authenticated = now
    if certhash is not None:
        normalized_hash = certhash or ''
        if mumble_user.certhash != normalized_hash:
            mumble_user.certhash = normalized_hash
            updates.append('certhash')
    mumble_user.save(update_fields=updates)


def upsert_session_from_state(server, state, observed_at=None):
    observed_at = observed_at or timezone.now()
    normalized = _normalize_user_state(state)
    if normalized.session_id <= 0:
        raise ValueError('Pulse session updates require a positive session_id')

    connected_at = _derive_connected_at(observed_at, normalized.onlinesecs)
    last_spoke_at = _derive_last_spoke_at(observed_at, normalized.idlesecs)
    mumble_user = _resolve_mumble_user(server, normalized)

    with transaction.atomic():
        session = (
            MumbleSession.objects.select_for_update()
            .filter(server=server, session_id=normalized.session_id, is_active=True)
            .first()
        )
        created = session is None
        if created:
            session = MumbleSession(
                server=server,
                session_id=normalized.session_id,
                connected_at=connected_at,
            )
        else:
            session.connected_at = min(session.connected_at, connected_at)

        session.mumble_user = mumble_user
        session.mumble_userid = normalized.mumble_userid
        session.username = normalized.username
        session.channel_id = normalized.channel_id
        session.address = normalized.address
        session.cert_hash = normalized.cert_hash or (mumble_user.certhash if mumble_user else '')
        session.tcponly = normalized.tcponly
        session.mute = normalized.mute
        session.deaf = normalized.deaf
        session.suppress = normalized.suppress
        session.priority_speaker = normalized.priority_speaker
        session.self_mute = normalized.self_mute
        session.self_deaf = normalized.self_deaf
        session.recording = normalized.recording
        session.onlinesecs = normalized.onlinesecs
        session.idlesecs = normalized.idlesecs
        session.last_seen = observed_at
        session.last_state = observed_at
        session.last_spoke = last_spoke_at
        session.disconnected_at = None
        session.is_active = True
        session.save()

    _apply_user_presence(
        mumble_user,
        connected_at=connected_at,
        seen_at=observed_at,
        spoke_at=last_spoke_at,
    )
    return session, created


def mark_session_disconnected(server, session_id, state=None, observed_at=None):
    observed_at = observed_at or timezone.now()
    normalized = _normalize_user_state(state) if state is not None else None

    with transaction.atomic():
        session = (
            MumbleSession.objects.select_for_update()
            .filter(server=server, session_id=session_id, is_active=True)
            .first()
        )
        if session is None:
            return False

        mumble_user = session.mumble_user
        if normalized is not None:
            if normalized.username:
                session.username = normalized.username
            session.channel_id = normalized.channel_id
            session.address = normalized.address or session.address
            session.cert_hash = normalized.cert_hash or session.cert_hash
            session.mute = normalized.mute
            session.deaf = normalized.deaf
            session.suppress = normalized.suppress
            session.priority_speaker = normalized.priority_speaker
            session.self_mute = normalized.self_mute
            session.self_deaf = normalized.self_deaf
            session.recording = normalized.recording
            session.onlinesecs = normalized.onlinesecs
            session.idlesecs = normalized.idlesecs
            if normalized.mumble_userid is not None:
                session.mumble_userid = normalized.mumble_userid
            if mumble_user is None:
                mumble_user = _resolve_mumble_user(server, normalized)
                session.mumble_user = mumble_user

        session.last_seen = observed_at
        session.last_state = observed_at
        if normalized is not None:
            session.last_spoke = _derive_last_spoke_at(observed_at, normalized.idlesecs)
        session.disconnected_at = observed_at
        session.is_active = False
        session.save()

    _apply_user_presence(
        mumble_user,
        disconnected_at=observed_at,
        seen_at=observed_at,
        spoke_at=session.last_spoke,
    )
    return True


def mark_server_sessions_disconnected(server, observed_at=None):
    observed_at = observed_at or timezone.now()
    session_ids = list(
        MumbleSession.objects.filter(server=server, is_active=True).values_list('session_id', flat=True)
    )
    disconnected = 0
    for session_id in session_ids:
        if mark_session_disconnected(server, session_id, observed_at=observed_at):
            disconnected += 1
    return disconnected


def reconcile_server_snapshot(server, users, observed_at=None):
    observed_at = observed_at or timezone.now()
    seen_sessions = set()
    created = 0
    updated = 0
    disconnected = 0

    for session_key, state in (users or {}).items():
        normalized = _normalize_user_state(state)
        session_id = normalized.session_id or _coerce_int(session_key)
        if not session_id:
            continue
        seen_sessions.add(int(session_id))
        _, was_created = upsert_session_from_state(server, state, observed_at=observed_at)
        if was_created:
            created += 1
        else:
            updated += 1

    stale_sessions = MumbleSession.objects.filter(server=server, is_active=True)
    if seen_sessions:
        stale_sessions = stale_sessions.exclude(session_id__in=seen_sessions)

    for session_id in stale_sessions.values_list('session_id', flat=True):
        if mark_session_disconnected(server, session_id, observed_at=observed_at):
            disconnected += 1

    return {
        'created': created,
        'updated': updated,
        'disconnected': disconnected,
    }


def _build_meta_callback(M, endpoint_runtime):
    class PulseMetaCallback(M.MetaCallback):
        def started(self, srv, current=None):
            endpoint_runtime.request_refresh()

        def stopped(self, srv, current=None):
            endpoint_runtime.request_refresh()

    return PulseMetaCallback()


def _build_server_callback(M, bg_server):
    class PulseServerCallback(M.ServerCallback):
        def userConnected(self, state, current=None):
            try:
                upsert_session_from_state(bg_server, state, observed_at=timezone.now())
            except Exception:
                logger.exception('Murmur Pulse failed to process userConnected for server=%s', bg_server.pk)

        def userDisconnected(self, state, current=None):
            try:
                normalized = _normalize_user_state(state)
                mark_session_disconnected(
                    bg_server,
                    normalized.session_id,
                    state=state,
                    observed_at=timezone.now(),
                )
            except Exception:
                logger.exception('Murmur Pulse failed to process userDisconnected for server=%s', bg_server.pk)

        def userStateChanged(self, state, current=None):
            try:
                upsert_session_from_state(bg_server, state, observed_at=timezone.now())
            except Exception:
                logger.exception('Murmur Pulse failed to process userStateChanged for server=%s', bg_server.pk)

        def userTextMessage(self, state, message, current=None):
            return None

        def channelCreated(self, state, current=None):
            return None

        def channelRemoved(self, state, current=None):
            return None

        def channelStateChanged(self, state, current=None):
            return None

    return PulseServerCallback()


class _EndpointRuntime:
    def __init__(self, communicator, adapter, M, server_configs):
        self._communicator = communicator
        self._adapter = adapter
        self._M = M
        self._server_configs = list(server_configs)
        self._host = self._server_configs[0].ice_host
        self._port = self._server_configs[0].ice_port
        self._secret = self._server_configs[0].ice_secret
        self._meta = None
        self._meta_callback_proxy = None
        self._meta_callback_servant = None
        self._server_callbacks = {}
        self._refresh_requested = True

    def request_refresh(self):
        self._refresh_requested = True

    @property
    def needs_refresh(self):
        return self._refresh_requested

    def _with_secret(self, proxy):
        if self._secret:
            return proxy.ice_context({'secret': self._secret})
        return proxy

    def _get_meta(self):
        if self._meta is not None:
            return self._meta

        endpoint = f'Meta:tcp -h {self._host} -p {self._port}'
        proxy = self._communicator.stringToProxy(endpoint)
        meta = self._M.MetaPrx.checkedCast(proxy)
        if not meta:
            raise MurmurPulseError(f'Failed to connect to ICE Meta at {self._host}:{self._port}')
        self._meta = self._with_secret(meta)
        self._register_meta_callback()
        return self._meta

    def _register_meta_callback(self):
        if self._meta_callback_proxy is not None:
            return
        servant = _build_meta_callback(self._M, self)
        base_proxy = self._adapter.addWithUUID(servant)
        callback_proxy = self._M.MetaCallbackPrx.uncheckedCast(base_proxy)
        self._get_meta().addCallback(callback_proxy)
        self._meta_callback_servant = servant
        self._meta_callback_proxy = callback_proxy

    def _match_booted_servers(self, booted_servers):
        targets = {}
        single_booted = booted_servers[0] if len(booted_servers) == 1 else None
        for bg_server in self._server_configs:
            target = None
            if bg_server.virtual_server_id is not None:
                for booted_server in booted_servers:
                    if booted_server.id() == bg_server.virtual_server_id:
                        target = self._with_secret(booted_server)
                        break
                if target is None:
                    logger.warning(
                        'Murmur Pulse could not find virtual_server_id=%s for bg server=%s',
                        bg_server.virtual_server_id,
                        bg_server.pk,
                    )
            elif single_booted is not None:
                target = self._with_secret(single_booted)
            else:
                logger.warning(
                    'Murmur Pulse requires virtual_server_id for bg server=%s because multiple booted servers share %s:%s',
                    bg_server.pk,
                    self._host,
                    self._port,
                )
            if target is not None:
                targets[bg_server.pk] = target
        return targets

    def _add_server_callback(self, bg_server, server_proxy):
        servant = _build_server_callback(self._M, bg_server)
        base_proxy = self._adapter.addWithUUID(servant)
        callback_proxy = self._M.ServerCallbackPrx.uncheckedCast(base_proxy)
        server_proxy.addCallback(callback_proxy)
        self._server_callbacks[bg_server.pk] = {
            'proxy': callback_proxy,
            'servant': servant,
            'server_proxy': server_proxy,
        }

    def _remove_server_callback(self, bg_server_id):
        existing = self._server_callbacks.pop(bg_server_id, None)
        if not existing:
            return
        try:
            existing['server_proxy'].removeCallback(existing['proxy'])
        except Exception:
            pass
        try:
            self._adapter.remove(existing['proxy'].ice_getIdentity())
        except Exception:
            pass

    def _sync_server_callbacks(self, matched_targets):
        matched_ids = set(matched_targets.keys())
        existing_ids = set(self._server_callbacks.keys())

        for missing_id in existing_ids - matched_ids:
            self._remove_server_callback(missing_id)

        for bg_server in self._server_configs:
            server_proxy = matched_targets.get(bg_server.pk)
            if server_proxy is None:
                continue
            if bg_server.pk not in self._server_callbacks:
                self._add_server_callback(bg_server, server_proxy)

    def tick(self):
        meta = self._get_meta()
        booted_servers = meta.getBootedServers()
        matched_targets = self._match_booted_servers(booted_servers)
        self._sync_server_callbacks(matched_targets)

        observed_at = timezone.now()
        for bg_server in self._server_configs:
            server_proxy = matched_targets.get(bg_server.pk)
            if server_proxy is None:
                mark_server_sessions_disconnected(bg_server, observed_at=observed_at)
                continue
            users = server_proxy.getUsers()
            reconcile_server_snapshot(bg_server, users, observed_at=observed_at)

        self._refresh_requested = False

    def close(self):
        for bg_server_id in list(self._server_callbacks):
            self._remove_server_callback(bg_server_id)
        if self._meta is not None and self._meta_callback_proxy is not None:
            try:
                self._meta.removeCallback(self._meta_callback_proxy)
            except Exception:
                pass
        if self._meta_callback_proxy is not None:
            try:
                self._adapter.remove(self._meta_callback_proxy.ice_getIdentity())
            except Exception:
                pass
        self._meta = None
        self._meta_callback_proxy = None
        self._meta_callback_servant = None
        self._refresh_requested = True


class MurmurPulseService:
    def __init__(self, *, callback_endpoint='tcp -h 0.0.0.0', server_id=None):
        self._callback_endpoint = callback_endpoint
        self._server_id = server_id

    def _load_server_configs(self):
        qs = MumbleServer.objects.filter(is_active=True).order_by('display_order', 'name')
        if self._server_id is not None:
            qs = qs.filter(pk=self._server_id)
        return list(qs)

    def _group_endpoints(self, server_configs):
        grouped = {}
        for server_config in server_configs:
            key = (
                server_config.ice_host,
                server_config.ice_port,
                server_config.ice_secret,
            )
            grouped.setdefault(key, []).append(server_config)
        return list(grouped.values())

    def run(self, *, once=False, poll_interval=30):
        try:
            import Ice
        except ImportError as exc:
            raise MurmurPulseError('ZeroC ICE is not installed in this environment') from exc

        server_configs = self._load_server_configs()
        if not server_configs:
            raise MurmurPulseError('No active MumbleServer rows matched for Murmur Pulse')

        M = _load_slice()
        endpoints = self._group_endpoints(server_configs)

        with Ice.initialize(['--Ice.Default.EncodingVersion=1.0']) as communicator:
            adapter = communicator.createObjectAdapterWithEndpoints('MurmurPulse', self._callback_endpoint)
            adapter.activate()
            runtimes = [_EndpointRuntime(communicator, adapter, M, endpoint_servers) for endpoint_servers in endpoints]
            try:
                while True:
                    for runtime in runtimes:
                        try:
                            runtime.tick()
                        except Exception:
                            logger.exception(
                                'Murmur Pulse endpoint tick failed for %s:%s',
                                runtime._host,
                                runtime._port,
                            )
                            runtime.close()
                    if once:
                        return
                    slept = 0
                    interval = max(poll_interval, 1)
                    while slept < interval:
                        if any(runtime.needs_refresh for runtime in runtimes):
                            break
                        time.sleep(1)
                        slept += 1
            finally:
                for runtime in runtimes:
                    runtime.close()
