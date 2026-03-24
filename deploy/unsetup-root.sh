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
VENV_DIR="${VENV_DIR:-${APP_HOME}/.venv/mumble-bg}"
ENV_FILE="${ENV_FILE:-${APP_HOME}/.env/mumble-bg}"

SERVICES=(
    "bg-control"
    "bg-authd"
    "mumble-bg-auth"
)

SUDOERS_FILES=(
    "/etc/sudoers.d/mumble-bg"
)

SERVICE_FILES=(
    "/etc/systemd/system/bg-control.service"
    "/etc/systemd/system/bg-authd.service"
    "/etc/systemd/system/mumble-bg-auth.service"
)

DROP_DB_MESSAGE="not attempted"

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
    raise SystemExit(1)

payload = json.loads(raw)
if not isinstance(payload, dict):
    raise SystemExit(1)

if all(key in payload for key in ("host", "username", "database", "password")):
    db_payload = payload
else:
    db_payload = payload.get(object_key)
    if db_payload is None or not isinstance(db_payload, dict):
        raise SystemExit(1)

value = db_payload.get(field, '')
if value is None:
    value = ''
print(value)
PY
}

if [ -f "${ENV_FILE}" ]; then
    set -a
    source "${ENV_FILE}"
    set +a

    BG_DBMS="${BG_DBMS:-${DATABASES:-}}"
    export BG_DBMS

    BG_DATABASE_NAME="$(json_field BG_DBMS bg database 2>/dev/null || true)"
    BG_DATABASE_HOST="$(json_field BG_DBMS bg host 2>/dev/null || true)"

    if [ -n "${BG_DATABASE_NAME}" ] && [[ "${BG_DATABASE_HOST}" =~ ^(127\.0\.0\.1|localhost)?$ ]]; then
        if command -v sudo >/dev/null 2>&1; then
            sudo -u postgres psql -v ON_ERROR_STOP=1 -d postgres -v db_name="${BG_DATABASE_NAME}" <<'SQL'
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = :'db_name'
  AND pid <> pg_backend_pid();
SQL
            sudo -u postgres dropdb --if-exists "${BG_DATABASE_NAME}"
            DROP_DB_MESSAGE="dropped local PostgreSQL database ${BG_DATABASE_NAME}"
        else
            DROP_DB_MESSAGE="skipped local BG database drop (sudo not available)"
        fi
    elif [ -n "${BG_DATABASE_NAME}" ]; then
        DROP_DB_MESSAGE="skipped BG database drop for non-local host ${BG_DATABASE_HOST}"
    fi
fi

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
for service in "${SERVICES[@]}"; do
    systemctl reset-failed "${service}" >/dev/null 2>&1 || true
done

if [ -d "${VENV_DIR}" ]; then
    rm -rf "${VENV_DIR}"
fi

cat <<EOF
[OK] Removed mumble-bg deployment artifacts.

Removed:
- systemd units for bg-control/bg-authd and legacy mumble-bg-auth
- sudoers file for mumble-bg
- virtualenv ${VENV_DIR}
- ${DROP_DB_MESSAGE}

Kept:
- repo checkout ${APP_DIR}
- environment file ${ENV_FILE}
EOF
