from bg.ice import load_ice_module
from bg.ice_meta import build_ice_client_props, connect_meta_with_fallback
import hashlib


class MurmurSyncError(RuntimeError):
    pass


_DISABLED_COMMENT_MARKER = '[bg-disabled]'


def _load_slice():
    try:
        return load_ice_module()
    except RuntimeError as exc:
        raise MurmurSyncError(str(exc)) from exc


def _open_target_server(server_config):
    try:
        import Ice
    except ImportError as exc:
        raise MurmurSyncError('ZeroC ICE is not installed in this environment') from exc

    M = _load_slice()
    communicator = Ice.initialize(
        build_ice_client_props(
            tls_cert=getattr(server_config, "ice_tls_cert", "") or "",
            tls_key=getattr(server_config, "ice_tls_key", "") or "",
            tls_ca=getattr(server_config, "ice_tls_ca", "") or "",
        )
    )
    try:
        meta, _protocol, _attempts = connect_meta_with_fallback(
            communicator,
            M,
            host=server_config.ice_host,
            port=server_config.ice_port,
            secret=server_config.ice_secret or "",
        )
        booted_servers = meta.getBootedServers()
        if not booted_servers:
            raise MurmurSyncError(
                f'No booted Murmur servers found on {server_config.ice_host}:{server_config.ice_port}'
            )

        ice_secret = server_config.ice_secret or ""
        target = None
        if server_config.virtual_server_id is not None:
            for srv in booted_servers:
                if srv.id() == server_config.virtual_server_id:
                    target = srv
                    break
            if target is None:
                raise MurmurSyncError(
                    f'Configured virtual server ID {server_config.virtual_server_id} was not found on '
                    f'{server_config.ice_host}:{server_config.ice_port}'
                )
        elif len(booted_servers) == 1:
            target = booted_servers[0]
        else:
            raise MurmurSyncError(
                'Multiple Murmur virtual servers are booted on this ICE endpoint; configure virtual_server_id in bg inventory'
            )

        if ice_secret and target is not None:
            target = target.ice_context({"secret": ice_secret})
        return communicator, M, target
    except Exception:
        communicator.destroy()
        raise


def _build_registration_info(M, mumble_user, password=None):
    info = {
        M.UserInfo.UserName: mumble_user.username,
    }
    if password:
        info[M.UserInfo.UserPassword] = password
    if mumble_user.certhash:
        info[M.UserInfo.UserHash] = mumble_user.certhash
    if mumble_user.display_name:
        info[M.UserInfo.UserComment] = mumble_user.display_name
    return info


def _find_existing_userid(server_proxy, username, preferred_userid=None, aliases=None):
    registered = server_proxy.getRegisteredUsers('')
    if preferred_userid is not None and preferred_userid in registered:
        return preferred_userid

    candidates = {
        str(value or '').strip().lower()
        for value in [username, *(aliases or [])]
        if str(value or '').strip()
    }
    if not candidates:
        return None

    for registered_userid, registered_name in (registered or {}).items():
        if str(registered_name or '').strip().lower() in candidates:
            return registered_userid
    return None


def sync_murmur_registration(mumble_user, password=None, *, create_password=None, return_details=False):
    try:
        communicator, M, server_proxy = _open_target_server(mumble_user.server)
        try:
            target_userid = _find_existing_userid(
                server_proxy,
                mumble_user.username,
                preferred_userid=mumble_user.mumble_userid,
                aliases=[mumble_user.display_name],
            )
            created = target_userid is None
            effective_password = password
            if target_userid is None and effective_password is None:
                effective_password = create_password
            info = _build_registration_info(M, mumble_user, password=effective_password)
            reenabled = False
            if target_userid is None:
                target_userid = server_proxy.registerUser(info)
                if target_userid < 0:
                    raise MurmurSyncError(
                        f'Failed to register Murmur user {mumble_user.username} on {mumble_user.server.name}'
                    )
            else:
                try:
                    current = server_proxy.getRegistration(int(target_userid))
                except Exception:  # noqa: BLE001
                    current = {}
                current_comment = str(current.get(M.UserInfo.UserComment, '') or '')
                if current_comment == _DISABLED_COMMENT_MARKER:
                    reenabled = True
                server_proxy.updateRegistration(target_userid, info)
            if return_details:
                return {
                    'murmur_userid': int(target_userid),
                    'created': bool(created),
                    'reenabled': bool(reenabled),
                }
            return int(target_userid)
        finally:
            communicator.destroy()
    except MurmurSyncError:
        raise
    except Exception as exc:
        raise MurmurSyncError(
            f'Failed to sync Murmur registration for {mumble_user.username} on {mumble_user.server.name}: {exc}'
        ) from exc


def _disabled_password_for(mumble_user) -> str:
    material = f'{mumble_user.user_id}:{mumble_user.server_id}:{mumble_user.pwhash or ""}'
    digest = hashlib.sha256(material.encode('utf-8')).hexdigest()
    return f'dis-{digest[:28]}'


