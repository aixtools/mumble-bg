#!/usr/bin/env bash
set -euo pipefail

echo "=== BG Django check ==="
python -m django check --settings=bg.settings

echo
echo "=== BG install assistant ==="
python -m django install_assistant --settings=bg.settings

echo
echo "=== BG migration state ==="
python -m django showmigrations state --settings=bg.settings

echo
echo "Preflight complete."
