from __future__ import annotations

import logging
import os
import threading
from dataclasses import asdict, dataclass
from typing import Any

from django.conf import settings
from django.db import close_old_connections
from django.utils.timezone import now

from bg.ice import load_ice_module
from bg.ice_meta import build_ice_client_props, connect_meta_with_fallback
from bg.state.models import MumbleServer, MurmurServerInventorySnapshot

logger = logging.getLogger(__name__)

_DEFAULT_FRESHNESS_SECONDS = 600


class MurmurInventoryError(RuntimeError):
    """Raised when a Murmur inventory snapshot cannot be fetched."""


@dataclass(frozen=True)
class InventoryEnvelope:
    snapshot: MurmurServerInventorySnapshot
    source: str
    freshness_seconds: int

    @property
    def is_real_time(self) -> bool:
        if self.snapshot.fetched_at is None:
            return False
        age = (now() - self.snapshot.fetched_at).total_seconds()
        return age < self.freshness_seconds


def inventory_freshness_seconds() -> int:
    raw = (
        os.getenv('BG_MURMUR_INVENTORY_FRESHNESS_SECONDS', '').strip()
        or str(getattr(settings, 'BG_MURMUR_INVENTORY_FRESHNESS_SECONDS', '') or '').strip()
    )
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_FRESHNESS_SECONDS
    return max(1, value)


def _normalize_channel(channel: Any) -> dict[str, Any]:
    return {
        'id': int(channel.id),
        'name': str(channel.name or ''),
        'parent': int(channel.parent),
        'description': str(channel.description or ''),
        'temporary': bool(channel.temporary),
        'position': int(channel.position),
        'links': [int(link_id) for link_id in list(getattr(channel, 'links', []) or [])],
    }


def _normalize_acl(acl: Any) -> dict[str, Any]:
    user_id = int(acl.userid)
    return {
        'apply_here': bool(acl.applyHere),
        'apply_subs': bool(acl.applySubs),
        'inherited': bool(acl.inherited),
        'user_id': None if user_id < 0 else user_id,
        'group': str(acl.group or ''),
        'allow': int(acl.allow),
        'deny': int(acl.deny),
    }


def _normalize_group(group: Any) -> dict[str, Any]:
    return {
        'name': str(group.name or ''),
        'inherit': bool(group.inherit),
        'inheritable': bool(group.inheritable),
        'inherited': bool(group.inherited),
        'add': [int(user_id) for user_id in list(getattr(group, 'add', []) or [])],
        'remove': [int(user_id) for user_id in list(getattr(group, 'remove', []) or [])],
    }


def _sorted_channel_ids(channels: dict[int, dict[str, Any]]) -> list[int]:
    return sorted(
        channels.keys(),
        key=lambda channel_id: (
            _channel_path(channel_id, channels).lower(),
            channel_id,
        ),
    )


def _channel_path(channel_id: int, channels: dict[int, dict[str, Any]]) -> str:
    parts: list[str] = []
    current_id = int(channel_id)
    seen: set[int] = set()
    while current_id in channels and current_id not in seen:
        seen.add(current_id)
        channel = channels[current_id]
        name = str(channel.get('name') or '').strip()
        if current_id == 0:
            break
        if name:
            parts.append(name)
        parent_id = int(channel.get('parent', -1))
        if parent_id < 0:
            break
        current_id = parent_id
    return '/' + '/'.join(reversed(parts))


def _select_target_server(server: MumbleServer):
    try:
        import Ice  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise MurmurInventoryError('ZeroC ICE is not installed in this environment') from exc

    communicator = Ice.initialize(
        build_ice_client_props(
            tls_cert=server.ice_tls_cert or "",
            tls_key=server.ice_tls_key or "",
            tls_ca=server.ice_tls_ca or "",
        )
    )
    try:
        M = load_ice_module()
        meta, protocol, _attempts = connect_meta_with_fallback(
            communicator,
            M,
            host=server.ice_host,
            port=server.ice_port,
            secret=server.ice_secret or "",
        )
        booted_servers = meta.getBootedServers()
        if not booted_servers:
            raise MurmurInventoryError(
                f'No booted Murmur servers found on {server.ice_host}:{server.ice_port}'
            )

        # Rewrite proxy endpoints for remote servers behind NAT.
        if server.ice_host not in ('127.0.0.1', 'localhost', '::1'):
            from bg.ice_meta import rewrite_proxy_host
            booted_servers = [rewrite_proxy_host(communicator, s, server.ice_host, server.ice_port) for s in booted_servers]

        target = None
        if server.virtual_server_id is not None:
            for booted_server in booted_servers:
                if int(booted_server.id()) == int(server.virtual_server_id):
                    target = booted_server
                    break
            if target is None:
                raise MurmurInventoryError(
                    f'virtual_server_id={server.virtual_server_id} not found on {server.ice_host}:{server.ice_port}'
                )
        elif len(booted_servers) == 1:
            target = booted_servers[0]
        else:
            raise MurmurInventoryError(
                'Multiple virtual servers are booted; configure virtual_server_id on bg MumbleServer rows'
            )

        if server.ice_secret:
            target = target.ice_context({"secret": server.ice_secret})
        return communicator, protocol, target
    except Exception:
        communicator.destroy()
        raise


