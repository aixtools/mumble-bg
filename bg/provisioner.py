"""Eligibility-driven MumbleUser provisioning from BG's cached FG snapshot."""

from __future__ import annotations

import logging
from dataclasses import dataclass
import re
import secrets

from django.contrib.auth.models import User

from bg.eve_lookup import resolve_and_cache_eve_objects
from bg.passwords import build_murmur_password_record
from bg.pilot_snapshot import current_pilot_snapshot
from bg.state.models import AccessRule, EveObject, MumbleServer, MumbleUser, PilotAccountCache
from fgbg_common.eligibility import (
    build_rule_sets,
    blocked_main_list_from_snapshot,
    eligible_account_list_from_snapshot,
)

_FORBIDDEN_PASSWORD_CHARS = {"'", '"', '`', '\\'}
_PASSWORD_CHARS = ''.join(
    chr(code) for code in range(33, 127) if chr(code) not in _FORBIDDEN_PASSWORD_CHARS
)


def _new_password(length: int = 16) -> str:
    return ''.join(secrets.choice(_PASSWORD_CHARS) for _ in range(length))


logger = logging.getLogger(__name__)
_USERNAME_SANITIZE_RE = re.compile(r'[^a-z0-9_]+')


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
    return list(AccessRule.objects.values('entity_id', 'entity_type', 'deny', 'acl_admin'))


def _resolved_username_for_account(account, *, user_id: int, existing: MumbleUser | None = None) -> str:
    username = _USERNAME_SANITIZE_RE.sub(
        '',
        str(getattr(account, 'account_username', '') or '').strip().lower().replace(' ', ''),
    )
    if username:
        return username
    if existing is not None and str(existing.username or '').strip():
        existing_username = _USERNAME_SANITIZE_RE.sub('', str(existing.username).strip().lower().replace(' ', ''))
        if existing_username:
            return existing_username
    auth_user = User.objects.filter(pk=user_id).only('username').first()
    if auth_user is not None and str(auth_user.username or '').strip():
        auth_username = _USERNAME_SANITIZE_RE.sub('', str(auth_user.username).strip().lower().replace(' ', ''))
        if auth_username:
            return auth_username
    return f'pkid_{user_id}'


def _account_matches_corp_or_alliance_deny(account, rs: dict[str, set[int]]) -> bool:
    for character in account.characters:
        if character.corporation_id in rs['denied_corps']:
            return True
        if character.alliance_id in rs['denied_alliances']:
            return True
    return False


def _display_name_needs_resolution(value: str) -> bool:
    normalized = str(value or '').strip()
    return not normalized or '????' in normalized


def _display_tags_look_name_based(value: str) -> bool:
    text = str(value or '').strip()
    if not (text.startswith('[') and '] ' in text):
        return False
    tag_section = text[1:text.find(']')]
    return any(char.isalpha() and char.islower() for char in tag_section)


def _display_name_from_account_with_eve_objects(account, *, eve_objects_by_key: dict[tuple[str, int], EveObject]) -> str:
    main = account.main_character
    if main is None:
        fallback = str(getattr(account, 'account_username', '') or '').strip()
        return fallback or f'pkid_{int(account.pkid)}'

    character_name = str(main.character_name or '').strip()
    if not character_name:
        pilot_obj = eve_objects_by_key.get(('pilot', int(main.character_id)))
        character_name = str(getattr(pilot_obj, 'name', '') or '').strip()
    if not character_name:
        character_name = str(getattr(account, 'account_username', '') or '').strip() or f'pkid_{int(account.pkid)}'

    tags: list[str] = []
    if main.alliance_id is not None:
        alliance_obj = eve_objects_by_key.get(('alliance', int(main.alliance_id)))
        tags.append(str(getattr(alliance_obj, 'ticker', '') or '').strip() or '????')
    if main.corporation_id is not None:
        corp_obj = eve_objects_by_key.get(('corporation', int(main.corporation_id)))
        tags.append(str(getattr(corp_obj, 'ticker', '') or '').strip() or '????')

    if tags:
        return f'[{" ".join(tags)}] {character_name}'
    return character_name


