#!/usr/bin/env python3
"""CLI entrypoint for the Murmur pulse daemon."""

from __future__ import annotations

import argparse
import json
import os


def _load_service():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bg.settings')
    import django

    django.setup()

    from bg.pulse.service import MurmurPulseError, MurmurPulseService

    return MurmurPulseError, MurmurPulseService


def _load_reconciler():
    """Load Django and the registration reconciler."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bg.settings')
    import django

    django.setup()

    from bg.pulse.reconciler import MurmurReconcileError, MurmurRegistrationReconciler

    return MurmurReconcileError, MurmurRegistrationReconciler


def build_parser():
    parser = argparse.ArgumentParser(
        description='Run Murmur Pulse to track Mumble connect, disconnect, and activity state',
    )
    parser.add_argument('--server-id', type=int, help='Only track one mumble-bg MumbleServer row')
    parser.add_argument(
        '--reconcile',
        action='store_true',
        help='Build/apply Murmur registration diffs instead of live presence pulse'
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
    return parser


def _reconcile_once(*, server_id=None, apply=False, json_output=False):
    MurmurReconcileError, MurmurRegistrationReconciler = _load_reconciler()
    reconciler = MurmurRegistrationReconciler(server_id=server_id)
    results = reconciler.reconcile(dry_run=not apply)
    payload = [result.to_dict() for result in results]
    if json_output:
        print(json.dumps(payload, indent=2), flush=True)
        return

    mode = 'APPLY' if apply else 'DRY RUN'
    for result in payload:
        print(
            f"{mode} server={result['server_name']} "
            f"create={result['planned_create_count']} "
            f"delete={result['planned_delete_count']} "
            f"applied={result['changed_count']} "
            f"failed={result['failed_count']}",
            flush=True,
        )
        for error in result['errors']:
            print(f'  ERROR: {error}', flush=True)


def run_service(
    *,
    server_id=None,
    poll_interval=30,
    callback_endpoint='tcp -h 0.0.0.0',
    once=False,
    reconcile=False,
    apply=False,
    json_output=False,
):
    if reconcile:
        return _reconcile_once(
            server_id=server_id,
            apply=apply,
            json_output=json_output,
        )

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
    if options.reconcile and options.poll_interval != 30:
        parser.error('--poll-interval has no effect when --reconcile is set')
    if options.reconcile and options.callback_endpoint != 'tcp -h 0.0.0.0':
        parser.error('--callback-endpoint has no effect when --reconcile is set')
    if options.apply and not options.reconcile:
        parser.error('--apply requires --reconcile')
    if options.json and not options.reconcile:
        parser.error('--json requires --reconcile')

    if options.reconcile:
        _, MurmurReconcileError = _load_reconciler()
        try:
            run_service(
                server_id=options.server_id,
                poll_interval=options.poll_interval,
                callback_endpoint=options.callback_endpoint,
                once=options.once,
                reconcile=options.reconcile,
                apply=options.apply,
                json_output=options.json,
            )
            return
        except MurmurReconcileError as exc:
            raise SystemExit(str(exc)) from exc

    MurmurPulseError, _ = _load_service()
    try:
        run_service(
            server_id=options.server_id,
            poll_interval=options.poll_interval,
            callback_endpoint=options.callback_endpoint,
            once=options.once,
            reconcile=options.reconcile,
            apply=options.apply,
            json_output=options.json,
        )
    except MurmurPulseError as exc:
        raise SystemExit(str(exc)) from exc
