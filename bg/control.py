"""HTTP control API for the fg/bg boundary."""

import json
import os
import secrets
from http import HTTPStatus
from typing import Any

from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from bg.passwords import build_murmur_password_record
from bg.pilot.registrations import (
    disable_murmur_registration,
    MurmurSyncError,
    sync_live_admin_membership,
    sync_murmur_registration,
)
from bg.contracts import MurmurRegistrationContractPatch, MurmurRegistrationSnapshot
from bg.state.models import (
    AccessRule,
    BG_AUDIT_ACTION_ACL_SYNC,
    BG_AUDIT_ACTION_PILOT_CREATE,
    BG_AUDIT_ACTION_PILOT_DISABLE,
    BG_AUDIT_ACTION_PILOT_ENABLE,
    BG_AUDIT_ACTION_PILOT_PWRESET,
    ENTITY_TYPE_ALLIANCE,
    ENTITY_TYPE_CORPORATION,
    ENTITY_TYPE_PILOT,
    ControlChannelKey,
    MumbleServer,
    MumbleSession,
    MumbleUser,
    append_bg_audit,
)

_PilotRegistrationSnapshot = MurmurRegistrationSnapshot
_RegistrationContractPatch = MurmurRegistrationContractPatch


class _BadRequest(ValueError):
    """Raised when a control request is malformed."""


class _NotFound(ValueError):
    """Raised when requested entities do not exist."""


class _Unauthorized(ValueError):
    """Raised when a control request fails authentication."""


class _Forbidden(ValueError):
    """Raised when a control request fails authorization."""


_FORBIDDEN_PASSWORD_CHARS = {"'", '"', '`', '\\'}
_PASSWORD_CHARS = ''.join(
    chr(code) for code in range(33, 127) if chr(code) not in _FORBIDDEN_PASSWORD_CHARS
)
_CONTROL_KEY_NAME = 'fg_bg'


def _new_password(length: int = 16) -> str:
    return ''.join(secrets.choice(_PASSWORD_CHARS) for _ in range(length))


def _env_bootstrap_psk() -> str | None:
    value = os.getenv('MURMUR_CONTROL_PSK', '').strip()
    return value or None


def _control_key_row() -> ControlChannelKey:
    row, _ = ControlChannelKey.objects.get_or_create(name=_CONTROL_KEY_NAME)
    return row


def _configured_control_secret() -> tuple[str | None, str]:
    try:
        row = ControlChannelKey.objects.filter(name=_CONTROL_KEY_NAME).only('shared_secret').first()
    except Exception:  # noqa: BLE001
        row = None
    if row and row.shared_secret:
        return row.shared_secret, 'db'
    env_secret = _env_bootstrap_psk()
    if env_secret:
        return env_secret, 'env'
    return None, 'open'


def _provided_control_secret(request) -> str | None:
    value = request.headers.get('X-Murmur-Control-PSK') or request.headers.get('X-Control-PSK')
    if value:
        value = str(value).strip()
        return value or None
    authorization = request.headers.get('Authorization') or ''
    if authorization.lower().startswith('bearer '):
        bearer = authorization[7:].strip()
        return bearer or None
    return None


def _require_control_auth(request) -> str:
    expected, source = _configured_control_secret()
    if not expected:
        return source
    provided = _provided_control_secret(request)
    if not provided:
        raise _Unauthorized('Missing control authentication secret')
    if not secrets.compare_digest(provided, expected):
        raise _Unauthorized('Invalid control authentication secret')
    return source


def _require_requested_by(requested_by: str | None):
    if not requested_by:
        raise _BadRequest('requested_by is required')


def _require_super(is_super: bool):
    if not is_super:
        raise _Forbidden('superuser permission is required')


def _request_id(payload: dict[str, Any]) -> str:
    value = payload.get('request_id')
    if isinstance(value, str) and value:
        return value
    return now().strftime('%Y%m%dT%H%M%SZ')


def _response(
    request_id: str,
    status: str,
    *,
    message: str | None = None,
    code: int = 200,
    **payload: Any,
) -> JsonResponse:
    envelope: dict[str, Any] = {'request_id': request_id, 'status': status}
    if message:
        envelope['message'] = message
    envelope.update(payload)
    return JsonResponse(envelope, status=code)


def _load_json_payload(request) -> dict[str, Any]:
    if not request.body:
        return {}

    try:
        raw = request.body.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise _BadRequest('Request payload must be valid UTF-8') from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _BadRequest('Request payload must be valid JSON') from exc

    if not isinstance(payload, dict):
        raise _BadRequest('Request payload must be an object')
    return payload


