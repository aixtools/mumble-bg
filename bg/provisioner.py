"""Eligibility-driven MumbleUser provisioning from BG's cached FG snapshot."""

from __future__ import annotations

import logging
from dataclasses import dataclass
import secrets

from django.contrib.auth.models import User

from bg.passwords import build_murmur_password_record
from bg.pilot_snapshot import current_pilot_snapshot
from bg.state.models import AccessRule, MumbleServer, MumbleUser
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
    username = str(getattr(account, 'account_username', '') or '').strip()
    if username:
        return username
    if existing is not None and str(existing.username or '').strip():
        return str(existing.username).strip()
    auth_user = User.objects.filter(pk=user_id).only('username').first()
    if auth_user is not None and str(auth_user.username or '').strip():
        return str(auth_user.username).strip()
    return f'pkid_{user_id}'


def _account_matches_corp_or_alliance_deny(account, rs: dict[str, set[int]]) -> bool:
    for character in account.characters:
        if character.corporation_id in rs['denied_corps']:
            return True
        if character.alliance_id in rs['denied_alliances']:
            return True
    return False


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
        server = MumbleServer.objects.filter(is_active=True).order_by('display_order', 'name').first()
    if server is None:
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

    existing = {
        mu.user_id: mu
        for mu in MumbleUser.objects.filter(server=server).select_related('user')
    }

    for user_id in sorted(eligible_user_ids):
        account = accounts_by_pkid.get(user_id)
        if account is None:
            continue
        main = account.main_character
        existing_row = existing.get(user_id)
        username = _resolved_username_for_account(account, user_id=user_id, existing=existing_row)
        display_name = account.display_name or username
        target_is_admin = user_id in admin_user_ids

        if user_id in existing:
            mu = existing[user_id]
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
                logger.info('Activated %s (pkid=%d)', username, user_id)
            else:
                if update_fields and not dry_run:
                    if mu.user.username != username:
                        mu.user.username = username
                        mu.user.save(update_fields=['username'])
                    mu.save(update_fields=update_fields + ['updated_at'])
                result.unchanged += 1
            continue

        if not dry_run:
            auth_user, _ = User.objects.get_or_create(
                pk=user_id,
                defaults={'username': username},
            )
            if auth_user.username != username:
                auth_user.username = username
                auth_user.save(update_fields=['username'])
            password = _new_password()
            password_record = build_murmur_password_record(password)
            MumbleUser.objects.create(
                user=auth_user,
                server=server,
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
        result.created += 1
        logger.info('Created %s (pkid=%d)', username, user_id)

    for user_id in sorted(blocked_user_ids):
        if user_id in existing and (existing[user_id].is_active or existing[user_id].is_mumble_admin):
            mu = existing[user_id]
            if not dry_run:
                update_fields = []
                if mu.is_active:
                    mu.is_active = False
                    update_fields.append('is_active')
                if mu.is_mumble_admin:
                    mu.is_mumble_admin = False
                    update_fields.append('is_mumble_admin')
                if update_fields:
                    mu.save(update_fields=update_fields + ['updated_at'])
            result.deactivated += 1
            logger.info('Deactivated %s (pkid=%d)', mu.username, user_id)

    return result
