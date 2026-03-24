import os

from django.core.management.base import BaseCommand, CommandError

from bg.state.models import ControlChannelKey

_CONTROL_KEY_NAME = 'fg_bg'


def _active_mode() -> str:
    row = ControlChannelKey.objects.filter(name=_CONTROL_KEY_NAME).only('shared_secret').first()
    if row and row.shared_secret:
        return 'db'
    if (os.getenv('BG_PSK') or '').strip():
        return 'env'
    return 'open'


class Command(BaseCommand):
    help = 'Reset FG/BG control channel DB key to NULL (CLI-only operation).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--yes',
            action='store_true',
            help='Required acknowledgement for this sensitive reset operation.',
        )

    def handle(self, *args, **options):
        if not options['yes']:
            raise CommandError('Refusing to run without --yes.')

        control_key, _ = ControlChannelKey.objects.get_or_create(name=_CONTROL_KEY_NAME)
        control_key_reset = control_key.shared_secret is not None
        if control_key_reset:
            control_key.shared_secret = None
            control_key.save(update_fields=['shared_secret', 'updated_at'])

        self.stdout.write(
            self.style.SUCCESS(
                'Control key reset complete '
                f'(control_key_reset={control_key_reset}, mode={_active_mode()})'
            )
        )
