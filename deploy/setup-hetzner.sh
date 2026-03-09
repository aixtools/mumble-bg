#!/bin/bash

set -euo pipefail

if [ "${EUID}" -ne 0 ]; then
    echo "Run as root on the target host."
    exit 1
fi

APP_USER="cube"
APP_HOME="/home/${APP_USER}"
APP_DIR="${APP_HOME}/cube-mumble"
VENV_DIR="${APP_HOME}/.venv/cube-mumble"
ENV_DIR="${APP_HOME}/.env"
ENV_FILE="${ENV_DIR}/cube-mumble"
SERVICE_NAME="cube-mumble-auth"
SERVICE_SRC="${APP_DIR}/deploy/systemd/${SERVICE_NAME}.service"
SERVICE_DEST="/etc/systemd/system/${SERVICE_NAME}.service"

if [ ! -d "${APP_DIR}" ]; then
    echo "Expected repo checkout at ${APP_DIR}"
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

sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install --quiet -r "${APP_DIR}/mumble_authenticator/requirements.txt"

cat > /etc/sudoers.d/cube-mumble << 'EOF'
cube ALL=(ALL) NOPASSWD: /bin/systemctl restart cube-mumble-auth, /bin/systemctl status cube-mumble-auth, /bin/systemctl daemon-reload
EOF
chmod 440 /etc/sudoers.d/cube-mumble

sudo install -D -m 0644 "${SERVICE_SRC}" "${SERVICE_DEST}"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

echo "[OK] ${SERVICE_NAME} installed and restarted."
