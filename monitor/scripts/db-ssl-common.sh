#!/usr/bin/env bash
set -euo pipefail

db_ssl_die() {
    echo "error: $*" >&2
    exit 1
}

db_ssl_require_command() {
    command -v "$1" >/dev/null 2>&1 || db_ssl_die "missing required command: $1"
}

db_ssl_parse_args() {
    OUTDIR=""
    SERVER_HOST=""
    SERVER_NAME=""
    CA_NAME="Monitor DB SSL CA"
    CLIENT_NAME="monitor"
    DAYS="825"
    FORCE=0
    MONITOR_USER="monitor"
    MONITOR_HOST="monitor.example.com"
    MONITOR_DIR="/etc/monitor"
    DB_NAME="dbname"
    DB_USER="monitor"
    MONITOR_SOURCE_CIDR="monitor.client.ip/32"
    SERVER_IPS=()

    while [ $# -gt 0 ]; do
        case "$1" in
            --out)
                OUTDIR="${2:-}"
                shift 2
                ;;
            --server-host)
                SERVER_HOST="${2:-}"
                shift 2
                ;;
            --server-name)
                SERVER_NAME="${2:-}"
                shift 2
                ;;
            --server-ip)
                SERVER_IPS+=("${2:-}")
                shift 2
                ;;
            --ca-name)
                CA_NAME="${2:-}"
                shift 2
                ;;
            --client-name)
                CLIENT_NAME="${2:-}"
                shift 2
                ;;
            --days)
                DAYS="${2:-}"
                shift 2
                ;;
            --monitor-user)
                MONITOR_USER="${2:-}"
                shift 2
                ;;
            --monitor-host)
                MONITOR_HOST="${2:-}"
                shift 2
                ;;
            --monitor-dir)
                MONITOR_DIR="${2:-}"
                shift 2
                ;;
            --db-name)
                DB_NAME="${2:-}"
                shift 2
                ;;
            --db-user)
                DB_USER="${2:-}"
                shift 2
                ;;
            --monitor-source-cidr)
                MONITOR_SOURCE_CIDR="${2:-}"
                shift 2
                ;;
            --force)
                FORCE=1
                shift
                ;;
            --help|-h)
                return 64
                ;;
            *)
                db_ssl_die "unknown argument: $1"
                ;;
        esac
    done

    [ -n "$OUTDIR" ] || db_ssl_die "--out is required"
    [ -n "$SERVER_HOST" ] || db_ssl_die "--server-host is required"
    [ -n "$MONITOR_DIR" ] || db_ssl_die "--monitor-dir must not be empty"
    [ -n "$DB_NAME" ] || db_ssl_die "--db-name must not be empty"
    [ -n "$DB_USER" ] || db_ssl_die "--db-user must not be empty"
    [ -n "$SERVER_NAME" ] || SERVER_NAME="$SERVER_HOST"

    db_ssl_require_command openssl

    OUTDIR="$(mkdir -p "$OUTDIR" && cd "$OUTDIR" && pwd)"
    CA_DIR="$OUTDIR/ca"
    SERVER_DIR="$OUTDIR/server"
    CLIENT_DIR="$OUTDIR/client"
    EXAMPLES_DIR="$OUTDIR/examples"
    mkdir -p "$CA_DIR" "$SERVER_DIR" "$CLIENT_DIR" "$EXAMPLES_DIR"

    if [ "$FORCE" -ne 1 ] && {
        [ -e "$CA_DIR/ca-key.pem" ] ||
        [ -e "$SERVER_DIR/server-key.pem" ] ||
        [ -e "$CLIENT_DIR/${CLIENT_NAME}-client-key.pem" ];
    }; then
        db_ssl_die "output directory already contains generated material; use --force to overwrite"
    fi

    if [ "$FORCE" -eq 1 ]; then
        rm -f \
            "$CA_DIR/ca-key.pem" \
            "$CA_DIR/ca-cert.pem" \
            "$CA_DIR/ca-cert.srl" \
            "$SERVER_DIR/server-key.pem" \
            "$SERVER_DIR/server.csr" \
            "$SERVER_DIR/server-cert.pem" \
            "$SERVER_DIR/server.ext" \
            "$CLIENT_DIR/${CLIENT_NAME}-client-key.pem" \
            "$CLIENT_DIR/${CLIENT_NAME}-client.csr" \
            "$CLIENT_DIR/${CLIENT_NAME}-client-cert.pem" \
            "$CLIENT_DIR/${CLIENT_NAME}-client.ext"
    fi
}

db_ssl_generate_ca() {
    openssl genrsa -out "$CA_DIR/ca-key.pem" 4096 >/dev/null 2>&1
    openssl req \
        -x509 \
        -new \
        -nodes \
        -key "$CA_DIR/ca-key.pem" \
        -sha256 \
        -days "$DAYS" \
        -out "$CA_DIR/ca-cert.pem" \
        -subj "/CN=$CA_NAME" >/dev/null 2>&1
}