def _extract_payload_envelope(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if 'payload' in payload:
        nested = payload.get('payload')
        if not isinstance(nested, dict):
            raise _BadRequest('payload must be an object')
        return payload, nested
    return payload, payload


def _coerce_int(value: Any, *, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise _BadRequest(f'{field} must be an integer') from exc


def _coerce_bool(value: Any, *, field: str) -> bool:
    if isinstance(value, bool):
        return value
    raise _BadRequest(f'{field} must be a boolean')


def _coerce_optional_text(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _BadRequest(f'{field} must be a string')
    return value.strip()


def _coerce_session_ids(payload: dict[str, Any]) -> list[int]:
    session_ids = payload.get('session_ids')
    if session_ids is None:
        return []
    if not isinstance(session_ids, (list, tuple)):
        raise _BadRequest('session_ids must be a list')
    normalized = [_coerce_int(session_id, field='session_ids') for session_id in session_ids]
    return [session_id for session_id in normalized if session_id > 0]


def _read_requested_by(outer_payload: dict[str, Any], payload: dict[str, Any]) -> str | None:
    value = outer_payload.get('requested_by')
    if value is None:
        value = payload.get('requested_by')
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise _BadRequest('requested_by must be a non-empty string')
    return value.strip()


def _read_is_super(outer_payload: dict[str, Any], payload: dict[str, Any]) -> bool:
    value = outer_payload.get('is_super')
    if value is None:
        value = payload.get('is_super')
    if value is None:
        return False
    if not isinstance(value, bool):
        raise _BadRequest('is_super must be a boolean')
    return value


def _read_password(payload: dict[str, Any]) -> str | None:
    if 'password' not in payload:
        return None
    password = payload.get('password')
    if not isinstance(password, str) or not password:
        raise _BadRequest('password must be a non-empty string')
    _validate_password(password, field_name='password')
    return password


def _read_preferred_password(payload: dict[str, Any]) -> str | None:
    password = _read_password(payload)
    if password is not None:
        return password
    for field_name in ('preferred_password', 'proposed_password', 'temporary_password', 'recommended_password'):
        if field_name not in payload:
            continue
        password = payload.get(field_name)
        if not isinstance(password, str) or not password:
            raise _BadRequest(f'{field_name} must be a non-empty string')
        _validate_password(password, field_name=field_name)
        return password
    return None


def _validate_password(password: str, *, field_name: str):
    for ch in password:
        if ord(ch) < 33 or ord(ch) > 126:
            raise _BadRequest(f'{field_name} must use printable 7-bit ASCII characters only')
        if ch in _FORBIDDEN_PASSWORD_CHARS:
            raise _BadRequest(f"{field_name} cannot contain any of: ' \" ` \\")


def _read_new_control_secret(payload: dict[str, Any]) -> str:
    for field_name in ('new_control_psk', 'control_psk', 'shared_secret', 'new_psk'):
        if field_name not in payload:
            continue
        value = payload.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise _BadRequest(f'{field_name} must be a non-empty string')
        normalized = value.strip()
        if len(normalized) < 16:
            raise _BadRequest(f'{field_name} must be at least 16 characters')
        return normalized
    raise _BadRequest('new_control_psk is required')


class _ServerResolver:
    """Resolve server selectors from control payloads."""

    def resolve(self, payload: dict[str, Any]) -> MumbleServer:
        name = payload.get('server_name')
        server_id = payload.get('server_id')

        if not name and not server_id:
            raise _BadRequest('Either server_name or server_id is required')
        if name and server_id:
            raise _BadRequest('Use either server_name or server_id, not both')

        if name:
            if not isinstance(name, str) or not name.strip():
                raise _BadRequest('server_name must be a non-empty string')
            servers = list(MumbleServer.objects.filter(name=name, is_active=True))
        else:
            server_id_value = _coerce_int(server_id, field='server_id')
            servers = list(MumbleServer.objects.filter(pk=server_id_value, is_active=True))

        if not servers:
            raise _NotFound('Server not found')
        if len(servers) > 1:
            raise _BadRequest('Multiple matching servers found; use server_id')
        return servers[0]


class _MumbleUserResolver:
    """Resolve pilot registration rows scoped to a target server."""

    def resolve(self, *, server: MumbleServer, payload: dict[str, Any]) -> MumbleUser:
        pkid = payload.get('pkid')
        if pkid is None:
            raise _BadRequest('pkid is required')
        pkid_value = _coerce_int(pkid, field='pkid')
        mumble_user = MumbleUser.objects.filter(user_id=pkid_value, server=server, is_active=True).first()
        if not mumble_user:
            raise _NotFound('Mumble registration not found')
        return mumble_user


class _RegistrationContractService:
    """Parse and persist contract metadata fields for one registration row."""

    def parse_patch(self, payload: dict[str, Any]) -> _RegistrationContractPatch:
        try:
            return _RegistrationContractPatch.from_payload(payload)
        except ValueError as exc:
            raise _BadRequest(str(exc)) from exc

    @staticmethod
    def apply(mumble_user: MumbleUser, patch: _RegistrationContractPatch):
        if 'evepilot_id' in patch.provided_fields:
            mumble_user.evepilot_id = patch.evepilot_id
        if 'corporation_id' in patch.provided_fields:
            mumble_user.corporation_id = patch.corporation_id
        if 'alliance_id' in patch.provided_fields:
            mumble_user.alliance_id = patch.alliance_id
        if 'kdf_iterations' in patch.provided_fields:
            mumble_user.kdf_iterations = patch.kdf_iterations
        mumble_user.save(update_fields=patch.update_fields())

    @staticmethod
    def values(mumble_user: MumbleUser) -> dict[str, int | None]:
        return {
            'evepilot_id': mumble_user.evepilot_id,
            'corporation_id': mumble_user.corporation_id,
            'alliance_id': mumble_user.alliance_id,
            'kdf_iterations': mumble_user.kdf_iterations,
        }


class _PilotProbeService:
    """Build read-only probe payloads for pilot registration status."""

    @staticmethod
    def _active_session_ids(row: MumbleUser) -> list[int]:
        return list(
            MumbleSession.objects.filter(
                server_id=row.server_id,
                mumble_user=row,
                is_active=True,
            ).order_by('session_id').values_list('session_id', flat=True)
        )

    @staticmethod
    def _has_priority_speaker(row: MumbleUser) -> bool:
        return MumbleSession.objects.filter(
            server_id=row.server_id,
            mumble_user=row,
            is_active=True,
            priority_speaker=True,
        ).exists()

    def pilot_payload(self, pkid: int) -> dict[str, Any] | None:
        rows = list(
            MumbleUser.objects.filter(user_id=pkid, is_active=True)
            .select_related('server')
            .order_by('server__display_order', 'server__name')
        )
        if not rows:
            return None

        snapshots = [
            _PilotRegistrationSnapshot.from_row(
                row,
                active_session_ids=self._active_session_ids(row),
                has_priority_speaker=self._has_priority_speaker(row),
            )
            for row in rows
        ]
        return {
            'status': 'completed',
            'pkid': pkid,
            'request_id': now().strftime('%Y%m%dT%H%M%SZ'),
            'registrations': [snapshot.as_dict() for snapshot in snapshots],
            'registration_count': len(snapshots),
            'timestamp': now().isoformat(),
        }

    def registrations_payload(self) -> dict[str, Any]:
        rows = list(
            MumbleUser.objects.filter(is_active=True)
            .select_related('server')
            .order_by('user_id', 'server__display_order', 'server__name')
        )
        snapshots = [
            _PilotRegistrationSnapshot.from_row(
                row,
                active_session_ids=self._active_session_ids(row),
                has_priority_speaker=self._has_priority_speaker(row),
            )
            for row in rows
        ]
        return {
            'status': 'completed',
            'request_id': now().strftime('%Y%m%dT%H%M%SZ'),
            'registrations': [snapshot.as_dict() for snapshot in snapshots],
            'registration_count': len(snapshots),
            'timestamp': now().isoformat(),
        }


_SERVER_RESOLVER = _ServerResolver()
_MUMBLE_USER_RESOLVER = _MumbleUserResolver()
_PILOT_PROBE_SERVICE = _PilotProbeService()
_REGISTRATION_CONTRACT_SERVICE = _RegistrationContractService()


def _sync_context(request):
    envelope = _load_json_payload(request)
    outer_payload, payload = _extract_payload_envelope(envelope)
    request_id = _request_id(outer_payload)
    requested_by = _read_requested_by(outer_payload, payload)
    is_super = _read_is_super(outer_payload, payload)
    return payload, request_id, requested_by, is_super


@csrf_exempt
@require_http_methods(['POST'])
def registrations_sync(request):
    try:
        auth_source = _require_control_auth(request)
        payload, request_id, requested_by, _ = _sync_context(request)
        _require_requested_by(requested_by)
        server = _SERVER_RESOLVER.resolve(payload)
        mumble_user = _MUMBLE_USER_RESOLVER.resolve(server=server, payload=payload)
        del auth_source  # validated, reserved for future audit logging
    except _BadRequest as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.BAD_REQUEST)
    except _Unauthorized as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.UNAUTHORIZED)
    except _Forbidden as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.FORBIDDEN)
    except _NotFound as exc:
        return _response('unknown', 'not_found', message=str(exc), code=HTTPStatus.NOT_FOUND)

    if payload.get('dry_run'):
        return _response(
            request_id,
            'completed',
            message='Dry run requested; skipping ICE registration call',
            server_name=server.name,
            pkid=mumble_user.user_id,
        )

    password = _read_preferred_password(payload)

    try:
        sync_result = sync_murmur_registration(mumble_user, password=password, return_details=True)
        murmur_userid = int(sync_result.get('murmur_userid'))
        created_in_murmur = bool(sync_result.get('created', False))
    except MurmurSyncError as exc:
        return _response(
            request_id,
            'failed',
            message=f'Failed to sync registration: {exc}',
            code=HTTPStatus.BAD_GATEWAY,
        )

    if murmur_userid is not None and mumble_user.mumble_userid != murmur_userid:
        mumble_user.mumble_userid = murmur_userid
        mumble_user.save(update_fields=['mumble_userid', 'updated_at'])

    if created_in_murmur:
        append_bg_audit(
            action=BG_AUDIT_ACTION_PILOT_CREATE,
            request_id=request_id,
            requested_by=requested_by,
            source='registrations_sync',
            user_id=mumble_user.user_id,
            server_name=server.name,
            metadata={
                'murmur_userid': murmur_userid,
                'username': mumble_user.username,
            },
        )

    if bool(sync_result.get('reenabled', False)):
        append_bg_audit(
            action=BG_AUDIT_ACTION_PILOT_ENABLE,
            request_id=request_id,
            requested_by=requested_by,
            source='registrations_sync',
            user_id=mumble_user.user_id,
            server_name=server.name,
            metadata={
                'murmur_userid': murmur_userid,
                'username': mumble_user.username,
            },
        )

    return _response(
        request_id,
        'completed',
        message='Registration synchronized',
        murmur_userid=mumble_user.mumble_userid,
        user_id=mumble_user.user_id,
        server_name=server.name,
    )


