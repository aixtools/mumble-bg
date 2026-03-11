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

set -a
source "${ENV_FILE}"
set +a

json_field() {
    local env_var="$1"
    local object_key="$2"
    local field="$3"
    python3 - "$env_var" "$object_key" "$field" <<'PY'
import json
import os
import sys

env_var = sys.argv[1]
object_key = sys.argv[2]
field = sys.argv[3]
raw = os.environ.get(env_var, '').strip()
if not raw:
    raise SystemExit(f"{env_var} is not set")

try:
    payload = json.loads(raw)
except json.JSONDecodeError as exc:
    raise SystemExit(f"{env_var} must be valid JSON: {exc}") from exc

if not isinstance(payload, dict):
    raise SystemExit(f"{env_var} must be a JSON object")

payload = payload.get(object_key)
if payload is None:
    raise SystemExit(f"{env_var} is missing required object: {object_key}")
if not isinstance(payload, dict):
    raise SystemExit(f"{env_var}.{object_key} must be a JSON object")

value = payload.get(field, '')
if value is None:
    value = ''
print(value)
PY
}

BG_ENGINE="${BG_ENGINE:-postgres}"

case "${BG_ENGINE}" in
    postgres|postgresql|psql|'')
        BG_ENGINE="postgres"
        ;;
    mysql|maria|mariadb)
        BG_ENGINE="mysql"
        ;;
    *)
        echo "Unsupported BG_ENGINE=${BG_ENGINE}"
        exit 1
        ;;
esac

case "${BG_ENGINE}" in
    postgres)
        apt-get install -y -qq postgresql-client
        ;;
    mysql)
        apt-get install -y -qq default-mysql-client
        ;;
esac

if [ ! -d "${VENV_DIR}" ]; then
    sudo -u "${APP_USER}" python3 -m venv "${VENV_DIR}"
fi

BG_DATABASE_NAME="$(json_field DATABASES bg database)"
BG_DATABASE_HOST="$(json_field DATABASES bg host)"
BG_DATABASE_USER="$(json_field DATABASES bg username)"
BG_DATABASE_PASSWORD="$(json_field DATABASES bg password)"

if [ -z "${BG_DATABASE_NAME}" ] || [ -z "${BG_DATABASE_HOST}" ] || [ -z "${BG_DATABASE_USER}" ] || [ -z "${BG_DATABASE_PASSWORD}" ]; then
    echo "Expected DATABASES.bg JSON with host, username, database, and password in ${ENV_FILE}"
    exit 1
fi

case "${BG_DATABASE_HOST}" in
    127.0.0.1|localhost)
        bash "${APP_DIR}/deploy/create-db.sh" \
            --engine "${BG_ENGINE}" \
            --user "${BG_DATABASE_USER}" \
            --db "${BG_DATABASE_NAME}" \
            --host "${BG_DATABASE_HOST}" \
            --pw "${BG_DATABASE_PASSWORD}"
        ;;
    *)
        echo "[WARN] Skipping local bg database bootstrap for non-local host ${BG_DATABASE_HOST}"
        ;;
esac

sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install --quiet -r "${APP_DIR}/requirements.txt"
sudo -u "${APP_USER}" env \
    DATABASES="${DATABASES}" \
    "${VENV_DIR}/bin/python" "${APP_DIR}/manage.py" migrate --noinput

cat > /etc/sudoers.d/mumble-bg << 'EOF'
cube ALL=(ALL) NOPASSWD: /bin/systemctl restart mumble-bg-auth, /bin/systemctl status mumble-bg-auth, /bin/systemctl daemon-reload, /bin/bash /home/cube/mumble-bg/deploy/create-db.sh *
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
