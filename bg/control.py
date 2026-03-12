"""HTTP control API for the fg/bg boundary."""

import json
import secrets
from http import HTTPStatus
from typing import Any

from django.http import JsonResponse
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from bg.passwords import build_murmur_password_record
from bg.pilot.registrations import (
    MumbleSyncError,
    sync_live_admin_membership,
    sync_mumble_registration,
    unregister_mumble_registration,
)
from bg.state.models import MumbleServer, MumbleUser


class _BadRequest(ValueError):
    """Raised when a control request is malformed."""


class _NotFound(ValueError):
    """Raised when requested entities do not exist."""


_PASSWORD_CHARS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'


def _new_password(length: int = 16) -> str:
    return ''.join(secrets.choice(_PASSWORD_CHARS) for _ in range(length))


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


def _coerce_session_ids(payload: dict[str, Any]) -> list[int]:
    session_ids = payload.get('session_ids')
    if session_ids is None:
        return []
    if not isinstance(session_ids, (list, tuple)):
        raise _BadRequest('session_ids must be a list')
    normalized = [_coerce_int(session_id, field='session_ids') for session_id in session_ids]
    return [session_id for session_id in normalized if session_id > 0]


def _read_password(payload: dict[str, Any]) -> str | None:
    if 'password' not in payload:
        return None
    password = payload.get('password')
    if not isinstance(password, str) or not password:
        raise _BadRequest('password must be a non-empty string')
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
        return password
    return None


def _resolve_server(payload: dict[str, Any]) -> MumbleServer:
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


def _resolve_mumble_user(*, server: MumbleServer, payload: dict[str, Any]) -> MumbleUser:
    pkid = payload.get('pkid')
    if pkid is None:
        raise _BadRequest('pkid is required')
    pkid_value = _coerce_int(pkid, field='pkid')
    mumble_user = MumbleUser.objects.filter(user_id=pkid_value, server=server, is_active=True).first()
    if not mumble_user:
        raise _NotFound('Mumble registration not found')
    return mumble_user


def _sync_context(request):
    envelope = _load_json_payload(request)
    outer_payload, payload = _extract_payload_envelope(envelope)
    request_id = _request_id(outer_payload)
    return payload, request_id


@csrf_exempt
@require_http_methods(['POST'])
def registrations_sync(request):
    try:
        payload, request_id = _sync_context(request)
        server = _resolve_server(payload)
        mumble_user = _resolve_mumble_user(server=server, payload=payload)
    except _BadRequest as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.BAD_REQUEST)
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
        mumble_userid = sync_mumble_registration(mumble_user, password=password)
    except MumbleSyncError as exc:
        return _response(
            request_id,
            'failed',
            message=f'Failed to sync registration: {exc}',
            code=HTTPStatus.BAD_GATEWAY,
        )

    if mumble_userid is not None and mumble_user.mumble_userid != mumble_userid:
        mumble_user.mumble_userid = mumble_userid
        mumble_user.save(update_fields=['mumble_userid', 'updated_at'])

    return _response(
        request_id,
        'completed',
        message='Registration synchronized',
        mumble_userid=mumble_user.mumble_userid,
        user_id=mumble_user.user_id,
        server_name=server.name,
    )


@csrf_exempt
@require_http_methods(['POST'])
def registrations_disable(request):
    try:
        payload, request_id = _sync_context(request)
        server = _resolve_server(payload)
        mumble_user = _resolve_mumble_user(server=server, payload=payload)
    except _BadRequest as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.BAD_REQUEST)
    except _NotFound as exc:
        return _response('unknown', 'not_found', message=str(exc), code=HTTPStatus.NOT_FOUND)

    try:
        disabled = unregister_mumble_registration(mumble_user)
    except MumbleSyncError as exc:
        return _response(
            request_id,
            'failed',
            message=f'Failed to disable registration: {exc}',
            code=HTTPStatus.BAD_GATEWAY,
        )

    if disabled:
        mumble_user.mumble_userid = None
        mumble_user.save(update_fields=['mumble_userid', 'updated_at'])

    return _response(
        request_id,
        'completed',
        message='Registration disabled' if disabled else 'No active Murmur registration found',
        disabled=disabled,
        user_id=mumble_user.user_id,
        server_name=server.name,
    )


