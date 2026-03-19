#!/usr/bin/env bash
set -euo pipefail

missing=0

check_var() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "MISSING: ${name}"
    missing=1
  else
    echo "OK: ${name}=${!name}"
  fi
}

echo "=== FG control env check ==="
check_var OPTIONAL_APPS
check_var MURMUR_CONTROL_URL
check_var MURMUR_CONTROL_PSK

if [[ "${OPTIONAL_APPS:-}" != *"mumble_ui.apps.MumbleUiConfig"* ]]; then
  echo "MISSING: OPTIONAL_APPS must include mumble_ui.apps.MumbleUiConfig"
  missing=1
fi

if [[ "${missing}" -ne 0 ]]; then
  echo
  echo "FG env check failed."
  exit 1
fi

echo
echo "FG env check passed."
