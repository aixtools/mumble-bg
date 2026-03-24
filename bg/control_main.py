#!/usr/bin/env python3
"""Runtime entrypoint for the mumble-bg HTTP control server."""

from __future__ import annotations

import argparse
import os

from bg.envtools import bootstrap_bg_environment, resolve_bg_bind


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the mumble-bg HTTP control server with env-aware bind resolution.",
    )
    parser.add_argument(
        "bind",
        nargs="?",
        help="Optional explicit bind address. If omitted, resolve from BG_BIND or MURMUR_CONTROL_URL.",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    options, runserver_args = parser.parse_known_args(argv)

    bootstrap_bg_environment()

    if options.bind:
        bind = str(options.bind).strip()
        bind_source = "argv"
        bind_detail = "explicit positional bind"
    else:
        bind_info = resolve_bg_bind(os.environ)
        bind = bind_info["bind"]
        bind_source = bind_info["source"]
        bind_detail = bind_info["detail"]

    if bind_source == "default":
        log_message = f"mumble-bg control {bind_detail}, using {bind}"
    else:
        log_message = f"mumble-bg control bind={bind} source={bind_source} detail={bind_detail}"

    print(log_message, flush=True)

    from django.core.management import execute_from_command_line

    execute_from_command_line(["django", "runserver", bind, *runserver_args])


if __name__ == "__main__":
    main()