@csrf_exempt
@require_http_methods(['POST'])
def registration_contract_sync(request):
    try:
        auth_source = _require_control_auth(request)
        payload, request_id, requested_by, is_super = _sync_context(request)
        _require_requested_by(requested_by)
        _require_super(is_super)
        server = _SERVER_RESOLVER.resolve(payload)
        mumble_user = _MUMBLE_USER_RESOLVER.resolve(server=server, payload=payload)
        patch = _REGISTRATION_CONTRACT_SERVICE.parse_patch(payload)
        del auth_source  # validated, reserved for future audit logging
    except _BadRequest as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.BAD_REQUEST)
    except _Unauthorized as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.UNAUTHORIZED)
    except _Forbidden as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.FORBIDDEN)
    except _NotFound as exc:
        return _response('unknown', 'not_found', message=str(exc), code=HTTPStatus.NOT_FOUND)

    _REGISTRATION_CONTRACT_SERVICE.apply(mumble_user, patch)
    return _response(
        request_id,
        'completed',
        message='Registration contract metadata synchronized',
        user_id=mumble_user.user_id,
        server_name=server.name,
        **_REGISTRATION_CONTRACT_SERVICE.values(mumble_user),
    )


@csrf_exempt
@require_http_methods(['POST'])
def registrations_disable(request):
    try:
        auth_source = _require_control_auth(request)
        payload, request_id, requested_by, _ = _sync_context(request)
        _require_requested_by(requested_by)
        server = _SERVER_RESOLVER.resolve(payload)
        mumble_user = _MUMBLE_USER_RESOLVER.resolve(server=server, payload=payload)
        del auth_source  # validated, reserved for future audit logging
    except _BadRequest as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.BAD_REQUEST)
    except _Unauthorized as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.UNAUTHORIZED)
    except _Forbidden as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.FORBIDDEN)
    except _NotFound as exc:
        return _response('unknown', 'not_found', message=str(exc), code=HTTPStatus.NOT_FOUND)

    try:
        disabled_result = disable_murmur_registration(mumble_user)
    except MurmurSyncError as exc:
        return _response(
            request_id,
            'failed',
            message=f'Failed to disable registration: {exc}',
            code=HTTPStatus.BAD_GATEWAY,
        )
    disabled = bool(disabled_result.get('changed', False))
    murmur_userid = disabled_result.get('murmur_userid')
    if murmur_userid is not None and mumble_user.mumble_userid != int(murmur_userid):
        mumble_user.mumble_userid = int(murmur_userid)
        mumble_user.save(update_fields=['mumble_userid', 'updated_at'])
    if disabled:
        append_bg_audit(
            action=BG_AUDIT_ACTION_PILOT_DISABLE,
            request_id=request_id,
            requested_by=requested_by,
            source='registrations_disable',
            user_id=mumble_user.user_id,
            server_name=server.name,
            metadata={
                'murmur_userid': murmur_userid,
                'username': mumble_user.username,
            },
        )

    return _response(
        request_id,
        'completed',
        message='Registration disabled' if disabled else 'Registration already disabled or missing',
        disabled=disabled,
        murmur_userid=murmur_userid,
        user_id=mumble_user.user_id,
        server_name=server.name,
    )


