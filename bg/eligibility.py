"""BG-side eligibility evaluation helpers."""

from __future__ import annotations

from typing import Any

from fgbg_common.entity_types import (
    ENTITY_TYPE_ALLIANCE,
    ENTITY_TYPE_CORPORATION,
    ENTITY_TYPE_PILOT,
)
from fgbg_common.snapshot import PilotSnapshot


def build_rule_sets(rules: list[dict[str, Any]]) -> dict[str, set[int]]:
    """Build categorized ID sets from ACL rules."""
    rs: dict[str, set[int]] = {
        'allowed_alliances': set(),
        'denied_alliances': set(),
        'allowed_corps': set(),
        'denied_corps': set(),
        'allowed_pilots': set(),
        'denied_pilots': set(),
    }
    for rule in rules:
        entity_id = int(rule['entity_id'])
        entity_type = rule['entity_type']
        deny = bool(rule.get('deny', False))
        if entity_type == ENTITY_TYPE_ALLIANCE:
            (rs['denied_alliances'] if deny else rs['allowed_alliances']).add(entity_id)
        elif entity_type == ENTITY_TYPE_CORPORATION:
            (rs['denied_corps'] if deny else rs['allowed_corps']).add(entity_id)
        elif entity_type == ENTITY_TYPE_PILOT:
            (rs['denied_pilots'] if deny else rs['allowed_pilots']).add(entity_id)
    return rs


DENIAL_REASON_LABELS: dict[str, str] = {
    ENTITY_TYPE_ALLIANCE: 'alliance',
    ENTITY_TYPE_CORPORATION: 'corp',
    ENTITY_TYPE_PILOT: 'pilot',
}

DENIAL_REASON_RANK: dict[str, int] = {
    ENTITY_TYPE_ALLIANCE: 1,
    ENTITY_TYPE_CORPORATION: 2,
    ENTITY_TYPE_PILOT: 3,
}


def _denial_reason_detail(reason_type: str, row: dict[str, Any]) -> str:
    if reason_type == ENTITY_TYPE_PILOT:
        return row['character_name'] or str(row['character_id'])
    if reason_type == ENTITY_TYPE_CORPORATION:
        return row['corporation_name'] or str(row['corporation_id'])
    return row['alliance_name'] or str(row['alliance_id'])


def _prefer_reason(current: dict[str, Any] | None, candidate: dict[str, Any]) -> dict[str, Any]:
    if current is None:
        return candidate
    current_rank = DENIAL_REASON_RANK[current['reason_type']]
    candidate_rank = DENIAL_REASON_RANK[candidate['reason_type']]
    if candidate_rank > current_rank:
        return candidate
    if candidate_rank < current_rank:
        return current
    if candidate['detail'].lower() < current['detail'].lower():
        return candidate
    return current


def explicit_rule_match(rs: dict[str, set[int]], row: dict[str, Any]) -> dict[str, Any] | None:
    """Return the first (highest-priority) matching rule for a character row."""
    cid = row['character_id']
    corp = row['corporation_id']
    ally = row['alliance_id']

    if cid in rs['allowed_pilots']:
        return {'action': 'allow', 'reason_type': ENTITY_TYPE_PILOT, 'detail': _denial_reason_detail(ENTITY_TYPE_PILOT, row)}
    if cid in rs['denied_pilots']:
        return {'action': 'deny', 'reason_type': ENTITY_TYPE_PILOT, 'detail': _denial_reason_detail(ENTITY_TYPE_PILOT, row)}
    if corp in rs['allowed_corps']:
        return {'action': 'allow', 'reason_type': ENTITY_TYPE_CORPORATION, 'detail': _denial_reason_detail(ENTITY_TYPE_CORPORATION, row)}
    if corp in rs['denied_corps']:
        return {'action': 'deny', 'reason_type': ENTITY_TYPE_CORPORATION, 'detail': _denial_reason_detail(ENTITY_TYPE_CORPORATION, row)}
    if ally in rs['allowed_alliances']:
        return {'action': 'allow', 'reason_type': ENTITY_TYPE_ALLIANCE, 'detail': _denial_reason_detail(ENTITY_TYPE_ALLIANCE, row)}
    if ally in rs['denied_alliances']:
        return {'action': 'deny', 'reason_type': ENTITY_TYPE_ALLIANCE, 'detail': _denial_reason_detail(ENTITY_TYPE_ALLIANCE, row)}
    return None


def explicit_rule_matches(rs: dict[str, set[int]], row: dict[str, Any]) -> list[dict[str, Any]]:
    """Return all matching rules for a character row."""
    matches: list[dict[str, Any]] = []
    cid = row['character_id']
    corp = row['corporation_id']
    ally = row['alliance_id']

    if cid in rs['allowed_pilots']:
        matches.append({'action': 'allow', 'reason_type': ENTITY_TYPE_PILOT, 'detail': _denial_reason_detail(ENTITY_TYPE_PILOT, row)})
    if cid in rs['denied_pilots']:
        matches.append({'action': 'deny', 'reason_type': ENTITY_TYPE_PILOT, 'detail': _denial_reason_detail(ENTITY_TYPE_PILOT, row)})
    if corp in rs['allowed_corps']:
        matches.append({'action': 'allow', 'reason_type': ENTITY_TYPE_CORPORATION, 'detail': _denial_reason_detail(ENTITY_TYPE_CORPORATION, row)})
    if corp in rs['denied_corps']:
        matches.append({'action': 'deny', 'reason_type': ENTITY_TYPE_CORPORATION, 'detail': _denial_reason_detail(ENTITY_TYPE_CORPORATION, row)})
    if ally in rs['allowed_alliances']:
        matches.append({'action': 'allow', 'reason_type': ENTITY_TYPE_ALLIANCE, 'detail': _denial_reason_detail(ENTITY_TYPE_ALLIANCE, row)})
    if ally in rs['denied_alliances']:
        matches.append({'action': 'deny', 'reason_type': ENTITY_TYPE_ALLIANCE, 'detail': _denial_reason_detail(ENTITY_TYPE_ALLIANCE, row)})
    return matches


def account_rule_decisions_from_snapshot(snapshot: PilotSnapshot, rs: dict[str, set[int]]) -> dict[int, dict[str, Any]]:
    """Build per-account allow/deny decision from an account-oriented snapshot."""
    account_rules: dict[int, dict[str, Any]] = {}
    for account in snapshot.accounts:
        user_rules = account_rules.setdefault(account.pkid, {'allow': None, 'deny': None})
        for character in account.characters:
            matches = explicit_rule_matches(rs, _snapshot_character_row(account, character=character))
            for match in matches:
                reason = {'reason_type': match['reason_type'], 'detail': match['detail']}
                user_rules[match['action']] = _prefer_reason(user_rules[match['action']], reason)
    return account_rules


def blocked_user_reasons(account_rules: dict[int, dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Identify blocked users: allowed and denied, where deny rank >= allow rank."""
    return {
        user_id: rules['deny']
        for user_id, rules in account_rules.items()
        if rules['allow']
        and rules['deny']
        and DENIAL_REASON_RANK[rules['deny']['reason_type']] >= DENIAL_REASON_RANK[rules['allow']['reason_type']]
    }


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
