#!/bin/bash

set -euo pipefail


usage() {
    cat <<'EOF'
Usage:
  bash deploy/create-db.sh [--engine ENGINE] --user DB_USER --db DB_NAME --host DB_HOST [--pw DB_PASSWORD]

Creates a local database and login for mumble-bg if they do not already exist.

Arguments:
  --engine   postgres|postgresql|psql or mysql|maria|mariadb; defaults to postgres
  --user     database login/user to create if missing
  --db       database name to create
  --host     application host value (used directly for MySQL grants; kept for env parity on PostgreSQL)
  --pw       password for the database user; if omitted, the script prompts securely

Notes:
  - Run this script as root on the target host.
  - PostgreSQL creation uses: su - postgres -c ...
  - MySQL/MariaDB creation uses the local root client.
  - Existing database users keep their current password.
EOF
}


fail() {
    echo "ERROR: $*" >&2
    exit 1
}


require_root() {
    if [ "${EUID}" -ne 0 ]; then
        fail "run as root"
    fi
}


validate_identifier() {
    local value="$1"
    local label="$2"

    if [[ ! "${value}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
        fail "${label} must match ^[A-Za-z_][A-Za-z0-9_]*$"
    fi
}


validate_host() {
    local value="$1"

    if [[ ! "${value}" =~ ^[%A-Za-z0-9_.:-]+$ ]]; then
        fail "host contains unsupported characters"
    fi
}


sql_literal() {
    printf "%s" "$1" | sed "s/'/''/g"
}


ENGINE="postgres"
DB_USER=""
DB_NAME=""
DB_HOST=""
DB_PASSWORD=""

while [ "$#" -gt 0 ]; do
    case "$1" in
        --engine)
            ENGINE="${2:-}"
            shift 2
            ;;
        --user)
            DB_USER="${2:-}"
            shift 2
            ;;
        --db)
            DB_NAME="${2:-}"
            shift 2
            ;;
        --host)
            DB_HOST="${2:-}"
            shift 2
            ;;
        --pw)
            DB_PASSWORD="${2:-}"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            fail "unknown argument: $1"
            ;;
    esac
done

require_root

[ -n "${DB_USER}" ] || fail "--user is required"
[ -n "${DB_NAME}" ] || fail "--db is required"
[ -n "${DB_HOST}" ] || fail "--host is required"

if [ -z "${DB_PASSWORD}" ]; then
    read -rsp "Password for database user ${DB_USER}: " DB_PASSWORD
    echo
fi

validate_identifier "${DB_USER}" "db user"
validate_identifier "${DB_NAME}" "db name"
validate_host "${DB_HOST}"

ENGINE="$(printf "%s" "${ENGINE}" | tr '[:upper:]' '[:lower:]')"

case "${ENGINE}" in
    postgres|postgresql|psql)
        ENGINE="postgres"
        ;;
    mysql|maria|mariadb)
        ENGINE="mysql"
        ;;
    *)
        fail "--engine must be one of: postgres, postgresql, psql, mysql, maria, mariadb"
        ;;
esac

PASSWORD_SQL="$(sql_literal "${DB_PASSWORD}")"

if [ "${ENGINE}" = "postgres" ]; then
    command -v psql >/dev/null 2>&1 || fail "psql is not installed"

    su - postgres -c "psql -v ON_ERROR_STOP=1 -d postgres" <<EOF
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${DB_USER}') THEN
        CREATE ROLE "${DB_USER}" LOGIN PASSWORD '${PASSWORD_SQL}';
    END IF;
END
\$\$;
SELECT format('CREATE DATABASE %I OWNER %I', '${DB_NAME}', '${DB_USER}')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB_NAME}') \gexec
ALTER DATABASE "${DB_NAME}" OWNER TO "${DB_USER}";
GRANT ALL PRIVILEGES ON DATABASE "${DB_NAME}" TO "${DB_USER}";
EOF

    su - postgres -c "psql -v ON_ERROR_STOP=1 -d ${DB_NAME}" <<EOF
CREATE SCHEMA IF NOT EXISTS "${DB_USER}" AUTHORIZATION "${DB_USER}";
ALTER SCHEMA "${DB_USER}" OWNER TO "${DB_USER}";
ALTER ROLE "${DB_USER}" IN DATABASE "${DB_NAME}" SET search_path TO "${DB_USER}", public;
GRANT ALL PRIVILEGES ON SCHEMA "${DB_USER}" TO "${DB_USER}";
EOF

    echo "[OK] PostgreSQL database ${DB_NAME} and user ${DB_USER} are ready."
    echo "Note: --host=${DB_HOST} is kept for env parity; PostgreSQL access control is handled separately via pg_hba.conf and schema privileges."
    exit 0
fi

command -v mysql >/dev/null 2>&1 || fail "mysql client is not installed"

mysql <<EOF
CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\`;
CREATE USER IF NOT EXISTS '${DB_USER}'@'${DB_HOST}' IDENTIFIED BY '${PASSWORD_SQL}';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'${DB_HOST}';
FLUSH PRIVILEGES;
EOF

echo "[OK] MySQL/MariaDB database ${DB_NAME} and user ${DB_USER}@${DB_HOST} are ready."