@csrf_exempt
@require_http_methods(['POST'])
def admin_membership_sync(request):
    try:
        auth_source = _require_control_auth(request)
        payload, request_id, requested_by, _ = _sync_context(request)
        _require_requested_by(requested_by)
        server = _SERVER_RESOLVER.resolve(payload)
        mumble_user = _MUMBLE_USER_RESOLVER.resolve(server=server, payload=payload)
        admin = _coerce_bool(payload.get('admin'), field='admin')
        groups = _coerce_optional_text(payload.get('groups'), field='groups')
        session_ids = _coerce_session_ids(payload)
        del auth_source  # validated, reserved for future audit logging
    except _BadRequest as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.BAD_REQUEST)
    except _Unauthorized as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.UNAUTHORIZED)
    except _Forbidden as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.FORBIDDEN)
    except _NotFound as exc:
        return _response('unknown', 'not_found', message=str(exc), code=HTTPStatus.NOT_FOUND)

    update_fields: list[str] = []
    if mumble_user.is_mumble_admin != admin:
        mumble_user.is_mumble_admin = admin
        update_fields.append('is_mumble_admin')
    if groups is not None and mumble_user.groups != groups:
        mumble_user.groups = groups
        update_fields.append('groups')
    if update_fields:
        mumble_user.save(update_fields=[*update_fields, 'updated_at'])

    try:
        synced_sessions = sync_live_admin_membership(mumble_user, session_ids=session_ids)
    except MurmurSyncError as exc:
        return _response(
            request_id,
            'failed',
            message=f'Failed to sync admin membership: {exc}',
            code=HTTPStatus.BAD_GATEWAY,
        )

    return _response(
        request_id,
        'completed',
        message='Admin membership synced',
        server_name=server.name,
        user_id=mumble_user.user_id,
        admin=admin,
        synced_sessions=synced_sessions,
    )


