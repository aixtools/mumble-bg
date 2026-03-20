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
    return list(AccessRule.objects.values('entity_id', 'entity_type', 'deny'))


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
        username = main.character_name

        if user_id in existing:
            mu = existing[user_id]
            if not mu.is_active:
                if not dry_run:
                    mu.is_active = True
                    mu.save(update_fields=['is_active', 'updated_at'])
                result.activated += 1
                logger.info('Activated %s (pkid=%d)', username, user_id)
            else:
                result.unchanged += 1
            continue

        if not dry_run:
            auth_user, _ = User.objects.get_or_create(
                pk=user_id,
                defaults={'username': username},
            )
            password = _new_password()
            password_record = build_murmur_password_record(password)
            MumbleUser.objects.create(
                user=auth_user,
                server=server,
                evepilot_id=main.character_id,
                corporation_id=main.corporation_id,
                alliance_id=main.alliance_id,
                username=username,
                display_name=username,
                pwhash=password_record['pwhash'],
                hashfn=password_record['hashfn'],
                pw_salt=password_record['pw_salt'],
                kdf_iterations=password_record['kdf_iterations'],
                is_active=True,
            )
        result.created += 1
        logger.info('Created %s (pkid=%d)', username, user_id)

    for user_id in sorted(blocked_user_ids):
        if user_id in existing and existing[user_id].is_active:
            mu = existing[user_id]
            if not dry_run:
                mu.is_active = False
                mu.save(update_fields=['is_active', 'updated_at'])
            result.deactivated += 1
            logger.info('Deactivated %s (pkid=%d)', mu.username, user_id)

    return result
