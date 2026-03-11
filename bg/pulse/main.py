#!/usr/bin/env python3
"""CLI entrypoint for the Murmur pulse daemon."""

from __future__ import annotations

import argparse
import os


def _load_service():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bg.settings')
    import django

    django.setup()

    from bg.pulse.service import MurmurPulseError, MurmurPulseService

    return MurmurPulseError, MurmurPulseService


def build_parser():
    parser = argparse.ArgumentParser(
        description='Run Murmur Pulse to track Mumble connect, disconnect, and activity state',
    )
    parser.add_argument('--server-id', type=int, help='Only track one mumble-bg MumbleServer row')
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
    return parser


def run_service(*, server_id=None, poll_interval=30, callback_endpoint='tcp -h 0.0.0.0', once=False):
    _, MurmurPulseService = _load_service()
    service = MurmurPulseService(
        callback_endpoint=callback_endpoint,
        server_id=server_id,
    )
    service.run(
        once=once,
        poll_interval=poll_interval,
    )


def main(argv=None):
    parser = build_parser()
    options = parser.parse_args(argv)
    MurmurPulseError, _ = _load_service()
    try:
        run_service(
            server_id=options.server_id,
            poll_interval=options.poll_interval,
            callback_endpoint=options.callback_endpoint,
            once=options.once,
        )
    except MurmurPulseError as exc:
        raise SystemExit(str(exc)) from exc
