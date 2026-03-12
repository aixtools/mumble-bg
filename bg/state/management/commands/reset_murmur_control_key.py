import os

from django.core.management.base import BaseCommand, CommandError

from bg.state.models import ControlChannelKey, MumbleServer

_CONTROL_KEY_NAME = 'fg_bg'


def _active_mode() -> str:
    row = ControlChannelKey.objects.filter(name=_CONTROL_KEY_NAME).only('shared_secret').first()
    if row and row.shared_secret:
        return 'db'
    if os.getenv('MURMUR_CONTROL_PSK', '').strip():
        return 'env'
    return 'open'


def _resolve_server(*, server_id: int | None, server_name: str | None) -> MumbleServer | None:
    if server_id is None and server_name is None:
        return None
    if server_id is not None and server_name is not None:
        raise CommandError('Use either --server-id or --server-name, not both.')

    if server_id is not None:
        server = MumbleServer.objects.filter(pk=server_id, is_active=True).first()
        if server is None:
            raise CommandError(f'No active server found for --server-id={server_id}.')
        return server

    assert server_name is not None
    normalized = server_name.strip()
    if not normalized:
        raise CommandError('--server-name must be a non-empty string.')
    matches = list(MumbleServer.objects.filter(name=normalized, is_active=True))
    if not matches:
        raise CommandError(f'No active server found for --server-name={normalized!r}.')
    if len(matches) > 1:
        raise CommandError('Multiple servers matched --server-name. Use --server-id instead.')
    return matches[0]


class Command(BaseCommand):
    help = (
        'Reset control channel DB key to NULL (CLI-only operation). '
        'Optionally clear one server ice_secret.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--server-id', type=int, help='Optional target server id for ice_secret reset.')
        parser.add_argument('--server-name', type=str, help='Optional target server name for ice_secret reset.')
        parser.add_argument(
            '--yes',
            action='store_true',
            help='Required acknowledgement for this sensitive reset operation.',
        )

    def handle(self, *args, **options):
        if not options['yes']:
            raise CommandError('Refusing to run without --yes.')

        server = _resolve_server(
            server_id=options.get('server_id'),
            server_name=options.get('server_name'),
        )

        control_key, _ = ControlChannelKey.objects.get_or_create(name=_CONTROL_KEY_NAME)
        control_key_reset = control_key.shared_secret is not None
        if control_key_reset:
            control_key.shared_secret = None
            control_key.save(update_fields=['shared_secret', 'updated_at'])

        ice_secret_reset = False
        if server is not None and server.ice_secret is not None:
            server.ice_secret = None
            server.save(update_fields=['ice_secret'])
            ice_secret_reset = True

        self.stdout.write(
            self.style.SUCCESS(
                'Control key reset complete '
                f'(control_key_reset={control_key_reset}, ice_secret_reset={ice_secret_reset}, mode={_active_mode()})'
            )
        )
        if server is not None:
            self.stdout.write(f'Server target: id={server.id} name={server.name}')
