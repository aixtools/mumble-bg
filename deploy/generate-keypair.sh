#!/usr/bin/env bash
# generate-keypair.sh — Generate BG keypair for password transit encryption.
#
# Usage:
#   ./deploy/generate-keypair.sh [KEY_DIR]
#
# Default KEY_DIR: /etc/mumble-bg/keys
# Creates: private_key.pem (passphrase-protected), public_key.pem
#
# The passphrase is prompted interactively or read from BG_KEY_PASSPHRASE env.
# Public key is world-readable; private key is owner-only.

set -euo pipefail

KEY_DIR="${1:-/etc/mumble-bg/keys}"
PRIVATE_KEY="$KEY_DIR/private_key.pem"
PUBLIC_KEY="$KEY_DIR/public_key.pem"

if [ -f "$PRIVATE_KEY" ]; then
    echo "ERROR: $PRIVATE_KEY already exists. Remove it first or use rotate-keypair.sh" >&2
    exit 1
fi

mkdir -p "$KEY_DIR"
chmod 0755 "$KEY_DIR"

if [ -n "${BG_KEY_PASSPHRASE:-}" ]; then
    PASS_ARGS=(-aes256 -passout "env:BG_KEY_PASSPHRASE")
    echo "Using passphrase from BG_KEY_PASSPHRASE env var"
else
    PASS_ARGS=(-aes256)
    echo "Enter passphrase for the private key:"
fi

# Generate 4096-bit RSA private key (passphrase-protected PKCS8)
openssl genpkey -algorithm RSA \
    -pkeyopt rsa_keygen_bits:4096 \
    "${PASS_ARGS[@]}" \
    -out "$PRIVATE_KEY"

chmod 0600 "$PRIVATE_KEY"

# Extract public key
openssl pkey -in "$PRIVATE_KEY" \
    -pubout \
    ${BG_KEY_PASSPHRASE:+-passin "env:BG_KEY_PASSPHRASE"} \
    -out "$PUBLIC_KEY"

chmod 0644 "$PUBLIC_KEY"

echo ""
echo "Keypair generated:"
echo "  Private: $PRIVATE_KEY (owner-only, passphrase-protected)"
echo "  Public:  $PUBLIC_KEY (world-readable)"
echo ""
echo "Distribute $PUBLIC_KEY to FG for password encryption."
echo "Set BG_KEY_PASSPHRASE in the BG environment file to enable decryption."