db_ssl_write_server_ext() {
    local ext_file="$SERVER_DIR/server.ext"
    {
        echo "basicConstraints=CA:FALSE"
        echo "keyUsage=digitalSignature,keyEncipherment"
        echo "extendedKeyUsage=serverAuth"
        echo "subjectAltName=@alt_names"
        echo
        echo "[alt_names]"
        echo "DNS.1=$SERVER_HOST"
        local idx=2
        local ip_idx=1
        local entry
        for entry in "${SERVER_IPS[@]}"; do
            echo "IP.$ip_idx=$entry"
            ip_idx=$((ip_idx + 1))
        done
        if [ "$SERVER_NAME" != "$SERVER_HOST" ]; then
            echo "DNS.$idx=$SERVER_NAME"
        fi
    } >"$ext_file"
}

db_ssl_generate_server_cert() {
    db_ssl_write_server_ext
    openssl genrsa -out "$SERVER_DIR/server-key.pem" 4096 >/dev/null 2>&1
    openssl req \
        -new \
        -key "$SERVER_DIR/server-key.pem" \
        -out "$SERVER_DIR/server.csr" \
        -subj "/CN=$SERVER_NAME" >/dev/null 2>&1
    openssl x509 \
        -req \
        -in "$SERVER_DIR/server.csr" \
        -CA "$CA_DIR/ca-cert.pem" \
        -CAkey "$CA_DIR/ca-key.pem" \
        -CAcreateserial \
        -out "$SERVER_DIR/server-cert.pem" \
        -days "$DAYS" \
        -sha256 \
        -extfile "$SERVER_DIR/server.ext" >/dev/null 2>&1
}

db_ssl_generate_client_cert() {
    local client_ext="$CLIENT_DIR/${CLIENT_NAME}-client.ext"
    {
        echo "basicConstraints=CA:FALSE"
        echo "keyUsage=digitalSignature,keyEncipherment"
        echo "extendedKeyUsage=clientAuth"
    } >"$client_ext"

    openssl genrsa -out "$CLIENT_DIR/${CLIENT_NAME}-client-key.pem" 4096 >/dev/null 2>&1
    openssl req \
        -new \
        -key "$CLIENT_DIR/${CLIENT_NAME}-client-key.pem" \
        -out "$CLIENT_DIR/${CLIENT_NAME}-client.csr" \
        -subj "/CN=$CLIENT_NAME" >/dev/null 2>&1
    openssl x509 \
        -req \
        -in "$CLIENT_DIR/${CLIENT_NAME}-client.csr" \
        -CA "$CA_DIR/ca-cert.pem" \
        -CAkey "$CA_DIR/ca-key.pem" \
        -CAcreateserial \
        -out "$CLIENT_DIR/${CLIENT_NAME}-client-cert.pem" \
        -days "$DAYS" \
        -sha256 \
        -extfile "$client_ext" >/dev/null 2>&1
}

db_ssl_write_monitor_examples() {
    cat >"$EXAMPLES_DIR/monitor-db-ssl.py" <<EOF
DB_SSL = [
    {
        "ca": "${MONITOR_DIR}/db-ca.pem",
        "cert": "${MONITOR_DIR}/db-client-cert.pem",
        "key": "${MONITOR_DIR}/db-client-key.pem",
    },
]
EOF

    cat >"$EXAMPLES_DIR/scp-to-monitor.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail

scp "${CA_DIR}/ca-cert.pem" "${MONITOR_USER}@${MONITOR_HOST}:${MONITOR_DIR}/db-ca.pem"
scp "${CLIENT_DIR}/${CLIENT_NAME}-client-cert.pem" "${MONITOR_USER}@${MONITOR_HOST}:${MONITOR_DIR}/db-client-cert.pem"
scp "${CLIENT_DIR}/${CLIENT_NAME}-client-key.pem" "${MONITOR_USER}@${MONITOR_HOST}:${MONITOR_DIR}/db-client-key.pem"
EOF
    chmod +x "$EXAMPLES_DIR/scp-to-monitor.sh"
}

db_ssl_print_summary() {
    cat <<EOF
Created DB SSL material under: $OUTDIR

Server files:
  CA cert:     $CA_DIR/ca-cert.pem
  CA key:      $CA_DIR/ca-key.pem
  Server cert: $SERVER_DIR/server-cert.pem
  Server key:  $SERVER_DIR/server-key.pem
  Client cert: $CLIENT_DIR/${CLIENT_NAME}-client-cert.pem
  Client key:  $CLIENT_DIR/${CLIENT_NAME}-client-key.pem

Monitor-side examples:
  DB_SSL block: $EXAMPLES_DIR/monitor-db-ssl.py
  scp helper:   $EXAMPLES_DIR/scp-to-monitor.sh
EOF
}