@csrf_exempt
@require_http_methods(['POST'])
def password_reset(request):
    try:
        auth_source = _require_control_auth(request)
        payload, request_id, requested_by, _ = _sync_context(request)
        _require_requested_by(requested_by)

        # Server is optional — if not provided, find the user's registration on any server
        has_server = payload.get('server_name') or payload.get('server_id')
        if has_server:
            server = _SERVER_RESOLVER.resolve(payload)
            mumble_user = _MUMBLE_USER_RESOLVER.resolve(server=server, payload=payload)
        else:
            pkid = payload.get('pkid')
            if pkid is None:
                raise _BadRequest('pkid is required')
            pkid_value = _coerce_int(pkid, field='pkid')
            mumble_user = MumbleUser.objects.filter(
                user_id=pkid_value, is_active=True, server__is_active=True,
            ).select_related('server').first()
            if not mumble_user:
                raise _NotFound('Mumble registration not found')
            server = mumble_user.server

        desired_password = _read_preferred_password(payload)
        encrypted_password = payload.get('encrypted_password')
        del auth_source  # validated, reserved for future audit logging
    except _BadRequest as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.BAD_REQUEST)
    except _Unauthorized as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.UNAUTHORIZED)
    except _Forbidden as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.FORBIDDEN)
    except _NotFound as exc:
        return _response('unknown', 'not_found', message=str(exc), code=HTTPStatus.NOT_FOUND)

    # Decrypt encrypted_password if provided (FG encrypts with BG's public key)
    if encrypted_password and desired_password is None:
        from bg.crypto import can_decrypt, decrypt_password
        if not can_decrypt():
            return _response(
                request_id,
                'failed',
                message='Encrypted password provided but BG crypto is not configured',
                code=HTTPStatus.SERVICE_UNAVAILABLE,
            )
        try:
            desired_password = decrypt_password(encrypted_password)
            _validate_password(desired_password, field_name='encrypted_password (decrypted)')
        except Exception as exc:
            return _response(
                request_id,
                'failed',
                message=f'Failed to decrypt password: {exc}',
                code=HTTPStatus.BAD_REQUEST,
            )

    requested = desired_password is None
    password = desired_password if desired_password is not None else _new_password()

    record = build_murmur_password_record(password)
    mumble_user.pwhash = record['pwhash']
    mumble_user.hashfn = record['hashfn']
    mumble_user.pw_salt = record['pw_salt']
    mumble_user.kdf_iterations = record['kdf_iterations']

    skip_ice = payload.get('skip_murmur_sync', False)
    murmur_userid = None
    ice_synced = False

    created_in_murmur = False
    if not skip_ice:
        try:
            sync_result = sync_murmur_registration(
                mumble_user,
                password=password,
                return_details=True,
            )
            murmur_userid = int(sync_result.get('murmur_userid'))
            created_in_murmur = bool(sync_result.get('created', False))
            ice_synced = True
        except MurmurSyncError as exc:
            # Store the hash locally even if ICE sync fails
            mumble_user.save(update_fields=['pwhash', 'hashfn', 'pw_salt', 'kdf_iterations', 'updated_at'])
            append_bg_audit(
                action=BG_AUDIT_ACTION_PILOT_PWRESET,
                request_id=request_id,
                requested_by=requested_by,
                source='password_reset',
                user_id=mumble_user.user_id,
                server_name=server.name,
                metadata={
                    'status': 'partial',
                    'ice_synced': False,
                    'password_generated': requested,
                    'reason': str(exc),
                },
            )
            return _response(
                request_id,
                'partial',
                message=f'Password hash stored but Murmur sync failed: {exc}',
                user_id=mumble_user.user_id,
                server_name=server.name,
                password=password,
                password_generated=requested,
                ice_synced=False,
                code=HTTPStatus.OK,
            )

    if murmur_userid is not None:
        mumble_user.mumble_userid = murmur_userid

    mumble_user.save(update_fields=['pwhash', 'hashfn', 'pw_salt', 'kdf_iterations', 'mumble_userid', 'updated_at'])

    append_bg_audit(
        action=BG_AUDIT_ACTION_PILOT_PWRESET,
        request_id=request_id,
        requested_by=requested_by,
        source='password_reset',
        user_id=mumble_user.user_id,
        server_name=server.name,
        metadata={
            'status': 'completed',
            'ice_synced': bool(ice_synced),
            'password_generated': requested,
            'skip_murmur_sync': bool(skip_ice),
            'murmur_userid': murmur_userid,
        },
    )
    if created_in_murmur:
        append_bg_audit(
            action=BG_AUDIT_ACTION_PILOT_CREATE,
            request_id=request_id,
            requested_by=requested_by,
            source='password_reset',
            user_id=mumble_user.user_id,
            server_name=server.name,
            metadata={
                'murmur_userid': murmur_userid,
                'username': mumble_user.username,
            },
        )

    return _response(
        request_id,
        'completed',
        message='Password set and registration synchronized' if ice_synced else 'Password hash stored (Murmur sync skipped)',
        user_id=mumble_user.user_id,
        server_name=server.name,
        murmur_userid=murmur_userid,
        password=password,
        password_generated=requested,
        ice_synced=ice_synced,
    )


