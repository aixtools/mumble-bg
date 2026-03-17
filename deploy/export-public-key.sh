#!/usr/bin/env bash
# export-public-key.sh — Copy BG's public key to a location accessible by FG.
#
# Usage:
#   ./deploy/export-public-key.sh [KEY_DIR] [DEST]
#
# Default KEY_DIR: /etc/mumble-bg/keys
# Default DEST:    /etc/mumble-fg/bg_public_key.pem
#
# Both FG and BG can read the public key. Only BG can read the private key.

set -euo pipefail

KEY_DIR="${1:-/etc/mumble-bg/keys}"
DEST="${2:-/etc/mumble-fg/bg_public_key.pem}"

PUBLIC_KEY="$KEY_DIR/public_key.pem"

if [ ! -f "$PUBLIC_KEY" ]; then
    echo "ERROR: $PUBLIC_KEY not found. Run generate-keypair.sh first." >&2
    exit 1
fi

mkdir -p "$(dirname "$DEST")"
cp "$PUBLIC_KEY" "$DEST"
chmod 0644 "$DEST"

echo "Public key exported to: $DEST"
echo "Configure FG with: BG_PUBLIC_KEY_PATH=$DEST"
