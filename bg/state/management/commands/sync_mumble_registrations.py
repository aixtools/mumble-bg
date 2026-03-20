from django.core.management.base import BaseCommand

from bg.pilot.registrations import MurmurSyncError, sync_murmur_registration
from bg.state.models import MumbleUser


class Command(BaseCommand):
    help = 'Backfill or adopt Murmur registrations for mumble-bg users'

    def add_arguments(self, parser):
        parser.add_argument('--server-id', type=int, help='Only sync one mumble-bg MumbleServer row')
        parser.add_argument('--user-id', type=int, help='Only sync one Django user')
        parser.add_argument('--only-missing-ids', action='store_true', help='Only sync rows missing murmur_userid')
        parser.add_argument('--dry-run', action='store_true', help='Report intended changes without mutating Murmur or BG state')

    def handle(self, *args, **options):
        qs = MumbleUser.objects.select_related('server', 'user').filter(is_active=True, server__is_active=True)
        if options.get('server_id'):
            qs = qs.filter(server_id=options['server_id'])
        if options.get('user_id'):
            qs = qs.filter(user_id=options['user_id'])
        if options.get('only_missing_ids'):
            qs = qs.filter(mumble_userid__isnull=True)

        total = qs.count()
        if total == 0:
            self.stdout.write('No active MumbleUser rows matched.')
            return

        synced = 0
        unchanged = 0
        failed = 0

        for mumble_user in qs.order_by('server__display_order', 'username'):
            current_id = mumble_user.mumble_userid
            if options['dry_run']:
                status = 'missing-id' if current_id is None else f'id={current_id}'
                self.stdout.write(
                    f'DRY RUN {mumble_user.server.name}: {mumble_user.username} ({mumble_user.user.username}) {status}'
                )
                continue

            try:
                synced_userid = sync_murmur_registration(mumble_user)
            except MurmurSyncError as exc:
                failed += 1
                self.stderr.write(
                    f'FAILED {mumble_user.server.name}: {mumble_user.username} ({mumble_user.user.username}) {exc}'
                )
                continue

            if current_id != synced_userid:
                mumble_user.mumble_userid = synced_userid
                mumble_user.save(update_fields=['mumble_userid', 'updated_at'])
                synced += 1
                self.stdout.write(
                    f'SYNCED {mumble_user.server.name}: {mumble_user.username} -> murmur_userid={synced_userid}'
                )
            else:
                unchanged += 1
                self.stdout.write(
                    f'UNCHANGED {mumble_user.server.name}: {mumble_user.username} already mapped to murmur_userid={synced_userid}'
                )

        if options['dry_run']:
            self.stdout.write(f'DRY RUN COMPLETE matched={total}')
            return

        self.stdout.write(
            f'COMPLETE matched={total} synced={synced} unchanged={unchanged} failed={failed}'
        )
