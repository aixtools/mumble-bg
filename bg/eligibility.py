"""BG-side eligibility helpers built on shared core logic."""

from __future__ import annotations

from typing import Any

from fgbg_common.eligibility import (
    DENIAL_REASON_LABELS,
    account_rule_decisions_from_snapshot,
    blocked_user_reasons,
    explicit_rule_match,
)
from fgbg_common.entity_types import ENTITY_TYPE_PILOT
from fgbg_common.snapshot import PilotSnapshot


def _snapshot_character_row(account, *, character) -> dict[str, Any]:
    return {
        'user_id': account.pkid,
        'character_id': character.character_id,
        'character_name': character.character_name,
        'corporation_id': character.corporation_id,
        'corporation_name': character.corporation_name,
        'alliance_id': character.alliance_id,
        'alliance_name': character.alliance_name,
    }


def blocked_main_list_from_snapshot(
    snapshot: PilotSnapshot,
    rs: dict[str, set[int]],
) -> list[dict[str, Any]]:
    """Return blocked accounts from an account-oriented snapshot."""
    blocked_by_user = blocked_user_reasons(account_rule_decisions_from_snapshot(snapshot, rs))
    if not blocked_by_user:
        return []

    pilots: list[dict[str, Any]] = []
    for account in snapshot.accounts:
        reason = blocked_by_user.get(account.pkid)
        if not reason:
            continue
        main = account.main_character
        denied_as = DENIAL_REASON_LABELS[reason['reason_type']]
        denied_detail = reason['detail']
        pilots.append(
            {
                'pkid': account.pkid,
                'character_name': main.character_name,
                'display_name': f'{main.character_name} (denied as: {denied_detail})',
                'corporation': main.corporation_name or '-',
                'alliance': main.alliance_name or '-',
                'denied_as': denied_as,
                'denied_detail': denied_detail,
            }
        )

    pilots.sort(key=lambda pilot: (pilot['character_name'].lower(), pilot['pkid']))
    return pilots


def eligible_account_list_from_snapshot(
    snapshot: PilotSnapshot,
    rs: dict[str, set[int]],
) -> list[dict[str, Any]]:
    """Return eligible accounts from an account-oriented snapshot."""
    blocked_ids = set(blocked_user_reasons(account_rule_decisions_from_snapshot(snapshot, rs)))
    pilots: list[dict[str, Any]] = []

    for account in snapshot.accounts:
        if account.pkid in blocked_ids:
            continue

        allowed_rows: list[tuple[Any, dict[str, Any]]] = []
        for character in account.characters:
            match = explicit_rule_match(rs, _snapshot_character_row(account, character=character))
            if not match or match.get('action') != 'allow':
                continue
            allowed_rows.append((character, match))

        if not allowed_rows:
            continue

        main = account.main_character
        alt_lines = sorted(
            {
                character.character_name
                for character, match in allowed_rows
                if match['reason_type'] == ENTITY_TYPE_PILOT
                and character.character_id != main.character_id
            },
            key=str.lower,
        )
        pilots.append(
            {
                'pkid': account.pkid,
                'character_name': main.character_name,
                'pilot_lines': [main.character_name, *alt_lines],
                'corporation': main.corporation_name or '-',
                'alliance': main.alliance_name or '-',
            }
        )

    pilots.sort(key=lambda pilot: (pilot['character_name'].lower(), pilot['pkid']))
    return pilots


def account_acl_state_by_pkid(snapshot: PilotSnapshot, rs: dict[str, set[int]]) -> dict[int, str]:
    """Return permit/deny evaluation state per pkid from a snapshot."""
    blocked_ids = set(blocked_user_reasons(account_rule_decisions_from_snapshot(snapshot, rs)))
    states: dict[int, str] = {}
    for account in snapshot.accounts:
        if account.pkid in blocked_ids:
            states[account.pkid] = 'deny'
            continue
        for character in account.characters:
            match = explicit_rule_match(rs, _snapshot_character_row(account, character=character))
            if match and match.get('action') == 'allow':
                states[account.pkid] = 'permit'
                break
    return states
