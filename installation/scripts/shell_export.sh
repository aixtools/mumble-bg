#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 KEY VALUE..."
  echo "Example:"
  echo "  $0 ICE_SECRET \"'CubeiNive'\""
  exit 1
fi

key="$1"
shift
value="$*"

if ! [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  echo "Invalid shell variable name: $key" >&2
  exit 1
fi

quoted="$(python3 -c 'import shlex,sys; print(shlex.quote(sys.argv[1]))' "$value")"
echo "export ${key}=${quoted}"
