#!/bin/bash

set -euo pipefail

if [ "${EUID}" -ne 0 ]; then
    echo "Run as root on the target host."
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${APP_DIR:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
APP_USER="${APP_USER:-$(stat -c '%U' "${APP_DIR}")}"
APP_HOME="${APP_HOME:-$(getent passwd "${APP_USER}" | cut -d: -f6)}"
APP_GROUP="${APP_GROUP:-$(id -gn "${APP_USER}")}"
VENV_DIR="${VENV_DIR:-${APP_HOME}/.venv/mumble-bg}"
ENV_DIR="${ENV_DIR:-${APP_HOME}/.env}"
ENV_FILE="${ENV_FILE:-${ENV_DIR}/mumble-bg}"
BG_KEY_DIR="${BG_KEY_DIR:-/etc/mumble-bg/keys}"
SERVICE_UNITS=("bg-control" "bg-authd")
SERVICE_FILES=(
    "/etc/systemd/system/bg-control.service"
    "/etc/systemd/system/bg-authd.service"
)
LEGACY_SERVICE="mumble-bg-auth"
LEGACY_SERVICE_FILE="/etc/systemd/system/${LEGACY_SERVICE}.service"

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

BG_DBMS="${BG_DBMS:-${DATABASES:-}}"
export BG_DBMS

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

if all(key in payload for key in ("host", "username", "database", "password")):
    db_payload = payload
else:
    db_payload = payload.get(object_key)
    if db_payload is None:
        raise SystemExit(f"{env_var} is missing required object: {object_key}")
    if not isinstance(db_payload, dict):
        raise SystemExit(f"{env_var}.{object_key} must be a JSON object")

value = db_payload.get(field, '')
if value is None:
    value = ''
print(value)
PY
}

# Default DB bootstrap engine is PostgreSQL.
# Override only when needed: export BG_ENGINE=mysql
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

BG_DATABASE_NAME="$(json_field BG_DBMS bg database)"
BG_DATABASE_HOST="$(json_field BG_DBMS bg host)"
BG_DATABASE_USER="$(json_field BG_DBMS bg username)"
BG_DATABASE_PASSWORD="$(json_field BG_DBMS bg password)"

if [ -z "${BG_DATABASE_NAME}" ] || [ -z "${BG_DATABASE_HOST}" ] || [ -z "${BG_DATABASE_USER}" ] || [ -z "${BG_DATABASE_PASSWORD}" ]; then
    echo "Expected BG_DBMS JSON with host, username, database, and password in ${ENV_FILE}"
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
sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install --quiet --no-deps "${APP_DIR}"
sudo -u "${APP_USER}" env \
    BG_DBMS="${BG_DBMS}" \
    ENV_FILE="${ENV_FILE}" \
    VENV_DIR="${VENV_DIR}" \
    APP_DIR="${APP_DIR}" \
    bash <<'EOF'
set -euo pipefail
set -a
source "${ENV_FILE}"
set +a
export BG_DBMS
"${VENV_DIR}/bin/python" "${APP_DIR}/manage.py" migrate --noinput
EOF

if systemctl list-unit-files "${LEGACY_SERVICE}.service" >/dev/null 2>&1; then
    systemctl stop "${LEGACY_SERVICE}" || true
    systemctl disable "${LEGACY_SERVICE}" || true
fi
rm -f "${LEGACY_SERVICE_FILE}"

cat > /etc/sudoers.d/mumble-bg <<EOF
${APP_USER} ALL=(ALL) NOPASSWD: /bin/systemctl restart bg-control, /bin/systemctl restart bg-authd, /bin/systemctl status bg-control, /bin/systemctl status bg-authd, /bin/systemctl is-active bg-control, /bin/systemctl is-active bg-authd, /bin/systemctl daemon-reload, /bin/bash ${APP_DIR}/deploy/create-db.sh *
EOF
chmod 440 /etc/sudoers.d/mumble-bg

"${VENV_DIR}/bin/python" "${APP_DIR}/manage.py" print_systemd_bg_control \
    --env-file "${ENV_FILE}" \
    --working-dir "${APP_DIR}" \
    --user "${APP_USER}" \
    --group "${APP_GROUP}" \
    --key-dir "${BG_KEY_DIR}" \
    > "${SERVICE_FILES[0]}"

"${VENV_DIR}/bin/python" "${APP_DIR}/manage.py" print_systemd_bg_authd \
    --env-file "${ENV_FILE}" \
    --working-dir "${APP_DIR}" \
    --user "${APP_USER}" \
    --group "${APP_GROUP}" \
    > "${SERVICE_FILES[1]}"

chmod 0644 "${SERVICE_FILES[@]}"
systemctl daemon-reload
systemctl enable "${SERVICE_UNITS[@]}"
systemctl restart "${SERVICE_UNITS[@]}"

echo "[OK] ${SERVICE_UNITS[*]} installed and restarted."
