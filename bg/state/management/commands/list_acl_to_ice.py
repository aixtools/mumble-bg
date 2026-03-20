"""Compare cached ACL decisions to ICE registrations, grouped by pilot."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from django.core.management.base import BaseCommand

from bg.pilot_snapshot import current_pilot_snapshot
from bg.pulse.reconciler import MurmurReconcileError, _MurmurServerAdapter
from bg.state.models import AccessRule, MumbleServer, MumbleUser


def _load_access_rules() -> list[dict[str, Any]]:
    return list(AccessRule.objects.values('entity_id', 'entity_type', 'deny'))


def _acl_from_sets(*, has_permit: bool, has_deny: bool) -> str:
    if has_permit and has_deny:
        return 'mixed'
    if has_permit:
        return 'permit'
    if has_deny:
        return 'deny'
    return 'missing'


def _safe(text: str, *, limit: int = 80) -> str:
    txt = str(text or '')
    return txt if len(txt) <= limit else txt[: limit - 3] + '...'


class Command(BaseCommand):
    help = (
        'List ACL decision vs ICE registration state per pilot. '
        'Rows are grouped by pilot id (pkid) with one line per vsid:server.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true', help='Output results as JSON.')

    def handle(self, **options):
        report: dict[str, Any] = {
            'fg_status': 'unknown',
            'fg_message': '',
            'pilots': [],
        }

        fg_allow_by_id: dict[int, set[str]] = defaultdict(set)
        fg_deny_by_id: dict[int, set[str]] = defaultdict(set)

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
                rule_sets = build_rule_sets(_load_access_rules())
                for row in eligible_account_list_from_snapshot(snapshot, rule_sets):
                    fg_allow_by_id[int(row['pkid'])].add(str(row['character_name'] or ''))
                for row in blocked_main_list_from_snapshot(snapshot, rule_sets):
                    fg_deny_by_id[int(row['pkid'])].add(str(row['character_name'] or ''))
                report['fg_status'] = 'ok'
                report['fg_message'] = 'evaluated via fgbg_common using cached pilot snapshot'

        bg_rows = list(
            MumbleUser.objects.select_related('user', 'server')
            .order_by('user_id', 'server__display_order', 'server__name')
        )
        bg_by_id: dict[int, list[MumbleUser]] = defaultdict(list)
        for row in bg_rows:
            bg_by_id[int(row.user_id)].append(row)

        ice_users_by_server: dict[int, set[str]] = {}
        ice_error_by_server: dict[int, str] = {}
        servers = list(MumbleServer.objects.filter(is_active=True).order_by('display_order', 'name', 'id'))
        for server in servers:
            try:
                with _MurmurServerAdapter(server) as adapter:
                    users = adapter._server_proxy.getRegisteredUsers('') or {}
                ice_users_by_server[int(server.id)] = {str(name or '') for name in users.values()}
            except (MurmurReconcileError, Exception) as exc:  # noqa: BLE001
                ice_error_by_server[int(server.id)] = str(exc)
                ice_users_by_server[int(server.id)] = set()

        all_ids = sorted(set(fg_allow_by_id) | set(fg_deny_by_id) | set(bg_by_id))
        pilots: list[dict[str, Any]] = []
        for id_value in all_ids:
            fg_acl = _acl_from_sets(
                has_permit=bool(fg_allow_by_id.get(id_value)),
                has_deny=bool(fg_deny_by_id.get(id_value)),
            )
            bg_active = any(row.is_active for row in bg_by_id.get(id_value, []))
            bg_deny = any(not row.is_active for row in bg_by_id.get(id_value, []))
            bg_acl = _acl_from_sets(has_permit=bg_active, has_deny=bg_deny)

            pilot_names = sorted(fg_allow_by_id.get(id_value, set()) | fg_deny_by_id.get(id_value, set()))
            if not pilot_names:
                pilot_names = sorted(
                    {
                        str(row.display_name or row.username or row.user.username or '')
                        for row in bg_by_id.get(id_value, [])
                    }
                )
            name_value = ', '.join([name for name in pilot_names if name]) or '-'

            acl_rows: list[dict[str, str]] = []
            if fg_acl == bg_acl:
                acl_rows.append({'db': 'pilot_data,bg_control_data', 'acl': fg_acl})
            else:
                acl_rows.append({'db': 'pilot_data', 'acl': fg_acl})
                acl_rows.append({'db': 'bg_control_data', 'acl': bg_acl})

            ice_rows: list[dict[str, str]] = []
            for row in bg_by_id.get(id_value, []):
                server = row.server
                vsid = server.virtual_server_id if server.virtual_server_id is not None else '-'
                vsid_server = f'{vsid}:{server.name}'
                if int(server.id) in ice_error_by_server:
                    reg = f"ice_error:{_safe(ice_error_by_server[int(server.id)], limit=40)}"
                else:
                    reg = 'registered' if row.username in ice_users_by_server[int(server.id)] else 'not_registered'
                ice_rows.append({'vsid_server': vsid_server, 'registered': reg})

            if not ice_rows:
                ice_rows.append({'vsid_server': '-', 'registered': 'no_bg_control_row'})

            pilots.append(
                {
                    'id': str(id_value),
                    'name': name_value,
                    'acl_rows': acl_rows,
                    'ice_rows': ice_rows,
                }
            )

        report['pilots'] = pilots

        if options['json']:
            self.stdout.write(json.dumps(report, indent=2))
            return

        self.stdout.write('id is the pkid contract identity')
        self.stdout.write(f"FG evaluation status: {report['fg_status']}")
        if report['fg_message']:
            self.stdout.write(f"FG message: {report['fg_message']}")
        self.stdout.write('')

        headers = ['id', 'name', 'db', 'acl', 'vsid:server', 'registered']
        widths = {header: len(header) for header in headers}
        for pilot in pilots:
            max_lines = max(len(pilot['acl_rows']), len(pilot['ice_rows']))
            for idx in range(max_lines):
                acl_row = pilot['acl_rows'][idx] if idx < len(pilot['acl_rows']) else {'db': '', 'acl': ''}
                ice_row = pilot['ice_rows'][idx] if idx < len(pilot['ice_rows']) else {'vsid_server': '', 'registered': ''}
                row_values = {
                    'id': pilot['id'] if idx == 0 else '',
                    'name': pilot['name'] if idx == 0 else '',
                    'db': acl_row['db'],
                    'acl': acl_row['acl'],
                    'vsid:server': ice_row['vsid_server'],
                    'registered': ice_row['registered'],
                }
                for header in headers:
                    widths[header] = max(widths[header], len(str(row_values[header])))

        def _row(values: dict[str, str]) -> str:
            return (
                f"{values['id'].ljust(widths['id'])} | "
                f"{values['name'].ljust(widths['name'])} | "
                f"{values['db'].ljust(widths['db'])} | "
                f"{values['acl'].ljust(widths['acl'])} | "
                f"{values['vsid:server'].ljust(widths['vsid:server'])} | "
                f"{values['registered'].ljust(widths['registered'])}"
            )

        self.stdout.write(_row({h: h for h in headers}))
        self.stdout.write(
            f"{'-' * widths['id']}-+-"
            f"{'-' * widths['name']}-+-"
            f"{'-' * widths['db']}-+-"
            f"{'-' * widths['acl']}-+-"
            f"{'-' * widths['vsid:server']}-+-"
            f"{'-' * widths['registered']}"
        )

        for pilot in pilots:
            max_lines = max(len(pilot['acl_rows']), len(pilot['ice_rows']))
            self.stdout.write(
                f"{'=' * widths['id']}=+="
                f"{'=' * widths['name']}=+="
                f"{'=' * widths['db']}=+="
                f"{'=' * widths['acl']}=+="
                f"{'=' * widths['vsid:server']}=+="
                f"{'=' * widths['registered']}"
            )
            for idx in range(max_lines):
                acl_row = pilot['acl_rows'][idx] if idx < len(pilot['acl_rows']) else {'db': '', 'acl': ''}
                ice_row = pilot['ice_rows'][idx] if idx < len(pilot['ice_rows']) else {'vsid_server': '', 'registered': ''}
                self.stdout.write(
                    _row(
                        {
                            'id': pilot['id'] if idx == 0 else '',
                            'name': pilot['name'] if idx == 0 else '',
                            'db': acl_row['db'],
                            'acl': acl_row['acl'],
                            'vsid:server': ice_row['vsid_server'],
                            'registered': ice_row['registered'],
                        }
                    )
                )
