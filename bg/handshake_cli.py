#!/usr/bin/env python3
"""CLI helpers for FG/BG control-handshake maintenance."""

from __future__ import annotations

import argparse
import os

from bg.envtools import bootstrap_bg_environment


def _load_models():
    bootstrap_bg_environment()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bg.settings')
    import django

    django.setup()

    from bg import control_keyring
    from bg.state.models import ControlChannelKey, ControlChannelKeyEntry

    return control_keyring, ControlChannelKey, ControlChannelKeyEntry


def _reset_handshake_state(*, confirm: bool) -> int:
    if not confirm:
        raise SystemExit('Refusing to run without --reset-handshake')

    control_keyring, ControlChannelKey, ControlChannelKeyEntry = _load_models()

    control_key, _ = ControlChannelKey.objects.get_or_create(name='fg_bg')
    db_secret_reset = control_key.shared_secret is not None
    if db_secret_reset:
        control_key.shared_secret = None
        control_key.save(update_fields=['shared_secret', 'updated_at'])

    key_entries_before = ControlChannelKeyEntry.objects.count()
    key_entries_deleted, _ = ControlChannelKeyEntry.objects.all().delete()
    key_entries_after = ControlChannelKeyEntry.objects.count()

    control_keyring.reset_rotation_state()

    print(
        'BG handshake reset complete '
        f'(db_secret_reset={db_secret_reset}, '
        f'key_entries_before={key_entries_before}, '
        f'key_entries_deleted={key_entries_deleted}, '
        f'key_entries_after={key_entries_after})',
        flush=True,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Reset BG-side FG/BG handshake state (DB control secret + keyring entries).',
    )
    parser.add_argument(
        '--reset-handshake',
        action='store_true',
        help='Required acknowledgement for this sensitive reset operation.',
    )
    return parser


def main(argv=None):
    parser = build_parser()
    options = parser.parse_args(argv)
    return _reset_handshake_state(confirm=bool(options.reset_handshake))


if __name__ == '__main__':
    raise SystemExit(main())
