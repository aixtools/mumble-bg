"""BG-owned pilot snapshot cache helpers."""

from __future__ import annotations

from typing import Any

from django.db import transaction

from bg.state.models import (
    PilotAccountCache,
    PilotCharacterCache,
    PilotSnapshotSyncAudit,
)
from fgbg_common.snapshot import PilotAccount, PilotCharacter, PilotSnapshot


def current_pilot_snapshot() -> PilotSnapshot:
    accounts: list[PilotAccount] = []
    generated_at = ''
    latest_sync = PilotSnapshotSyncAudit.objects.order_by('-created_at', '-id').values('summary_after').first()
    if latest_sync:
        summary_after = latest_sync.get('summary_after') or {}
        if isinstance(summary_after, dict):
            generated_at = str(summary_after.get('generated_at') or '')
    rows = PilotAccountCache.objects.prefetch_related('characters').order_by('pkid')
    for row in rows:
        characters = tuple(
            PilotCharacter(
                character_id=int(character.character_id),
                character_name=str(character.character_name or ''),
                corporation_id=int(character.corporation_id) if character.corporation_id is not None else None,
                corporation_name=str(character.corporation_name or ''),
                alliance_id=int(character.alliance_id) if character.alliance_id is not None else None,
                alliance_name=str(character.alliance_name or ''),
                is_main=bool(character.is_main),
            )
            for character in row.characters.all().order_by('-is_main', 'character_name', 'character_id')
        )
        if not characters:
            continue
        accounts.append(
            PilotAccount(
                pkid=int(row.pkid),
                account_username=str(row.account_username or ''),
                pilot_data_hash=str(row.pilot_data_hash or ''),
                display_name=str(row.display_name or ''),
                characters=characters,
            )
        )
    return PilotSnapshot(accounts=tuple(accounts), generated_at=generated_at)


def pilot_snapshot_summary(snapshot: PilotSnapshot | None = None) -> dict[str, Any]:
    effective = snapshot or current_pilot_snapshot()
    return effective.summary()


def has_pilot_snapshot() -> bool:
    return PilotAccountCache.objects.exists()


def pilot_snapshot_hash_pairs() -> list[dict[str, Any]]:
    return [
        {
            'pkid': int(row['pkid']),
            'hash': str(row['pilot_data_hash'] or ''),
        }
        for row in PilotAccountCache.objects.order_by('pkid').values('pkid', 'pilot_data_hash')
    ]


def store_pilot_snapshot(
    snapshot: PilotSnapshot,
    *,
    request_id: str,
    requested_by: str,
) -> dict[str, Any]:
    before = current_pilot_snapshot()
    before_payload = before.as_dict()
    after_payload = snapshot.as_dict()
    changed = before_payload != after_payload
    before_summary = before.summary()
    after_summary = snapshot.summary()

    if not changed:
        return {
            'changed': False,
            'account_count': snapshot.account_count,
            'character_count': snapshot.character_count,
            'summary_before': before_summary,
            'summary_after': after_summary,
            'pilot_hashes': pilot_snapshot_hash_pairs(),
        }

    with transaction.atomic():
        PilotCharacterCache.objects.all().delete()
        PilotAccountCache.objects.all().delete()

        account_rows = []
        for account in snapshot.accounts:
            main = account.main_character
            account_rows.append(
                PilotAccountCache(
                    pkid=account.pkid,
                    account_username=account.account_username,
                    pilot_data_hash=account.pilot_data_hash,
                    display_name=account.display_name,
                    main_character_id=main.character_id if main else None,
                    main_character_name=main.character_name if main else '',
                )
            )
        PilotAccountCache.objects.bulk_create(account_rows)

        accounts_by_pkid = {
            int(row.pkid): row
            for row in PilotAccountCache.objects.filter(pkid__in=[account.pkid for account in snapshot.accounts])
        }
        character_rows = []
        for account in snapshot.accounts:
            account_row = accounts_by_pkid[account.pkid]
            for character in account.characters:
                character_rows.append(
                    PilotCharacterCache(
                        account=account_row,
                        character_id=character.character_id,
                        character_name=character.character_name,
                        corporation_id=character.corporation_id,
                        corporation_name=character.corporation_name,
                        alliance_id=character.alliance_id,
                        alliance_name=character.alliance_name,
                        is_main=character.is_main,
                    )
                )
        if character_rows:
            PilotCharacterCache.objects.bulk_create(character_rows)

        PilotSnapshotSyncAudit.objects.create(
            request_id=request_id,
            requested_by=requested_by,
            action='sync',
            summary_before=before_summary,
            summary_after=after_summary,
        )

    return {
        'changed': True,
        'account_count': snapshot.account_count,
        'character_count': snapshot.character_count,
        'summary_before': before_summary,
        'summary_after': after_summary,
        'pilot_hashes': pilot_snapshot_hash_pairs(),
    }
