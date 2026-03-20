"""Provision MumbleUser rows from eligibility evaluation.

Usage:
    python manage.py provision_registrations [--apply] [--json]
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Evaluate eligibility and create/activate/deactivate MumbleUser rows'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Apply changes. Without this flag, runs in dry-run mode.',
        )
        parser.add_argument(
            '--json',
            action='store_true',
            help='Output results as JSON.',
        )

    def handle(self, **options):
        from bg.provisioner import provision_registrations

        result = provision_registrations(
            dry_run=not options['apply'],
        )

        if options['json']:
            self.stdout.write(json.dumps(result.to_dict(), indent=2))
            return

        mode = 'APPLY' if options['apply'] else 'DRY RUN'
        self.stdout.write(
            f'{mode}: created={result.created} activated={result.activated} '
            f'deactivated={result.deactivated} unchanged={result.unchanged}'
        )
        for error in result.errors or []:
            self.stderr.write(f'  ERROR: {error}')
