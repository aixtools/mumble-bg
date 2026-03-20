"""List ACL allow/deny comparisons across cached pilot data and BG control data."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from django.core.management.base import BaseCommand

from bg.pilot_snapshot import current_pilot_snapshot
from bg.state.models import AccessRule, MumbleUser


def _load_access_rules() -> list[dict[str, Any]]:
    return list(
        AccessRule.objects.values(
            'entity_id',
            'entity_type',
            'deny',
        )
    )


def _bg_state_lists() -> dict[str, list[dict[str, Any]]]:
    qs = MumbleUser.objects.select_related('user', 'server').order_by('user_id', 'server__display_order', 'server__name')
    active: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []

    for row in qs:
        pilot_name = row.display_name or row.username or row.user.username or ''
        id_value = int(row.user_id)
        summary = {'id': id_value, 'pilot_name': pilot_name}
        if row.is_active:
            active.append(summary)
        else:
            blocked.append(summary)

        rows.append(
            {
                'id': id_value,
                'pilot_name': pilot_name,
                'is_active': bool(row.is_active),
            }
        )

    return {
        'bg_active': active,
        'bg_blocked': blocked,
        'bg_rows': rows,
    }


def _acl_from_sets(*, has_permit: bool, has_deny: bool) -> str:
    if has_permit and has_deny:
        return 'mixed'
    if has_permit:
        return 'permit'
    if has_deny:
        return 'deny'
    return 'missing'


def _build_comparison_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    fg_allow_by_id: dict[int, set[str]] = defaultdict(set)
    fg_deny_by_id: dict[int, set[str]] = defaultdict(set)

    for row in report['fg_allowed']:
        fg_allow_by_id[int(row['id'])].add(str(row.get('pilot_name') or ''))

    for row in report['fg_denied']:
        fg_deny_by_id[int(row['id'])].add(str(row.get('pilot_name') or ''))

    bg_active_by_id: dict[int, list[dict[str, Any]]] = defaultdict(list)
    bg_blocked_by_id: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in report['bg_rows']:
        id_value = int(row['id'])
        if row.get('is_active'):
            bg_active_by_id[id_value].append(row)
        else:
            bg_blocked_by_id[id_value].append(row)

    all_ids = sorted(set(fg_allow_by_id) | set(fg_deny_by_id) | set(bg_active_by_id) | set(bg_blocked_by_id))
    comparison: list[dict[str, str]] = []

    for id_value in all_ids:
        fg_acl = _acl_from_sets(
            has_permit=bool(fg_allow_by_id.get(id_value)),
            has_deny=bool(fg_deny_by_id.get(id_value)),
        )
        bg_acl = _acl_from_sets(
            has_permit=bool(bg_active_by_id.get(id_value)),
            has_deny=bool(bg_blocked_by_id.get(id_value)),
        )

        pilot_names = sorted(fg_allow_by_id.get(id_value, set()) | fg_deny_by_id.get(id_value, set()))
        if not pilot_names:
            pilot_names = sorted(
                {
                    str(r.get('pilot_name') or r.get('display_name') or r.get('username') or '')
                    for r in (bg_active_by_id.get(id_value, []) + bg_blocked_by_id.get(id_value, []))
                }
            )

        bg_names = sorted(
            {
                str(r.get('pilot_name') or '')
                for r in (bg_active_by_id.get(id_value, []) + bg_blocked_by_id.get(id_value, []))
                if str(r.get('pilot_name') or '')
            }
        )
        bg_name_value = ', '.join(bg_names) if bg_names else '-'
        name_value = ', '.join(pilot_names) if pilot_names else bg_name_value

        if fg_acl == bg_acl:
            comparison.append(
                {
                    'id': str(id_value),
                    'name': name_value,
                    'db': 'pilot_data,bg_control_data',
                    'acl': fg_acl,
                }
            )
            continue

        comparison.append(
            {
                'id': str(id_value),
                'name': name_value,
                'db': 'pilot_data',
                'acl': fg_acl,
            }
        )
        comparison.append(
            {
                'id': str(id_value),
                'name': bg_name_value,
                'db': 'bg_control_data',
                'acl': bg_acl,
            }
        )

    return comparison


class Command(BaseCommand):
    help = (
        'List ACL comparison rows using id (pkid contract identity), combining cached pilot data and BG control data.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--json',
            action='store_true',
            help='Output results as JSON.',
        )

    def handle(self, **options):
        report: dict[str, Any] = {
            'fg_status': 'unknown',
            'fg_message': '',
            'fg_allowed': [],
            'fg_denied': [],
            'comparison_rows': [],
        }
        report.update(_bg_state_lists())

        try:
            from fgbg_common.eligibility import (
                build_rule_sets,
                blocked_main_list_from_snapshot,
                eligible_account_list_from_snapshot,
            )
        except Exception:
            report['fg_status'] = 'unavailable'
            report['fg_message'] = 'fg not configured/installed'
        else:
            snapshot = current_pilot_snapshot()
            if not snapshot.accounts:
                report['fg_status'] = 'no_data'
                report['fg_message'] = 'no data to evaluate (no cached FG pilot snapshot)'
            else:
                rs = build_rule_sets(_load_access_rules())
                report['fg_allowed'] = [
                    {'id': int(row['pkid']), 'pilot_name': str(row['character_name'] or '')}
                    for row in eligible_account_list_from_snapshot(snapshot, rs)
                ]
                report['fg_denied'] = [
                    {'id': int(row['pkid']), 'pilot_name': str(row['character_name'] or '')}
                    for row in blocked_main_list_from_snapshot(snapshot, rs)
                ]
                report['fg_status'] = 'ok'
                report['fg_message'] = 'evaluated via fgbg_common using cached pilot snapshot'

        report['comparison_rows'] = _build_comparison_rows(report)

        if options['json']:
            self.stdout.write(json.dumps(report, indent=2))
            return

        self.stdout.write('id is the pkid contract identity')
        self.stdout.write(f"FG evaluation status: {report['fg_status']}")
        if report['fg_message']:
            self.stdout.write(f"FG message: {report['fg_message']}")
        self.stdout.write('')
        self.stdout.write(f"ACL Comparison ({len(report['comparison_rows'])} rows)")

        headers = ['id', 'name', 'db', 'acl']
        widths = {header: len(header) for header in headers}
        for row in report['comparison_rows']:
            for header in headers:
                widths[header] = max(widths[header], len(str(row[header])))

        self.stdout.write(
            f"{'id'.ljust(widths['id'])} | "
            f"{'name'.ljust(widths['name'])} | "
            f"{'db'.ljust(widths['db'])} | "
            f"{'acl'.ljust(widths['acl'])}"
        )
        self.stdout.write(
            f"{'-' * widths['id']}-+-"
            f"{'-' * widths['name']}-+-"
            f"{'-' * widths['db']}-+-"
            f"{'-' * widths['acl']}"
        )

        if not report['comparison_rows']:
            self.stdout.write('(none)')
            return

        for row in report['comparison_rows']:
            self.stdout.write(
                f"{row['id'].ljust(widths['id'])} | "
                f"{row['name'].ljust(widths['name'])} | "
                f"{row['db'].ljust(widths['db'])} | "
                f"{row['acl'].ljust(widths['acl'])}"
            )
