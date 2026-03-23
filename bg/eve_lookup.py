"""Lazy ESI lookup/cache helpers for EVE object dictionary rows."""

from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils.timezone import now

from bg.state.models import EveObject
from fgbg_common.entity_types import CATEGORY_TO_TYPE

logger = logging.getLogger(__name__)

_BOOL_TRUE = {'1', 'true', 'yes', 'on'}


def _lookup_enabled() -> bool:
    env_value = os.getenv('BG_ESI_LOOKUP_ENABLED')
    if env_value is not None:
        return str(env_value).strip().lower() in _BOOL_TRUE
    return bool(getattr(settings, 'BG_ESI_LOOKUP_ENABLED', True))


def _esi_base_url() -> str:
    return str(
        os.getenv('ESI_BASE_URL')
        or getattr(settings, 'ESI_BASE_URL', '')
        or 'https://esi.evetech.net/latest'
    ).rstrip('/')


def _esi_datasource() -> str:
    return str(os.getenv('ESI_DATASOURCE') or getattr(settings, 'ESI_DATASOURCE', '') or 'tranquility').strip()


def _esi_timeout_seconds() -> int:
    raw = str(os.getenv('ESI_TIMEOUT_SECONDS') or getattr(settings, 'ESI_TIMEOUT_SECONDS', '') or '8').strip()
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 8


def _request_json(path: str, *, method: str = 'GET', payload: Any | None = None) -> Any:
    url = f'{_esi_base_url()}{path}'
    body = None
    headers: dict[str, str] = {}
    if payload is not None:
        body = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    request = Request(url, data=body, method=method, headers=headers)
    with urlopen(request, timeout=_esi_timeout_seconds()) as response:
        raw = response.read()
    if not raw:
        return None
    return json.loads(raw.decode('utf-8'))


def _safe_request_json(path: str, *, method: str = 'GET', payload: Any | None = None) -> Any | None:
    try:
        return _request_json(path, method=method, payload=payload)
    except (HTTPError, URLError, ValueError, TimeoutError) as exc:
        logger.warning('ESI lookup failed for %s %s: %s', method, path, exc)
        return None


