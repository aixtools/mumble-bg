#!/bin/bash

set -euo pipefail

if [ "${EUID}" -ne 0 ]; then
    echo "Run as root on the target host."
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${APP_DIR:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
APP_USER="${APP_USER:-cube}"
APP_HOME="${APP_HOME:-$(getent passwd "${APP_USER}" | cut -d: -f6)}"
VENV_DIR="${VENV_DIR:-${APP_HOME}/.venv/cube-monitor}"
ENV_FILE="${ENV_FILE:-${APP_HOME}/.env/cube-monitor}"

SERVICES=(
    "cube-monitor-auth"
    "cube-mumble-auth"
)

SUDOERS_FILES=(
    "/etc/sudoers.d/cube-monitor"
    "/etc/sudoers.d/cube-mumble"
)

SERVICE_FILES=(
    "/etc/systemd/system/cube-monitor-auth.service"
    "/etc/systemd/system/cube-mumble-auth.service"
)

for service in "${SERVICES[@]}"; do
    if systemctl list-unit-files "${service}.service" >/dev/null 2>&1; then
        systemctl stop "${service}" || true
        systemctl disable "${service}" || true
    fi
done

for service_file in "${SERVICE_FILES[@]}"; do
    rm -f "${service_file}"
done

for sudoers_file in "${SUDOERS_FILES[@]}"; do
    rm -f "${sudoers_file}"
done

systemctl daemon-reload
systemctl reset-failed cube-monitor-auth cube-mumble-auth || true

if [ -d "${VENV_DIR}" ]; then
    rm -rf "${VENV_DIR}"
fi

cat <<EOF
[OK] Removed Cube monitor auth deployment artifacts.

Removed:
- systemd units for cube-monitor-auth and cube-mumble-auth
- sudoers files for cube-monitor and cube-mumble
- virtualenv ${VENV_DIR}

Kept:
- repo checkout ${APP_DIR}
- environment file ${ENV_FILE}
EOF