@csrf_exempt
@require_http_methods(['POST'])
def control_key_bootstrap(request):
    try:
        auth_source = _require_control_auth(request)
        payload, request_id, requested_by, is_super = _sync_context(request)
        _require_requested_by(requested_by)
        _require_super(is_super)
        new_secret = _read_new_control_secret(payload)
    except _BadRequest as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.BAD_REQUEST)
    except _Unauthorized as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.UNAUTHORIZED)
    except _Forbidden as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.FORBIDDEN)

    try:
        control_key = _control_key_row()
    except Exception as exc:  # noqa: BLE001
        return _response(
            request_id,
            'failed',
            message=f'Control key table is unavailable: {exc}',
            code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
    if control_key.shared_secret:
        return _response(
            request_id,
            'rejected',
            message='Control key already exists; use /v1/control-key/rotate',
            code=HTTPStatus.CONFLICT,
            key_source='db',
        )

    control_key.shared_secret = new_secret
    control_key.save(update_fields=['shared_secret', 'updated_at'])

    return _response(
        request_id,
        'completed',
        message='Control key bootstrapped',
        key_source='db',
        previous_key_source=auth_source,
    )


@csrf_exempt
@require_http_methods(['POST'])
def control_key_rotate(request):
    try:
        auth_source = _require_control_auth(request)
        payload, request_id, requested_by, is_super = _sync_context(request)
        _require_requested_by(requested_by)
        _require_super(is_super)
        new_secret = _read_new_control_secret(payload)
    except _BadRequest as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.BAD_REQUEST)
    except _Unauthorized as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.UNAUTHORIZED)
    except _Forbidden as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.FORBIDDEN)

    try:
        control_key = _control_key_row()
    except Exception as exc:  # noqa: BLE001
        return _response(
            request_id,
            'failed',
            message=f'Control key table is unavailable: {exc}',
            code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
    had_key = bool(control_key.shared_secret)
    control_key.shared_secret = new_secret
    control_key.save(update_fields=['shared_secret', 'updated_at'])

    return _response(
        request_id,
        'completed',
        message='Control key rotated' if had_key else 'Control key created',
        key_source='db',
        previous_key_source=auth_source,
    )


@require_http_methods(['GET'])
def control_key_status(request):
    _, source = _configured_control_secret()
    try:
        row = ControlChannelKey.objects.filter(name=_CONTROL_KEY_NAME).only('id', 'updated_at', 'created_at').first()
    except Exception:  # noqa: BLE001
        row = None
    return JsonResponse(
        {
            'status': 'completed',
            'request_id': now().strftime('%Y%m%dT%H%M%SZ'),
            'mode': source,
            'has_db_key': bool(row),
            'uses_env_bootstrap': source == 'env',
            'updated_at': row.updated_at.isoformat() if row else None,
            'created_at': row.created_at.isoformat() if row else None,
        }
    )


@require_http_methods(['GET'])
def health(request):
    status = 'ok'
    details: dict[str, Any] = {'bg_db': 'ok'}
    _, control_mode = _configured_control_secret()
    details['control_mode'] = control_mode

    try:
        MumbleServer.objects.exists()
    except Exception as exc:  # noqa: BLE001
        status = 'error'
        details['bg_db'] = f'error: {exc}'

    from bg.crypto import status as crypto_status
    details['crypto'] = crypto_status()

    return JsonResponse(
        {
            'status': status,
            'details': details,
            'timestamp': now().isoformat(),
            'request_id': now().strftime('%Y%m%dT%H%M%SZ'),
        }
    )


@require_http_methods(['GET'])
def servers(request):
    rows = list(
        MumbleServer.objects.values(
            'id',
            'name',
            'address',
            'ice_host',
            'ice_port',
            'virtual_server_id',
            'is_active',
        ).order_by('display_order', 'name')
    )
    return JsonResponse(
        {
            'status': 'completed',
            'request_id': now().strftime('%Y%m%dT%H%M%SZ'),
            'servers': rows,
        }
    )


@require_http_methods(['GET'])
def registrations(request):
    payload = _PILOT_PROBE_SERVICE.registrations_payload()
    return JsonResponse(payload)


@require_http_methods(['GET'])
def pilot(request, pkid: int):
    payload = _PILOT_PROBE_SERVICE.pilot_payload(pkid)
    if payload is None:
        return _response('unknown', 'not_found', message='No registration records found', code=HTTPStatus.NOT_FOUND)
    return JsonResponse(payload)


_VALID_ENTITY_TYPES = {ENTITY_TYPE_ALLIANCE, ENTITY_TYPE_CORPORATION, ENTITY_TYPE_PILOT}


def _validate_access_rules(rules: list[Any]) -> list[dict[str, Any]]:
    if not isinstance(rules, list):
        raise _BadRequest('rules must be a list')
    validated = []
    seen_ids = set()
    for idx, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise _BadRequest(f'rules[{idx}] must be an object')
        entity_id = rule.get('entity_id')
        if entity_id is None:
            raise _BadRequest(f'rules[{idx}].entity_id is required')
        entity_id = _coerce_int(entity_id, field=f'rules[{idx}].entity_id')
        if entity_id in seen_ids:
            raise _BadRequest(f'rules[{idx}].entity_id={entity_id} is duplicated')
        seen_ids.add(entity_id)
        entity_type = rule.get('entity_type', '')
        if entity_type not in _VALID_ENTITY_TYPES:
            raise _BadRequest(
                f'rules[{idx}].entity_type must be one of: {", ".join(sorted(_VALID_ENTITY_TYPES))}'
            )
        deny = rule.get('deny', False)
        if not isinstance(deny, bool):
            raise _BadRequest(f'rules[{idx}].deny must be a boolean')
        validated.append({
            'entity_id': entity_id,
            'entity_type': entity_type,
            'deny': deny,
            'note': str(rule.get('note', '') or '').strip(),
            'created_by': str(rule.get('created_by', '') or '').strip(),
        })
    return validated


@csrf_exempt
@require_http_methods(['POST'])
def access_rules_sync(request):
    """
    Replace the full access rule set with the payload from FG.

    This is a full-table sync: BG's access rules are replaced entirely by
    whatever FG sends. Rules not in the payload are deleted.

    BG ACL audit rows are appended only when the incoming rules produce a state delta.
    """
    try:
        auth_source = _require_control_auth(request)
        payload, request_id, requested_by, is_super = _sync_context(request)
        _require_requested_by(requested_by)
        _require_super(is_super)
        rules = payload.get('rules')
        if rules is None:
            raise _BadRequest('rules is required')
        validated = _validate_access_rules(rules)
        del auth_source
    except _BadRequest as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.BAD_REQUEST)
    except _Unauthorized as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.UNAUTHORIZED)
    except _Forbidden as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.FORBIDDEN)

    existing = {
        row['entity_id']: row
        for row in AccessRule.objects.values('entity_id', 'entity_type', 'deny', 'note', 'created_by')
    }
    incoming = {rule['entity_id']: rule for rule in validated}

    created_ids = sorted(set(incoming) - set(existing))
    deleted_ids = sorted(set(existing) - set(incoming))
    updated_ids = sorted(
        entity_id
        for entity_id in (set(existing) & set(incoming))
        if (
            existing[entity_id]['entity_type'] != incoming[entity_id]['entity_type']
            or bool(existing[entity_id]['deny']) != bool(incoming[entity_id]['deny'])
            or str(existing[entity_id]['note'] or '') != str(incoming[entity_id]['note'] or '')
            or str(existing[entity_id]['created_by'] or '') != str(incoming[entity_id]['created_by'] or '')
        )
    )

    if not created_ids and not updated_ids and not deleted_ids:
        return _response(
            request_id,
            'completed',
            message='Access rules already synchronized (no changes)',
            created=0,
            updated=0,
            deleted=0,
            total=len(validated),
            noop=True,
        )

    synced_at = now()
    with transaction.atomic():
        for entity_id in created_ids:
            rule = incoming[entity_id]
            AccessRule.objects.create(
                entity_id=rule['entity_id'],
                entity_type=rule['entity_type'],
                deny=rule['deny'],
                note=rule['note'],
                created_by=rule['created_by'],
                synced_at=synced_at,
            )

        for entity_id in updated_ids:
            rule = incoming[entity_id]
            AccessRule.objects.filter(entity_id=entity_id).update(
                entity_type=rule['entity_type'],
                deny=rule['deny'],
                note=rule['note'],
                created_by=rule['created_by'],
                synced_at=synced_at,
            )

        deleted_count, _ = AccessRule.objects.filter(entity_id__in=deleted_ids).delete()

        append_bg_audit(
            action=BG_AUDIT_ACTION_ACL_SYNC,
            request_id=request_id,
            requested_by=requested_by,
            source='access_rules_sync',
            metadata={
                'created': len(created_ids),
                'updated': len(updated_ids),
                'deleted': int(deleted_count),
                'total': len(validated),
                'created_ids': created_ids,
                'updated_ids': updated_ids,
                'deleted_ids': deleted_ids,
            },
        )

    return _response(
        request_id,
        'completed',
        message='Access rules synchronized',
        created=len(created_ids),
        updated=len(updated_ids),
        deleted=int(deleted_count),
        total=len(validated),
        noop=False,
    )


