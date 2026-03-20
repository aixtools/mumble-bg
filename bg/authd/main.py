#!/usr/bin/env python3
"""CLI entrypoint for the mumble-bg auth daemon."""

from __future__ import annotations

from bg.envtools import bootstrap_bg_environment


def main(argv=None):
    if argv is not None:
        raise SystemExit('bg.authd does not accept CLI arguments yet')
    bootstrap_bg_environment()
    from bg.authd.service import main as run_authd

    run_authd()


if __name__ == '__main__':
    main()