def _lookup_names_by_id(entity_ids: set[int]) -> dict[int, dict[str, str]]:
    if not entity_ids:
        return {}
    ds = _esi_datasource()
    payload = sorted(int(entity_id) for entity_id in entity_ids)
    rows = _safe_request_json(
        f'/universe/names/?datasource={ds}',
        method='POST',
        payload=payload,
    )
    if not isinstance(rows, list):
        return {}
    results: dict[int, dict[str, str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            entity_id = int(row.get('id'))
        except (TypeError, ValueError):
            continue
        category = str(row.get('category') or '').strip()
        name = str(row.get('name') or '').strip()
        if not category:
            continue
        results[entity_id] = {
            'category': category,
            'name': name,
        }
    return results


def _lookup_corporation_details(corporation_ids: set[int]) -> dict[int, dict[str, str]]:
    ds = _esi_datasource()
    details: dict[int, dict[str, str]] = {}
    for corporation_id in sorted(int(corporation_id) for corporation_id in corporation_ids):
        row = _safe_request_json(f'/corporations/{corporation_id}/?datasource={ds}')
        if not isinstance(row, dict):
            continue
        details[corporation_id] = {
            'name': str(row.get('name') or '').strip(),
            'ticker': str(row.get('ticker') or '').strip(),
        }
    return details


def _lookup_alliance_details(alliance_ids: set[int]) -> dict[int, dict[str, str]]:
    ds = _esi_datasource()
    details: dict[int, dict[str, str]] = {}
    for alliance_id in sorted(int(alliance_id) for alliance_id in alliance_ids):
        row = _safe_request_json(f'/alliances/{alliance_id}/?datasource={ds}')
        if not isinstance(row, dict):
            continue
        details[alliance_id] = {
            'name': str(row.get('name') or '').strip(),
            'ticker': str(row.get('ticker') or '').strip(),
        }
    return details


def resolve_and_cache_eve_objects(
    *,
    character_ids: set[int],
    corporation_ids: set[int],
    alliance_ids: set[int],
) -> None:
    """Populate BG EveObject cache from ESI for IDs missing local dictionary rows."""
    if not _lookup_enabled():
        return

    all_ids = {int(i) for i in character_ids | corporation_ids | alliance_ids}
    if not all_ids:
        return

    timestamp = now()
    existing_by_id = {
        int(row.entity_id): row
        for row in EveObject.objects.filter(entity_id__in=all_ids)
    }

    ids_missing_name = {
        entity_id
        for entity_id in all_ids
        if entity_id not in existing_by_id or not str(existing_by_id[entity_id].name or '').strip()
    }
    names_by_id = _lookup_names_by_id(ids_missing_name)
    for entity_id, data in names_by_id.items():
        category = str(data.get('category') or '')
        entity_type = CATEGORY_TO_TYPE.get(category)
        if entity_type is None:
            continue
        name = str(data.get('name') or '')
        row = existing_by_id.get(entity_id)
        if row is None:
            row = EveObject(
                entity_id=entity_id,
                type=entity_type,
                category=category,
                name=name,
                ticker='',
                synced_at=timestamp,
            )
            row.save()
            existing_by_id[entity_id] = row
            continue
        changed = False
        if row.type != entity_type:
            row.type = entity_type
            changed = True
        if row.category != category:
            row.category = category
            changed = True
        if name and row.name != name:
            row.name = name
            changed = True
        row.synced_at = timestamp
        row.save(update_fields=['type', 'category', 'name', 'synced_at', 'updated_at'] if changed else ['synced_at', 'updated_at'])

    corp_ids_needing_details = {
        int(corporation_id)
        for corporation_id in corporation_ids
        if corporation_id not in existing_by_id
        or not str(existing_by_id[int(corporation_id)].ticker or '').strip()
        or not str(existing_by_id[int(corporation_id)].name or '').strip()
    }
    for corporation_id, data in _lookup_corporation_details(corp_ids_needing_details).items():
        row = existing_by_id.get(corporation_id)
        if row is None:
            row = EveObject(
                entity_id=corporation_id,
                type='corporation',
                category='corporation',
                name=str(data.get('name') or ''),
                ticker=str(data.get('ticker') or ''),
                synced_at=timestamp,
            )
            row.save()
            existing_by_id[corporation_id] = row
            continue
        row.type = 'corporation'
        row.category = 'corporation'
        if data.get('name'):
            row.name = str(data.get('name') or '')
        if data.get('ticker'):
            row.ticker = str(data.get('ticker') or '')
        row.synced_at = timestamp
        row.save(update_fields=['type', 'category', 'name', 'ticker', 'synced_at', 'updated_at'])

    alliance_ids_needing_details = {
        int(alliance_id)
        for alliance_id in alliance_ids
        if alliance_id not in existing_by_id
        or not str(existing_by_id[int(alliance_id)].ticker or '').strip()
        or not str(existing_by_id[int(alliance_id)].name or '').strip()
    }
    for alliance_id, data in _lookup_alliance_details(alliance_ids_needing_details).items():
        row = existing_by_id.get(alliance_id)
        if row is None:
            row = EveObject(
                entity_id=alliance_id,
                type='alliance',
                category='alliance',
                name=str(data.get('name') or ''),
                ticker=str(data.get('ticker') or ''),
                synced_at=timestamp,
            )
            row.save()
            existing_by_id[alliance_id] = row
            continue
        row.type = 'alliance'
        row.category = 'alliance'
        if data.get('name'):
            row.name = str(data.get('name') or '')
        if data.get('ticker'):
            row.ticker = str(data.get('ticker') or '')
        row.synced_at = timestamp
        row.save(update_fields=['type', 'category', 'name', 'ticker', 'synced_at', 'updated_at'])
