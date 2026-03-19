#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-$HOME/.env/mumble-bg}"

if [[ ! -f "$env_file" ]]; then
  echo "Missing env file: $env_file" >&2
  exit 1
fi

if ! bash -n "$env_file" >/dev/null 2>&1; then
  echo "Shell syntax check failed for: $env_file" >&2
  echo "Fix syntax first (example: unmatched quotes)." >&2
  bash -n "$env_file" || true
  exit 1
fi

mapfile -t keys < <(
  awk '
    match($0, /^[[:space:]]*(export[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=/, m) {
      print m[2]
    }
  ' "$env_file" | awk '!seen[$0]++'
)

if [[ ${#keys[@]} -eq 0 ]]; then
  echo "No KEY=VALUE assignments found in: $env_file"
  exit 0
fi

echo "Scanning: $env_file"
echo
echo "Only variables with tricky characters are shown."
echo

bash -c '
  set -euo pipefail
  env_file="$1"
  shift
  set -a
  # shellcheck disable=SC1090
  source "$env_file"
  set +a
  for k in "$@"; do
    v="${!k-}"
    if printf "%s" "$v" | grep -qE "[[:space:]'\"\\\\\$#]"; then
      printf "KEY: %s\n" "$k"
      printf "VALUE: %s\n" "$v"
      printf "SAFE : export %s=%q\n\n" "$k" "$v"
    fi
  done
' _ "$env_file" "${keys[@]}"
