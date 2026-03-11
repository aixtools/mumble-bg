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
VENV_DIR="${VENV_DIR:-${APP_HOME}/.venv/mumble-bg}"
ENV_DIR="${ENV_DIR:-${APP_HOME}/.env}"
ENV_FILE="${ENV_FILE:-${ENV_DIR}/mumble-bg}"
SERVICE_NAME="mumble-bg-auth"
SERVICE_DEST="/etc/systemd/system/${SERVICE_NAME}.service"

if [ ! -d "${APP_DIR}" ]; then
    echo "Expected repo checkout at ${APP_DIR}"
    exit 1
fi

if [ -z "${APP_HOME}" ]; then
    echo "Could not determine home directory for ${APP_USER}"
    exit 1
fi

if ! sudo -u "${APP_USER}" test -r "${APP_DIR}/bg/authd/main.py"; then
    echo "User ${APP_USER} cannot read ${APP_DIR}. Adjust permissions or set APP_DIR/APP_USER."
    exit 1
fi

apt-get update -qq
apt-get install -y -qq python3 python3-venv

mkdir -p "${APP_HOME}/.venv" "${ENV_DIR}"
chown -R "${APP_USER}:${APP_USER}" "${APP_HOME}/.venv" "${ENV_DIR}"

if [ ! -f "${ENV_FILE}" ]; then
    echo "Expected environment file at ${ENV_FILE}"
    exit 1
fi

if [ ! -d "${VENV_DIR}" ]; then
    sudo -u "${APP_USER}" python3 -m venv "${VENV_DIR}"
fi

sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install --quiet -r "${APP_DIR}/requirements.txt"

cat > /etc/sudoers.d/mumble-bg << 'EOF'
cube ALL=(ALL) NOPASSWD: /bin/systemctl restart mumble-bg-auth, /bin/systemctl status mumble-bg-auth, /bin/systemctl daemon-reload
EOF
chmod 440 /etc/sudoers.d/mumble-bg

cat > "${SERVICE_DEST}" <<EOF
[Unit]
Description=mumble-bg ICE authenticator
After=network.target postgresql.service mumble-server.service

[Service]
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${VENV_DIR}/bin/python -m bg.authd
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

chmod 0644 "${SERVICE_DEST}"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

echo "[OK] ${SERVICE_NAME} installed and restarted."
