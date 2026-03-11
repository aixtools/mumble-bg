#!/usr/bin/env python3
"""Compatibility wrapper for the relocated auth daemon entrypoint."""

from bg.authd.main import *  # noqa: F401,F403


if __name__ == "__main__":
    main()
