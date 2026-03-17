#!/usr/bin/env bash
# setup-bg-env.sh — Create or update BG environment file with key passphrase.
#
# Usage:
#   ./deploy/setup-bg-env.sh [ENV_FILE]
#
# Default ENV_FILE: /etc/mumble-bg/bg.env
#
# Prompts for passphrase if not in BG_KEY_PASSPHRASE env.
# Appends BG_KEY_PASSPHRASE to the env file (creates if needed).
# Sets file to 0600 root:root.

set -euo pipefail

ENV_FILE="${1:-/etc/mumble-bg/bg.env}"

if [ -n "${BG_KEY_PASSPHRASE:-}" ]; then
    PASSPHRASE="$BG_KEY_PASSPHRASE"
else
    echo -n "Enter BG_KEY_PASSPHRASE: "
    read -rs PASSPHRASE
    echo ""
fi

if [ -z "$PASSPHRASE" ]; then
    echo "ERROR: Passphrase cannot be empty." >&2
    exit 1
fi

mkdir -p "$(dirname "$ENV_FILE")"

# Remove existing BG_KEY_PASSPHRASE line if present
if [ -f "$ENV_FILE" ]; then
    grep -v '^BG_KEY_PASSPHRASE=' "$ENV_FILE" > "$ENV_FILE.tmp" || true
    mv "$ENV_FILE.tmp" "$ENV_FILE"
fi

echo "BG_KEY_PASSPHRASE=$PASSPHRASE" >> "$ENV_FILE"
chmod 0600 "$ENV_FILE"
chown root:root "$ENV_FILE" 2>/dev/null || true

echo "BG_KEY_PASSPHRASE written to: $ENV_FILE (mode 0600)"
