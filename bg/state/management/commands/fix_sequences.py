"""Reset PostgreSQL id sequences past MAX(id) for every table that has one.

After a bulk import (e.g. import-mumble-db.sh) PostgreSQL sequences are not
advanced — only explicit INSERTs touching an `id` column update the sequence
when called via `nextval()`. The next ORM-driven INSERT can then collide with
an existing primary key and raise IntegrityError, which has cascaded into 500s
on customer-facing flows.

This command iterates every base table in the public schema, looks up the
sequence backing its `id` column (if any), and bumps `last_value` to
`MAX(id) + 1` (with `is_called=false` so the next nextval returns that value).

Idempotent and read-mostly — safe to run any time.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connections, router

from bg.state.models import MumbleUser


class Command(BaseCommand):
    help = 'Reset PostgreSQL id sequences past MAX(id) for every applicable table.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print what would change without writing.',
        )
        parser.add_argument(
            '--database',
            default=None,
            help='Database alias to operate on (defaults to the bg model router target).',
        )

    def handle(self, **options):
        alias = options['database'] or router.db_for_write(MumbleUser) or 'default'
        connection = connections[alias]
        if connection.vendor != 'postgresql':
            self.stdout.write(f'Skipping: {alias} is {connection.vendor}, not postgresql.')
            return

        dry_run = bool(options['dry_run'])

        with connection.cursor() as cursor:
            # Tables aren't always in `public` — a per-role default schema
            # (e.g. PG `mumble_bg` role creating its own schema) will land
            # objects outside it. Target every schema reachable via the
            # current search_path.
            cursor.execute(
                """
                SELECT c.table_schema, c.table_name
                FROM information_schema.columns AS c
                JOIN information_schema.tables AS t
                  ON t.table_schema = c.table_schema
                 AND t.table_name = c.table_name
                WHERE c.table_schema = ANY (current_schemas(false))
                  AND c.column_name = 'id'
                  AND t.table_type = 'BASE TABLE'
                ORDER BY c.table_schema, c.table_name
                """
            )
            tables = cursor.fetchall()

            updated = 0
            skipped = 0
            for schema, table in tables:
                qualified = f'"{schema}"."{table}"'
                qualified_label = f'{schema}.{table}'
                cursor.execute(
                    "SELECT pg_get_serial_sequence(%s, 'id')",
                    [qualified],
                )
                seq = cursor.fetchone()[0]
                if not seq:
                    skipped += 1
                    continue

                cursor.execute(
                    f'SELECT COALESCE(MAX(id), 0) FROM {qualified}'  # noqa: S608 — ident from system catalog
                )
                max_id = int(cursor.fetchone()[0] or 0)
                target = max_id + 1

                cursor.execute(f"SELECT last_value, is_called FROM {seq}")
                last_value, is_called = cursor.fetchone()
                effective = int(last_value) + (1 if is_called else 0)

                if effective > max_id:
                    self.stdout.write(
                        f'OK    {qualified_label:50s} max(id)={max_id} sequence_next={effective}'
                    )
                    skipped += 1
                    continue

                if dry_run:
                    self.stdout.write(
                        f'DRY   {qualified_label:50s} max(id)={max_id} sequence_next={effective} -> {target}'
                    )
                else:
                    cursor.execute('SELECT setval(%s, %s, false)', [seq, target])
                    self.stdout.write(
                        f'FIXED {qualified_label:50s} max(id)={max_id} sequence_next={effective} -> {target}'
                    )
                updated += 1

        self.stdout.write('')
        self.stdout.write(
            f'{"Would update" if dry_run else "Updated"} {updated} sequence(s); '
            f'{skipped} already-healthy or non-id table(s).'
        )
