from django.core.management.base import BaseCommand, CommandError

from bg.pulse.main import run_service
from bg.pulse.service import MurmurPulseError
from bg.pulse.reconciler import MurmurReconcileError


class Command(BaseCommand):
    help = 'Run Murmur Pulse to track Mumble connect, disconnect, and activity state'

    def add_arguments(self, parser):
        parser.add_argument('--server-id', type=int, help='Only track one mumble-bg MumbleServer row')
        parser.add_argument(
            '--reconcile',
            action='store_true',
            help='Build/apply Murmur registration diffs instead of presence pulse tracking'
        )
        parser.add_argument(
            '--apply',
            action='store_true',
            help='When --reconcile is set, apply the planned changes',
        )
        parser.add_argument(
            '--json',
            action='store_true',
            help='When --reconcile is set, emit reconciliation result as JSON',
        )
        parser.add_argument(
            '--poll-interval',
            type=int,
            default=30,
            help='Seconds between reconciliation snapshots',
        )
        parser.add_argument(
            '--callback-endpoint',
            default='tcp -h 0.0.0.0',
            help='ICE endpoint definition for receiving Murmur callbacks',
        )
        parser.add_argument(
            '--once',
            action='store_true',
            help='Perform one reconciliation pass and exit',
        )

    def handle(self, *args, **options):
        try:
            run_service(
                server_id=options.get('server_id'),
                callback_endpoint=options['callback_endpoint'],
                once=options['once'],
                poll_interval=options['poll_interval'],
                reconcile=options['reconcile'],
                apply=options['apply'],
                json_output=options['json'],
            )
        except (MurmurPulseError, MurmurReconcileError) as exc:
            raise CommandError(str(exc)) from exc
