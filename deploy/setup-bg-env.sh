#!/usr/bin/env bash
# setup-bg-env.sh — Create or update BG environment file with key passphrase.
#
# Usage:
#   ./deploy/setup-bg-env.sh [ENV_FILE]
#
# Default ENV_FILE: /etc/mumble-bg/bg.env
#
# Prompts for passphrase if not in BG_PKI_PASSPHRASE env.
# Appends BG_PKI_PASSPHRASE to the env file (creates if needed).
# Sets file to 0600 root:root.

set -euo pipefail

ENV_FILE="${1:-/etc/mumble-bg/bg.env}"

if [ -n "${BG_PKI_PASSPHRASE:-}" ]; then
    PASSPHRASE="$BG_PKI_PASSPHRASE"
elif [ -n "${BG_KEY_PASSPHRASE:-}" ]; then
    echo "WARNING: BG_KEY_PASSPHRASE is deprecated; use BG_PKI_PASSPHRASE instead." >&2
    PASSPHRASE="$BG_KEY_PASSPHRASE"
else
    echo -n "Enter BG_PKI_PASSPHRASE: "
    read -rs PASSPHRASE
    echo ""
fi

if [ -z "$PASSPHRASE" ]; then
    echo "ERROR: Passphrase cannot be empty." >&2
    exit 1
fi

mkdir -p "$(dirname "$ENV_FILE")"

# Remove existing BG_PKI_PASSPHRASE / BG_KEY_PASSPHRASE lines if present
if [ -f "$ENV_FILE" ]; then
    grep -v '^BG_PKI_PASSPHRASE=' "$ENV_FILE" | grep -v '^BG_KEY_PASSPHRASE=' > "$ENV_FILE.tmp" || true
    mv "$ENV_FILE.tmp" "$ENV_FILE"
fi

echo "BG_PKI_PASSPHRASE=$PASSPHRASE" >> "$ENV_FILE"
chmod 0600 "$ENV_FILE"
chown root:root "$ENV_FILE" 2>/dev/null || true

echo "BG_PKI_PASSPHRASE written to: $ENV_FILE (mode 0600)"