def _resolved_display_name_for_account(account, *, eve_objects_by_key: dict[tuple[str, int], EveObject]) -> str:
    current = str(getattr(account, 'display_name', '') or '').strip()
    resolved = _display_name_from_account_with_eve_objects(account, eve_objects_by_key=eve_objects_by_key)
    resolved = str(resolved or '').strip()
    if current and not _display_name_needs_resolution(current):
        if resolved and '????' not in resolved:
            return resolved
        if _display_tags_look_name_based(current) and resolved:
            return resolved
        return current
    if resolved:
        return resolved
    return current


def _acl_admin_accounts(snapshot, rules: list[dict[str, object]], rs: dict[str, set[int]]) -> set[int]:
    """Resolve pkids that should be Murmur admin from pilot ACL markers."""
    admin_pilot_ids = {
        int(rule['entity_id'])
        for rule in rules
        if rule.get('entity_type') == 'pilot'
        and not bool(rule.get('deny', False))
        and bool(rule.get('acl_admin', False))
    }
    if not admin_pilot_ids:
        return set()

    admin_accounts: set[int] = set()
    for account in snapshot.accounts:
        if _account_matches_corp_or_alliance_deny(account, rs):
            continue
        for character in account.characters:
            if int(character.character_id) in admin_pilot_ids:
                admin_accounts.add(int(account.pkid))
                break
    return admin_accounts