@csrf_exempt
@require_http_methods(['POST'])
def admin_membership_sync(request):
    try:
        payload, request_id = _sync_context(request)
        server = _resolve_server(payload)
        mumble_user = _resolve_mumble_user(server=server, payload=payload)
        admin = _coerce_bool(payload.get('admin'), field='admin')
        session_ids = _coerce_session_ids(payload)
    except _BadRequest as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.BAD_REQUEST)
    except _NotFound as exc:
        return _response('unknown', 'not_found', message=str(exc), code=HTTPStatus.NOT_FOUND)

    if mumble_user.is_mumble_admin != admin:
        mumble_user.is_mumble_admin = admin
        mumble_user.save(update_fields=['is_mumble_admin', 'updated_at'])

    try:
        synced_sessions = sync_live_admin_membership(mumble_user, session_ids=session_ids)
    except MumbleSyncError as exc:
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
        payload, request_id = _sync_context(request)
        server = _resolve_server(payload)
        mumble_user = _resolve_mumble_user(server=server, payload=payload)
        desired_password = _read_preferred_password(payload)
    except _BadRequest as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.BAD_REQUEST)
    except _NotFound as exc:
        return _response('unknown', 'not_found', message=str(exc), code=HTTPStatus.NOT_FOUND)

    requested = desired_password is None
    password = desired_password if desired_password is not None else _new_password()

    record = build_murmur_password_record(password)
    mumble_user.pwhash = record['pwhash']
    mumble_user.hashfn = record['hashfn']
    mumble_user.pw_salt = record['pw_salt']
    mumble_user.kdf_iterations = record['kdf_iterations']

    try:
        mumble_userid = sync_mumble_registration(mumble_user, password=password)
    except MumbleSyncError as exc:
        return _response(
            request_id,
            'failed',
            message=f'Failed to reset password: {exc}',
            code=HTTPStatus.BAD_GATEWAY,
        )

    if mumble_userid is not None:
        mumble_user.mumble_userid = mumble_userid

    mumble_user.save(update_fields=['pwhash', 'hashfn', 'pw_salt', 'kdf_iterations', 'mumble_userid', 'updated_at'])

    return _response(
        request_id,
        'completed',
        message='Password set and registration synchronized',
        user_id=mumble_user.user_id,
        server_name=server.name,
        mumble_userid=mumble_userid,
        password=password,
        password_generated=requested,
    )


@require_http_methods(['GET'])
def health(request):
    status = 'ok'
    details: dict[str, Any] = {'bg_db': 'ok'}

    try:
        MumbleServer.objects.exists()
    except Exception as exc:  # noqa: BLE001
        status = 'error'
        details['bg_db'] = f'error: {exc}'

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
def pilot(request, pkid: int):
    rows = MumbleUser.objects.filter(user_id=pkid, is_active=True).select_related('server').order_by(
        'server__display_order',
        'server__name',
    )
    if not rows:
        return _response('unknown', 'not_found', message='No registration records found', code=HTTPStatus.NOT_FOUND)

    registrations = []
    for row in rows:
        registrations.append(
            {
                'server_id': row.server_id,
                'server_name': row.server.name,
                'username': row.username,
                'mumble_userid': row.mumble_userid,
                'is_active': row.is_active,
                'is_mumble_admin': row.is_mumble_admin,
                'pw_lastchanged': row.updated_at.isoformat() if row.updated_at else None,
                'last_authenticated': row.last_authenticated.isoformat() if row.last_authenticated else None,
                'last_connected': row.last_connected.isoformat() if row.last_connected else None,
                'last_seen': row.last_seen.isoformat() if row.last_seen else None,
            }
        )

    return JsonResponse(
        {
            'status': 'completed',
            'pkid': pkid,
            'request_id': now().strftime('%Y%m%dT%H%M%SZ'),
            'registrations': registrations,
            'registration_count': len(registrations),
            'timestamp': now().isoformat(),
        }
    )


@csrf_exempt
@require_http_methods(['POST'])
def psk_reset(request):
    try:
        payload, request_id = _sync_context(request)
        server = _resolve_server(payload)
    except _BadRequest as exc:
        return _response('unknown', 'rejected', message=str(exc), code=HTTPStatus.BAD_REQUEST)
    except _NotFound as exc:
        return _response('unknown', 'not_found', message=str(exc), code=HTTPStatus.NOT_FOUND)

    server.ice_secret = None
    server.save(update_fields=['ice_secret'])

    return _response(
        request_id,
        'completed',
        message='Server write secret cleared',
        server_name=server.name,
        server_id=server.id,
    )