def disable_murmur_registration(mumble_user):
    """Keep a Murmur registration row but move it to disabled state."""
    try:
        communicator, M, server_proxy = _open_target_server(mumble_user.server)
        try:
            target_userid = _find_existing_userid(
                server_proxy,
                mumble_user.username,
                preferred_userid=mumble_user.mumble_userid,
                aliases=[mumble_user.display_name],
            )
            if target_userid is None:
                return {'changed': False, 'murmur_userid': None, 'already_disabled': False}

            try:
                current = server_proxy.getRegistration(int(target_userid))
            except Exception:  # noqa: BLE001
                current = {}

            current_comment = str(current.get(M.UserInfo.UserComment, '') or '')
            current_hash = str(current.get(M.UserInfo.UserHash, '') or '')
            already_disabled = (
                current_comment == _DISABLED_COMMENT_MARKER
                and not current_hash
            )
            if already_disabled:
                return {'changed': False, 'murmur_userid': int(target_userid), 'already_disabled': True}

            disabled_password = _disabled_password_for(mumble_user)
            info = {
                M.UserInfo.UserName: mumble_user.username,
                M.UserInfo.UserPassword: disabled_password,
                M.UserInfo.UserHash: '',
                M.UserInfo.UserComment: _DISABLED_COMMENT_MARKER,
            }
            server_proxy.updateRegistration(int(target_userid), info)
            return {'changed': True, 'murmur_userid': int(target_userid), 'already_disabled': False}
        finally:
            communicator.destroy()
    except MurmurSyncError:
        raise
    except Exception as exc:
        raise MurmurSyncError(
            f'Failed to disable Murmur registration for {mumble_user.username} on {mumble_user.server.name}: {exc}'
        ) from exc


def unregister_murmur_registration(mumble_user):
    try:
        communicator, _, server_proxy = _open_target_server(mumble_user.server)
        try:
            target_userid = _find_existing_userid(
                server_proxy,
                mumble_user.username,
                preferred_userid=mumble_user.mumble_userid,
                aliases=[mumble_user.display_name],
            )
            if target_userid is None:
                return False
            server_proxy.unregisterUser(int(target_userid))
            return True
        finally:
            communicator.destroy()
    except MurmurSyncError:
        raise
    except Exception as exc:
        raise MurmurSyncError(
            f'Failed to unregister Murmur registration for {mumble_user.username} on {mumble_user.server.name}: {exc}'
        ) from exc


def _coerce_session_ids(session_ids):
    normalized = []
    for value in (session_ids or []):
        try:
            session_id = int(value)
        except (TypeError, ValueError):
            raise MurmurSyncError(f'Invalid session_id in payload: {value!r}') from None
        if session_id > 0:
            normalized.append(session_id)
    return normalized


def disconnect_live_sessions(mumble_user, *, reason='Registration updated; reconnect required'):
    from bg.pulse.service import mark_session_disconnected
    from bg.state.models import MumbleSession

    session_ids = list(
        MumbleSession.objects.filter(
            server=mumble_user.server,
            mumble_user=mumble_user,
            is_active=True,
        ).order_by('session_id').values_list('session_id', flat=True)
    )
    if not session_ids:
        return {'requested': 0, 'kicked': 0, 'errors': []}

    reason_text = str(reason or '').strip() or 'Registration updated; reconnect required'
    kicked = 0
    errors: list[str] = []
    try:
        communicator, _, server_proxy = _open_target_server(mumble_user.server)
        try:
            for session_id in session_ids:
                try:
                    server_proxy.kickUser(int(session_id), reason_text)
                    kicked += 1
                    mark_session_disconnected(mumble_user.server, int(session_id))
                except Exception as exc:  # noqa: BLE001
                    errors.append(f'session {int(session_id)}: {exc}')
        finally:
            communicator.destroy()
    except MurmurSyncError:
        raise
    except Exception as exc:
        raise MurmurSyncError(
            f'Failed to disconnect live sessions for {mumble_user.username} on {mumble_user.server.name}: {exc}'
        ) from exc

    return {'requested': len(session_ids), 'kicked': kicked, 'errors': errors}


def sync_live_admin_membership(mumble_user, *, session_ids=None, old_groups=None):
    from bg.state.models import MumbleSession

    if session_ids is None:
        session_ids = list(
            MumbleSession.objects.filter(
                server=mumble_user.server,
                mumble_user=mumble_user,
                is_active=True,
            ).order_by('session_id').values_list('session_id', flat=True)
        )
    else:
        session_ids = _coerce_session_ids(session_ids)

    if not session_ids:
        return 0

    new_group_set = {g.strip() for g in (mumble_user.groups or '').split(',') if g.strip()}
    if mumble_user.is_mumble_admin:
        new_group_set.add('admin')
    else:
        new_group_set.discard('admin')

    if old_groups is not None:
        old_group_set = {g.strip() for g in old_groups.split(',') if g.strip()}
        groups_to_add = new_group_set - old_group_set
        groups_to_remove = old_group_set - new_group_set
    else:
        groups_to_add = new_group_set
        groups_to_remove = {'admin'} - new_group_set

    if not groups_to_add and not groups_to_remove:
        return len(session_ids)

    sorted_add = sorted(groups_to_add)
    sorted_remove = sorted(groups_to_remove)

    try:
        communicator, _, server_proxy = _open_target_server(mumble_user.server)
        try:
            for session_id in session_ids:
                for group in sorted_add:
                    server_proxy.addUserToGroup(0, int(session_id), group)
                for group in sorted_remove:
                    server_proxy.removeUserFromGroup(0, int(session_id), group)
            return len(session_ids)
        finally:
            communicator.destroy()
    except MurmurSyncError:
        raise
    except Exception as exc:
        raise MurmurSyncError(
            f'Failed to sync live Murmur group membership for {mumble_user.username} '
            f'on {mumble_user.server.name}: {exc}'
        ) from exc
