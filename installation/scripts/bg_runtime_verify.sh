#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:18080}"

echo "=== BG health (${BASE_URL}/v1/health) ==="
curl -fsS "${BASE_URL}/v1/health" | python -m json.tool

echo
echo "=== BG public key (${BASE_URL}/v1/public-key) ==="
curl -fsS "${BASE_URL}/v1/public-key" | sed -n '1,5p'
echo "..."

echo
echo "=== ICE users ==="
python -m django list_ice_users --settings=bg.settings

echo
echo "Runtime verification complete."
