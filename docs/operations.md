# mumble-bg Operations

Verified: `mumble-bg` `main` version `0.3.7.dev1` on `2026-04-24`.

## Scope

This document covers:

- manual installation of BG as a standalone service
- current GitHub Actions deployment behavior
- local BG and Murmur test harnesses
- smoke checks and restoreability probes
- IceSSL/TLS guidance for ICE endpoints

## Manual Installation

### Create the working directory and venv

```bash
mkdir -p ~/mumble-bg
cd ~/mumble-bg
python3 -m venv .venv/mumble-bg
source .venv/mumble-bg/bin/activate
pip install --upgrade pip
pip install mumble_bg-<version>-py3-none-any.whl
export DJANGO_SETTINGS_MODULE=bg.settings
```

### Create and load the BG env file

Preferred operator env file:

- `~/.env/mumble-bg`

Generate a template:

```bash
python -m django init_bg_env
```

Load it:

```bash
set -a
source ~/.env/mumble-bg
set +a
```

Minimum variables:

- `BG_DBMS`
- `ICE`
- `BG_PSK`

Common optional variables:

- `MURMUR_PROBE`
- `BG_BIND`
- `MURMUR_CONTROL_URL`
- `BG_KEY_DIR`
- `BG_PKI_PASSPHRASE`

JSON env values should remain both valid JSON and shell-parseable.

### Preflight the install

```bash
python -m django check
python -m django install_assistant
```

`install_assistant` verifies:

- BG DB connectivity
- control secret presence
- crypto/key readiness
- schema readiness
- ICE reachability
- authd registration ability

### Generate BG keys

If encryption is not ready, create the key directory and keypair:

```bash
sudo mkdir -p /etc/mumble-bg/keys
sudo chown -R "$USER":"$USER" /etc/mumble-bg
sudo chmod 700 /etc/mumble-bg /etc/mumble-bg/keys
export BG_PKI_PASSPHRASE='<passphrase>'
python -m django generate_bg_keypair --key-dir /etc/mumble-bg/keys
python -m django install_assistant
```

If the generated private key is encrypted, `BG_PKI_PASSPHRASE` must remain available in the runtime env file before `bg.control_main`, `bg.authd`, or `install_assistant` are started.

### Migrate and run BG

```bash
python -m django showmigrations state
python -m django migrate
BG_ENV_FILE=~/.env/mumble-bg python -I -m bg.control_main
```

In another shell:

```bash
source .venv/mumble-bg/bin/activate
export DJANGO_SETTINGS_MODULE=bg.settings
set -a
source ~/.env/mumble-bg
set +a
BG_ENV_FILE=~/.env/mumble-bg python -I -m bg.authd
```

### Verify the runtime

```bash
curl -s http://127.0.0.1:18080/v1/health | python3 -m json.tool
curl -s http://127.0.0.1:18080/v1/public-key
python -m django list_ice_users
python -m django install_assistant --json
python -m django sync_ice_inventory --show-current
python -m django provision_registrations
```

## Workflow Deployment

Current workflow files:

- `.github/workflows/deploy-dev.yml`
- `.github/workflows/deploy-dev-us.yml`
- `.github/workflows/deploy-prod.yml`
- `.github/workflows/deploy.yml`

The workflows are code-sync oriented. They do not replace one-time host setup.

### Dev workflow

Required secrets:

- `TARGETHOST`
- `TARGETUSER`
- `BG_DBMS`
- `ICE`
- `BG_PSK`

Common optional values:

- `MURMUR_PROBE`
- `BG_PKI_PASSPHRASE`

The dev workflow currently:

- resolves `TARGETHOST` and `TARGETUSER`
- rsyncs code
- writes the target env file
- creates the venv if needed
- installs requirements
- bootstraps a local BG database when the target is local
- runs `python manage.py migrate --noinput` automatically
- restarts configured service units

### Dev US workflow

The US-East dev workflow is the same basic flow with `TARGETHOST_US_DEV` and `TARGETUSER_US_DEV`, plus matching US secret names for BG DB, ICE, PSK, and passphrase values.

### Prod workflow

Current prod defaults:

- target secret: `MUMBLE_PROD_US`
- env secret: `MUMBLE_PROD_US_ENV`

Prod workflow currently:

- rsyncs code
- writes the target env file from the env JSON secret
- bootstraps system packages, venv, and systemd units on first deploy
- installs requirements
- runs `python manage.py migrate --noinput` automatically
- restarts the configured service

### Reusable workflow

`.github/workflows/deploy.yml` is the reusable workflow form.

It performs the shared deploy steps and is consumed by other workflow entrypoints.

### Bootstrap notes

- PostgreSQL is the default bootstrap engine.
- set `BG_ENGINE=mysql` only when the target truly needs MySQL or MariaDB
- `BG_RESET_DB_ON_DEPLOY` is a disposable local reset hook; it belongs only in a target env file for test runs, not in normal workflow secrets

## Local Murmur Harness

`python -m django start_local_murmur`

This harness:

- starts a private local `mumble-server` instance backed by SQLite
- writes matching `MumbleServer` rows
- alternates SSL and TCP ICE endpoints by instance number
- creates local TLS material when SSL is used

Related checks:

- `python -m django sync_ice_inventory`
- `python -m django list_ice_users`
- `python -m django probe_murmur_sqlite --sqlite-path <path>`
- `python -m django verify_auth_fallback`

## ICE TLS / IceSSL

BG supports TLS for Murmur ICE endpoints when the target server is configured for IceSSL.

Key requirements:

- generate or reuse a certificate/private key bundle under `/etc/mumble-bg/keys`
- ensure the CA certificate that signed the client cert is available on each ICE host
- store the private key with `chmod 600`
- if encrypted, keep the passphrase available in BG env as configured by the deployment
- put `Ice.Plugin.IceSSL=IceSSL:createIceSSL` and related `IceSSL.*` settings in the `[Ice]` section of `mumble-server.ini`

Useful verification:

```bash
strings /usr/bin/mumble-server | grep -i IceSSL | head
ldd /usr/bin/mumble-server | grep -i ice
```

If `ssl` endpoints fail to bind, confirm the IceSSL plugin is present in the `[Ice]` section and that the Murmur binary actually has the IceSSL library.

## Server Identity Repairs

BG links Murmur inventory views by `server_key`, not by the raw `MumbleServer.id` primary key.

After changing `ICE`:

1. Rebuild the inventory rows:

```bash
python -m django sync_ice_inventory --show-current
```

2. Verify the active rows and their stable keys:

```bash
python -m django shell -c "from bg.state.models import MumbleServer; print([{'id': row.id, 'server_key': row.server_key, 'name': row.name, 'address': row.address, 'is_active': row.is_active} for row in MumbleServer.objects.order_by('display_order', 'name')])"
```

3. If BG logs `Server not found` for `/v1/servers/<server_key>/inventory`, confirm the `ICE` env is correct and refresh FG inventory from BG after the BG rows are rebuilt.

## `PILOT_DBMS` Restoreability Probe

Use this to answer one narrow question:

- can a captured pilot-data backup be restored cleanly into a disposable probe DB?

### Local non-destructive restore probe

Replace the placeholders for your environment:

```bash
export PGPASSWORD='<db_password>'
BACKUP_FILE='/path/to/pilot_dump.sql.gz'
PROBE_DB="pilot_dbms_restore_probe_$(date +%Y%m%d_%H%M%S)"

createdb -h 127.0.0.1 -U <db_user> "$PROBE_DB"

gzip -dc "$BACKUP_FILE" | psql -h 127.0.0.1 -U <db_user> -d "$PROBE_DB"

psql -h 127.0.0.1 -U <db_user> -d "$PROBE_DB" -c '\dt'
dropdb -h 127.0.0.1 -U <db_user> "$PROBE_DB"
```

Check:

- backup stream decompresses cleanly
- `psql` import completes without schema/object errors
- expected tables exist in the probe DB
- the probe DB can be dropped cleanly afterward

## Practical Testing Order

Recommended progression:

1. `init_bg_env`
2. `install_assistant`
3. `generate_bg_keypair`
4. `sync_ice_inventory`
5. `start_local_murmur` or real ICE-backed Murmur
6. `list_ice_users`
7. feed BG with FG data
8. `provision_registrations --apply`
9. `list_acl_to_ice`
10. end-to-end UI checks from the host emulator used for integration testing
