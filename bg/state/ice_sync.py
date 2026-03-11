from bg.ice import load_ice_module


class MumbleSyncError(RuntimeError):
    pass


def _load_slice():
    try:
        return load_ice_module()
    except RuntimeError as exc:
        raise MumbleSyncError(str(exc)) from exc


def _open_target_server(server_config):
    try:
        import Ice
    except ImportError as exc:
        raise MumbleSyncError('ZeroC ICE is not installed in this environment') from exc

    M = _load_slice()
    communicator = Ice.initialize(['--Ice.ImplicitContext=Shared', '--Ice.Default.EncodingVersion=1.0'])
    try:
        if server_config.ice_secret:
            communicator.getImplicitContext().put('secret', server_config.ice_secret)

        proxy = communicator.stringToProxy(
            f'Meta:tcp -h {server_config.ice_host} -p {server_config.ice_port}'
        )
        meta = M.MetaPrx.checkedCast(proxy)
        if not meta:
            raise MumbleSyncError(
                f'Failed to connect to ICE on {server_config.ice_host}:{server_config.ice_port}'
            )
        booted_servers = meta.getBootedServers()
        if not booted_servers:
            raise MumbleSyncError(
                f'No booted Murmur servers found on {server_config.ice_host}:{server_config.ice_port}'
            )

        target = None
        if server_config.virtual_server_id is not None:
            for srv in booted_servers:
                if srv.id() == server_config.virtual_server_id:
                    target = srv
                    break
            if target is None:
                raise MumbleSyncError(
                    f'Configured virtual server ID {server_config.virtual_server_id} was not found on '
                    f'{server_config.ice_host}:{server_config.ice_port}'
                )
        elif len(booted_servers) == 1:
            target = booted_servers[0]
        else:
            raise MumbleSyncError(
                'Multiple Murmur virtual servers are booted on this ICE endpoint; configure virtual_server_id in bg inventory'
            )

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


def _find_existing_userid(server_proxy, username, preferred_userid=None):
    registered = server_proxy.getRegisteredUsers('')
    if preferred_userid is not None and preferred_userid in registered:
        return preferred_userid

    target = (username or '').strip().lower()
    if not target:
        return None

    for registered_userid, registered_name in (registered or {}).items():
        if str(registered_name or '').strip().lower() == target:
            return registered_userid
    return None


def sync_mumble_registration(mumble_user, password=None):
    try:
        communicator, M, server_proxy = _open_target_server(mumble_user.server)
        try:
            target_userid = _find_existing_userid(
                server_proxy,
                mumble_user.username,
                preferred_userid=mumble_user.mumble_userid,
            )
            info = _build_registration_info(M, mumble_user, password=password)
            if target_userid is None:
                target_userid = server_proxy.registerUser(info)
                if target_userid < 0:
                    raise MumbleSyncError(
                        f'Failed to register Murmur user {mumble_user.username} on {mumble_user.server.name}'
                    )
            else:
                server_proxy.updateRegistration(target_userid, info)
            return int(target_userid)
        finally:
            communicator.destroy()
    except MumbleSyncError:
        raise
    except Exception as exc:
        raise MumbleSyncError(
            f'Failed to sync Murmur registration for {mumble_user.username} on {mumble_user.server.name}: {exc}'
        ) from exc


def unregister_mumble_registration(mumble_user):
    try:
        communicator, _, server_proxy = _open_target_server(mumble_user.server)
        try:
            target_userid = _find_existing_userid(
                server_proxy,
                mumble_user.username,
                preferred_userid=mumble_user.mumble_userid,
            )
            if target_userid is None:
                return False
            server_proxy.unregisterUser(int(target_userid))
            return True
        finally:
            communicator.destroy()
    except MumbleSyncError:
        raise
    except Exception as exc:
        raise MumbleSyncError(
            f'Failed to unregister Murmur registration for {mumble_user.username} on {mumble_user.server.name}: {exc}'
        ) from exc


def sync_live_admin_membership(mumble_user):
    from .models import MumbleSession

    session_ids = list(
        MumbleSession.objects.filter(
            server=mumble_user.server,
            mumble_user=mumble_user,
            is_active=True,
        ).order_by('session_id').values_list('session_id', flat=True)
    )
    if not session_ids:
        return 0

    try:
        communicator, _, server_proxy = _open_target_server(mumble_user.server)
        try:
            for session_id in session_ids:
                if mumble_user.is_mumble_admin:
                    server_proxy.addUserToGroup(0, int(session_id), 'admin')
                else:
                    server_proxy.removeUserFromGroup(0, int(session_id), 'admin')
            return len(session_ids)
        finally:
            communicator.destroy()
    except MumbleSyncError:
        raise
    except Exception as exc:
        action = 'grant' if mumble_user.is_mumble_admin else 'revoke'
        raise MumbleSyncError(
            f'Failed to {action} live Murmur admin membership for {mumble_user.username} '
            f'on {mumble_user.server.name}: {exc}'
        ) from exc