@require_http_methods(['GET'])
def access_rules(request):
    """Return the current access rule set."""
    rows = list(
        AccessRule.objects.values(
            'entity_id', 'entity_type', 'deny', 'note', 'created_by', 'synced_at', 'updated_at',
        ).order_by('entity_type', 'entity_id')
    )
    for row in rows:
        if row['synced_at']:
            row['synced_at'] = row['synced_at'].isoformat()
        if row['updated_at']:
            row['updated_at'] = row['updated_at'].isoformat()
    return JsonResponse({
        'status': 'completed',
        'request_id': now().strftime('%Y%m%dT%H%M%SZ'),
        'rules': rows,
        'rule_count': len(rows),
    })


def _reconcile_murmur_with_bg_state(*, request_id: str, requested_by: str) -> dict[str, Any]:
    """Converge Murmur registrations to BG active/inactive state."""
    summary: dict[str, Any] = {
        'enabled': True,
        'created': 0,
        'disabled': 0,
        'enabled_count': 0,
        'already_present': 0,
        'already_disabled': 0,
        'missing': 0,
        'errors': [],
    }

    rows = list(
        MumbleUser.objects.select_related('server').filter(server__is_active=True).order_by('server_id', 'user_id')
    )
    for mumble_user in rows:
        server_name = mumble_user.server.name
        if mumble_user.is_active:
            try:
                sync_result = sync_murmur_registration(
                    mumble_user,
                    create_password=_new_password(),
                    return_details=True,
                )
            except MurmurSyncError as exc:
                summary['errors'].append(f'active user_id={mumble_user.user_id}: {exc}')
                continue

            murmur_userid = sync_result.get('murmur_userid')
            created = bool(sync_result.get('created', False))
            reenabled = bool(sync_result.get('reenabled', False))
            if murmur_userid is not None and mumble_user.mumble_userid != int(murmur_userid):
                mumble_user.mumble_userid = int(murmur_userid)
                mumble_user.save(update_fields=['mumble_userid', 'updated_at'])

            if created:
                summary['created'] += 1
                append_bg_audit(
                    action=BG_AUDIT_ACTION_PILOT_CREATE,
                    request_id=request_id,
                    requested_by=requested_by,
                    source='provision_reconcile',
                    user_id=mumble_user.user_id,
                    server_name=server_name,
                    metadata={
                        'murmur_userid': murmur_userid,
                        'username': mumble_user.username,
                    },
                )
            else:
                summary['already_present'] += 1
            if reenabled:
                summary['enabled_count'] += 1
                append_bg_audit(
                    action=BG_AUDIT_ACTION_PILOT_ENABLE,
                    request_id=request_id,
                    requested_by=requested_by,
                    source='provision_reconcile',
                    user_id=mumble_user.user_id,
                    server_name=server_name,
                    metadata={
                        'murmur_userid': murmur_userid,
                        'username': mumble_user.username,
                    },
                )
            continue

        try:
            disabled_result = disable_murmur_registration(mumble_user)
        except MurmurSyncError as exc:
            summary['errors'].append(f'inactive user_id={mumble_user.user_id}: {exc}')
            continue

        murmur_userid = disabled_result.get('murmur_userid')
        if murmur_userid is None:
            summary['missing'] += 1
            continue
        if mumble_user.mumble_userid != int(murmur_userid):
            mumble_user.mumble_userid = int(murmur_userid)
            mumble_user.save(update_fields=['mumble_userid', 'updated_at'])

        if bool(disabled_result.get('changed', False)):
            summary['disabled'] += 1
            append_bg_audit(
                action=BG_AUDIT_ACTION_PILOT_DISABLE,
                request_id=request_id,
                requested_by=requested_by,
                source='provision_reconcile',
                user_id=mumble_user.user_id,
                server_name=server_name,
                metadata={
                    'murmur_userid': murmur_userid,
                    'username': mumble_user.username,
                },
            )
        else:
            summary['already_disabled'] += 1

    return summary