def provision_registrations(
    *,
    server: MumbleServer | None = None,
    dry_run: bool = False,
) -> ProvisionResult:
    """Sync MumbleUser rows to match eligibility from BG's cached pilot snapshot."""
    result = ProvisionResult(errors=[])

    if server is None:
        servers = list(MumbleServer.objects.filter(is_active=True).order_by('display_order', 'name'))
    else:
        servers = [server]

    if not servers:
        result.errors.append('No active MumbleServer found')
        return result

    snapshot = current_pilot_snapshot()
    if not snapshot.accounts:
        result.errors.append('No pilot snapshot data available; sync /v1/pilot-snapshot/sync first')
        return result

    rules = _load_access_rules()
    rs = build_rule_sets(rules)
    eligible = eligible_account_list_from_snapshot(snapshot, rs)
    blocked = blocked_main_list_from_snapshot(snapshot, rs)
    admin_user_ids = _acl_admin_accounts(snapshot, rules, rs)

    eligible_by_pkid = {int(entry['pkid']): entry for entry in eligible}
    eligible_user_ids = set(eligible_by_pkid)
    blocked_user_ids = {int(entry['pkid']) for entry in blocked}

    accounts_by_pkid = {int(account.pkid): account for account in snapshot.accounts}
    character_ids: set[int] = set()
    corporation_ids: set[int] = set()
    alliance_ids: set[int] = set()
    for account in accounts_by_pkid.values():
        for character in account.characters:
            character_ids.add(int(character.character_id))
            if character.corporation_id is not None:
                corporation_ids.add(int(character.corporation_id))
            if character.alliance_id is not None:
                alliance_ids.add(int(character.alliance_id))

    needs_display_resolution = any(
        (account.main_character is not None)
        and (
            account.main_character.alliance_id is not None
            or account.main_character.corporation_id is not None
            or _display_name_needs_resolution(str(getattr(account, 'display_name', '') or ''))
        )
        for account in accounts_by_pkid.values()
    )
    if needs_display_resolution:
        resolve_and_cache_eve_objects(
            character_ids=character_ids,
            corporation_ids=corporation_ids,
            alliance_ids=alliance_ids,
        )
    eve_objects_by_key = {
        (str(row.type), int(row.entity_id)): row
        for row in EveObject.objects.filter(entity_id__in=list(character_ids | corporation_ids | alliance_ids))
    }
    resolved_display_by_pkid: dict[int, str] = {
        pkid: _resolved_display_name_for_account(account, eve_objects_by_key=eve_objects_by_key)
        for pkid, account in accounts_by_pkid.items()
    }
    if not dry_run:
        for pkid, resolved_display in resolved_display_by_pkid.items():
            cached_display = str(getattr(accounts_by_pkid[pkid], 'display_name', '') or '').strip()
            if resolved_display and resolved_display != cached_display:
                PilotAccountCache.objects.filter(pkid=pkid).update(display_name=resolved_display)

    server_ids = [int(item.id) for item in servers]
    existing = {
        (int(mu.server_id), int(mu.user_id)): mu
        for mu in MumbleUser.objects.filter(server_id__in=server_ids).select_related('user', 'server')
    }

    auth_user_cache: dict[int, User] = {}

    for target_server in servers:
        server_id = int(target_server.id)

        for user_id in sorted(eligible_user_ids):
            account = accounts_by_pkid.get(user_id)
            if account is None:
                continue
            main = account.main_character
            existing_row = existing.get((server_id, user_id))
            username = _resolved_username_for_account(account, user_id=user_id, existing=existing_row)
            display_name = str(resolved_display_by_pkid.get(user_id) or account.display_name or username)
            target_is_admin = user_id in admin_user_ids

            if existing_row is not None:
                mu = existing_row
                update_fields = []
                if mu.username != username:
                    mu.username = username
                    update_fields.append('username')
                if mu.display_name != display_name:
                    mu.display_name = display_name
                    update_fields.append('display_name')
                if mu.evepilot_id != main.character_id:
                    mu.evepilot_id = main.character_id
                    update_fields.append('evepilot_id')
                if mu.corporation_id != main.corporation_id:
                    mu.corporation_id = main.corporation_id
                    update_fields.append('corporation_id')
                if mu.alliance_id != main.alliance_id:
                    mu.alliance_id = main.alliance_id
                    update_fields.append('alliance_id')
                if mu.is_mumble_admin != target_is_admin:
                    mu.is_mumble_admin = target_is_admin
                    update_fields.append('is_mumble_admin')
                if not mu.is_active:
                    if not dry_run:
                        mu.is_active = True
                        update_fields.append('is_active')
                        if mu.user.username != username:
                            mu.user.username = username
                            mu.user.save(update_fields=['username'])
                        mu.save(update_fields=update_fields + ['updated_at'])
                    result.activated += 1
                    logger.info('Activated %s on %s (pkid=%d)', username, target_server.name, user_id)
                else:
                    if update_fields and not dry_run:
                        if mu.user.username != username:
                            mu.user.username = username
                            mu.user.save(update_fields=['username'])
                        mu.save(update_fields=update_fields + ['updated_at'])
                    result.unchanged += 1
                continue

            if not dry_run:
                auth_user = auth_user_cache.get(user_id)
                if auth_user is None:
                    auth_user, _ = User.objects.get_or_create(
                        pk=user_id,
                        defaults={'username': username},
                    )
                    auth_user_cache[user_id] = auth_user
                if auth_user.username != username:
                    auth_user.username = username
                    auth_user.save(update_fields=['username'])
                password = _new_password()
                password_record = build_murmur_password_record(password)
                created_row = MumbleUser.objects.create(
                    user=auth_user,
                    server=target_server,
                    evepilot_id=main.character_id,
                    corporation_id=main.corporation_id,
                    alliance_id=main.alliance_id,
                    username=username,
                    display_name=display_name,
                    pwhash=password_record['pwhash'],
                    hashfn=password_record['hashfn'],
                    pw_salt=password_record['pw_salt'],
                    kdf_iterations=password_record['kdf_iterations'],
                    is_mumble_admin=target_is_admin,
                    is_active=True,
                )
                existing[(server_id, user_id)] = created_row
            result.created += 1
            logger.info('Created %s on %s (pkid=%d)', username, target_server.name, user_id)

        for user_id in sorted(blocked_user_ids):
            existing_row = existing.get((server_id, user_id))
            if existing_row is None:
                continue
            if not (existing_row.is_active or existing_row.is_mumble_admin):
                continue
            if not dry_run:
                update_fields = []
                if existing_row.is_active:
                    existing_row.is_active = False
                    update_fields.append('is_active')
                if existing_row.is_mumble_admin:
                    existing_row.is_mumble_admin = False
                    update_fields.append('is_mumble_admin')
                if update_fields:
                    existing_row.save(update_fields=update_fields + ['updated_at'])
            result.deactivated += 1
            logger.info('Deactivated %s on %s (pkid=%d)', existing_row.username, target_server.name, user_id)

    return result
