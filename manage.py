#!/usr/bin/env python3
"""Manage utility for local mumble-bg Django-managed tables."""

import os
import sys


def main():
    from bg.envtools import bootstrap_bg_environment

    bootstrap_bg_environment()

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise SystemExit(
            'Django is required for migrations. Install with: pip install django'
        ) from exc

    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