@csrf_exempt
@require_http_methods(['POST'])
def provision(request):
    """Evaluate eligibility and provision MumbleUser rows."""
    try:
        auth_source = _require_control_auth(request)
        payload, request_id, requested_by, is_super = _sync_context(request)
        _require_requested_by(requested_by)
        del auth_source
    except _BadRequest as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.BAD_REQUEST)
    except _Unauthorized as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.UNAUTHORIZED)

    dry_run = bool(payload.get('dry_run', False))
    reconcile_murmur = bool(payload.get('reconcile', True))

    from bg.authd.service import get_pilot_db_connection
    from bg.db import PilotDBError
    from bg.provisioner import provision_registrations

    try:
        conn = get_pilot_db_connection()
    except PilotDBError as exc:
        return _response(
            request_id, 'failed',
            message=f'Cannot connect to pilot source: {exc}',
            code=HTTPStatus.BAD_GATEWAY,
        )

    try:
        result = provision_registrations(conn, dry_run=dry_run)
    except Exception as exc:
        return _response(
            request_id, 'failed',
            message=f'Provisioning failed: {exc}',
            code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
    finally:
        conn.close()

    murmur_reconcile: dict[str, Any] = {
        'enabled': bool(reconcile_murmur),
        'created': 0,
        'disabled': 0,
        'already_present': 0,
        'already_disabled': 0,
        'missing': 0,
        'errors': [],
    }
    if not dry_run and reconcile_murmur:
        murmur_reconcile = _reconcile_murmur_with_bg_state(
            request_id=request_id,
            requested_by=requested_by,
        )

    return _response(
        request_id, 'completed',
        message='Provisioning complete',
        dry_run=dry_run,
        murmur_reconcile=murmur_reconcile,
        **result.to_dict(),
    )


@require_http_methods(['GET'])
def public_key(request):
    """Serve BG's public key for FG to encrypt passwords."""
    from bg.crypto import is_available, get_public_key_pem
    if not is_available():
        return JsonResponse(
            {'status': 'not_configured', 'message': 'No public key available'},
            status=503,
        )
    return HttpResponse(
        get_public_key_pem(),
        content_type='application/x-pem-file',
    )
