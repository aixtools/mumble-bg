#!/usr/bin/env python3
"""Manage utility for local cube-monitor Django-managed tables."""

import os
import sys


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'authenticator.django_settings')

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise SystemExit(
            'Django is required for migrations. Install with: pip install django'
        ) from exc

    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