def fetch_server_inventory(server: MumbleServer) -> tuple[dict[str, Any], str]:
    communicator, protocol, target = _select_target_server(server)
    try:
        channel_map = target.getChannels() or {}
        normalized_channels = {
            int(channel_id): _normalize_channel(channel)
            for channel_id, channel in channel_map.items()
        }
        channel_paths = {cid: _channel_path(cid, normalized_channels) for cid in normalized_channels}
        exported_channels: list[dict[str, Any]] = []
        acl_total = 0
        group_total = 0
        root_groups: list[dict[str, Any]] = []

        for channel_id in _sorted_channel_ids(normalized_channels):
            channel = normalized_channels[channel_id]
            acls, groups, inherit_acl = target.getACL(int(channel_id))
            normalized_acls = [_normalize_acl(acl) for acl in list(acls or [])]
            normalized_groups = [_normalize_group(group) for group in list(groups or [])]
            acl_total += len(normalized_acls)
            group_total += len(normalized_groups)
            if channel_id == 0:
                root_groups = sorted(normalized_groups, key=lambda item: item['name'].lower())

            exported_channels.append(
                {
                    **channel,
                    'path': channel_paths[channel_id],
                    'link_paths': [
                        channel_paths[target_id]
                        for target_id in channel.get('links', [])
                        if target_id in channel_paths
                    ],
                    'inherit_acl': bool(inherit_acl),
                    'acls': normalized_acls,
                    'groups': normalized_groups,
                }
            )

        payload = {
            'server': {
                'id': int(server.pk),
                'name': str(server.name or ''),
                'address': str(server.address or ''),
                'ice_host': str(server.ice_host or ''),
                'ice_port': int(server.ice_port),
                'virtual_server_id': int(server.virtual_server_id) if server.virtual_server_id is not None else None,
            },
            'summary': {
                'channel_count': len(exported_channels),
                'acl_count': acl_total,
                'group_count': group_total,
                'root_group_count': len(root_groups),
            },
            'root_groups': root_groups,
            'channels': exported_channels,
        }
        return payload, protocol
    finally:
        communicator.destroy()


def get_server_inventory_snapshot(
    server: MumbleServer,
    *,
    force_refresh: bool = False,
) -> InventoryEnvelope:
    freshness_seconds = inventory_freshness_seconds()
    snapshot, _created = MurmurServerInventorySnapshot.objects.get_or_create(server=server)

    fresh = False
    if snapshot.fetched_at is not None:
        age_seconds = (now() - snapshot.fetched_at).total_seconds()
        fresh = age_seconds < freshness_seconds and snapshot.fetch_status == 'ok' and bool(snapshot.payload)

    if fresh and not force_refresh:
        return InventoryEnvelope(snapshot=snapshot, source='cache', freshness_seconds=freshness_seconds)

    try:
        payload, protocol = fetch_server_inventory(server)
    except Exception as exc:  # noqa: BLE001
        wrapped_exc = exc if isinstance(exc, MurmurInventoryError) else MurmurInventoryError(str(exc))
        snapshot.fetch_status = 'error'
        snapshot.fetch_error = str(wrapped_exc)
        snapshot.save(update_fields=['fetch_status', 'fetch_error', 'updated_at'])
        if snapshot.payload and snapshot.fetched_at is not None:
            return InventoryEnvelope(snapshot=snapshot, source='stale-cache', freshness_seconds=freshness_seconds)
        raise wrapped_exc

    snapshot.payload = payload
    snapshot.protocol = protocol
    snapshot.fetch_status = 'ok'
    snapshot.fetch_error = ''
    snapshot.fetched_at = now()
    snapshot.save(update_fields=['payload', 'protocol', 'fetch_status', 'fetch_error', 'fetched_at', 'updated_at'])
    return InventoryEnvelope(snapshot=snapshot, source='live', freshness_seconds=freshness_seconds)


def _warm_other_server_inventories(selected_server_id: int) -> None:
    close_old_connections()
    try:
        for server in MumbleServer.objects.filter(is_active=True).exclude(pk=selected_server_id).order_by('display_order', 'name'):
            try:
                get_server_inventory_snapshot(server, force_refresh=False)
            except Exception:  # noqa: BLE001
                logger.exception('Failed to warm Murmur inventory cache for server_id=%s', server.pk)
    finally:
        close_old_connections()


def warm_other_server_inventories_async(selected_server_id: int) -> bool:
    other_count = MumbleServer.objects.filter(is_active=True).exclude(pk=selected_server_id).count()
    if other_count <= 0:
        return False
    thread = threading.Thread(
        target=_warm_other_server_inventories,
        args=(int(selected_server_id),),
        name=f'bg-murmur-inventory-warm-{selected_server_id}',
        daemon=True,
    )
    thread.start()
    return True


__all__ = [
    'InventoryEnvelope',
    'MurmurInventoryError',
    'fetch_server_inventory',
    'get_server_inventory_snapshot',
    'inventory_freshness_seconds',
    'warm_other_server_inventories_async',
]
