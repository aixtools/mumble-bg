"""Eligibility-driven MumbleUser provisioning.

Evaluates eligibility using fgbg_common against pilot source data and
BG access rules, then creates/activates/deactivates MumbleUser rows.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.contrib.auth.models import User

from bg.state.models import AccessRule, MumbleServer, MumbleUser
from fgbg_common.eligibility import (
    build_rule_sets,
    eligible_account_list,
    blocked_main_list,
)

logger = logging.getLogger(__name__)


@dataclass
class ProvisionResult:
    created: int = 0
    activated: int = 0
    deactivated: int = 0
    unchanged: int = 0
    errors: list[str] | None = None

    def to_dict(self):
        return {
            'created': self.created,
            'activated': self.activated,
            'deactivated': self.deactivated,
            'unchanged': self.unchanged,
            'errors': self.errors or [],
        }


def _load_access_rules():
    """Load access rules from BG's own DB as dicts for fgbg_common."""
    return list(
        AccessRule.objects.values(
            'entity_id', 'entity_type', 'deny',
        )
    )


def _query_character_rows(pilot_db_conn, rs):
    """Query pilot source for all characters matching access rules."""
    from fgbg_common.eligibility import all_referenced_ids

    ids = all_referenced_ids(rs)
    if not ids['alliance_ids'] and not ids['corporation_ids'] and not ids['pilot_ids']:
        return []

    # Build WHERE clauses for matching characters
    conditions = []
    params = []

    if ids['alliance_ids']:
        placeholders = ','.join(['%s'] * len(ids['alliance_ids']))
        conditions.append(f'ec.alliance_id IN ({placeholders})')
        params.extend(ids['alliance_ids'])

    if ids['corporation_ids']:
        placeholders = ','.join(['%s'] * len(ids['corporation_ids']))
        conditions.append(f'ec.corporation_id IN ({placeholders})')
        params.extend(ids['corporation_ids'])

    if ids['pilot_ids']:
        placeholders = ','.join(['%s'] * len(ids['pilot_ids']))
        conditions.append(f'ec.character_id IN ({placeholders})')
        params.extend(ids['pilot_ids'])

    where = ' OR '.join(conditions)
    query = f"""
        SELECT
            ec.user_id,
            ec.character_id,
            ec.character_name,
            ec.corporation_id,
            COALESCE(ec.corporation_name, '') AS corporation_name,
            ec.alliance_id,
            COALESCE(ec.alliance_name, '') AS alliance_name
        FROM accounts_evecharacter ec
        WHERE ec.pending_delete = false
          AND ({where})
        ORDER BY ec.user_id, ec.character_name
    """

    with pilot_db_conn.cursor() as cur:
        cur.execute(query, params)
        columns = [col[0] for col in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def _query_main_rows(pilot_db_conn, user_ids):
    """Query pilot source for main characters of given users."""
    if not user_ids:
        return {}

    placeholders = ','.join(['%s'] * len(user_ids))
    query = f"""
        SELECT
            ec.user_id,
            ec.character_id,
            ec.character_name,
            COALESCE(ec.corporation_name, '') AS corporation_name,
            COALESCE(ec.alliance_name, '') AS alliance_name,
            ec.is_main
        FROM accounts_evecharacter ec
        WHERE ec.user_id IN ({placeholders})
          AND ec.pending_delete = false
        ORDER BY ec.user_id, ec.is_main DESC, ec.character_name
    """

    mains = {}
    with pilot_db_conn.cursor() as cur:
        cur.execute(query, list(user_ids))
        columns = [col[0] for col in cur.description]
        for row_tuple in cur.fetchall():
            row = dict(zip(columns, row_tuple))
            mains.setdefault(row['user_id'], row)
    return mains


def provision_registrations(
    pilot_db_conn,
    *,
    server: MumbleServer | None = None,
    dry_run: bool = False,
) -> ProvisionResult:
    """Sync MumbleUser rows to match current eligibility.

    - Eligible accounts without a MumbleUser → create one
    - Eligible accounts with inactive MumbleUser → reactivate
    - Blocked accounts with active MumbleUser → deactivate
    """
    result = ProvisionResult(errors=[])

    if server is None:
        server = MumbleServer.objects.filter(is_active=True).order_by('display_order', 'name').first()
    if server is None:
        result.errors.append('No active MumbleServer found')
        return result

    rules = _load_access_rules()
    rs = build_rule_sets(rules)

    char_rows = _query_character_rows(pilot_db_conn, rs)
    if not char_rows:
        logger.info('No matching characters found for access rules')
        return result

    user_ids = list({r['user_id'] for r in char_rows})
    main_rows = _query_main_rows(pilot_db_conn, user_ids)

    eligible = eligible_account_list(char_rows, main_rows, rs)
    blocked = blocked_main_list(char_rows, main_rows, rs)

    eligible_user_ids = set()
    eligible_by_user_id = {}
    for entry in eligible:
        # Find the user_id from main_rows
        for uid, main in main_rows.items():
            if main['character_name'] == entry['character_name']:
                eligible_user_ids.add(uid)
                eligible_by_user_id[uid] = entry
                break

    blocked_user_ids = set()
    for entry in blocked:
        for uid, main in main_rows.items():
            if main['character_name'] == entry['character_name']:
                blocked_user_ids.add(uid)
                break

    # Load existing MumbleUser rows for this server
    existing = {
        mu.user_id: mu
        for mu in MumbleUser.objects.filter(server=server).select_related('user')
    }

    # Create/activate eligible accounts
    for user_id in eligible_user_ids:
        entry = eligible_by_user_id[user_id]
        main = main_rows.get(user_id)
        if main is None:
            continue

        username = main['character_name']

        if user_id in existing:
            mu = existing[user_id]
            if not mu.is_active:
                if not dry_run:
                    mu.is_active = True
                    mu.save(update_fields=['is_active', 'updated_at'])
                result.activated += 1
                logger.info('Activated %s (user_id=%d)', username, user_id)
            else:
                result.unchanged += 1
        else:
            if not dry_run:
                # Ensure auth.User exists
                auth_user, _ = User.objects.get_or_create(
                    pk=user_id,
                    defaults={'username': username},
                )
                MumbleUser.objects.create(
                    user=auth_user,
                    server=server,
                    evepilot_id=main['character_id'],
                    corporation_id=main.get('corporation_id'),
                    alliance_id=main.get('alliance_id'),
                    username=username,
                    display_name=username,
                    is_active=True,
                )
            result.created += 1
            logger.info('Created %s (user_id=%d)', username, user_id)

    # Deactivate blocked accounts
    for user_id in blocked_user_ids:
        if user_id in existing and existing[user_id].is_active:
            mu = existing[user_id]
            if not dry_run:
                mu.is_active = False
                mu.save(update_fields=['is_active', 'updated_at'])
            result.deactivated += 1
            logger.info('Deactivated %s (user_id=%d)', mu.username, user_id)

    return result
