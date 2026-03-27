# Manual Deployment

This document covers manual installation of `mumble-bg` as a standalone service.

## 1. Create the working directory and venv

```bash
mkdir -p ~/mumble-bg
cd ~/mumble-bg
python3 -m venv .venv/mumble-bg
source .venv/mumble-bg/bin/activate
pip install --upgrade pip
pip install mumble_bg-<version>-py3-none-any.whl
export DJANGO_SETTINGS_MODULE=bg.settings
```

## 2. Create and load the BG env file

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
  - When ICE uses TLS, follow `docs/securing-ice-protocol.md` to place cert/key files and `BG_ICE_KEY_PASSPHRASE`.

Common optional variables:

- `MURMUR_PROBE`
- `BG_BIND`
- `MURMUR_CONTROL_URL`
- `BG_KEY_DIR`

Required when the BG private key is encrypted:

- `BG_PKI_PASSPHRASE`

JSON env values SHALL remain both valid JSON and shell-parseable. If a literal apostrophe must appear inside a JSON string, encode it as `\\u0027`.

## 3. Preflight the install

```bash
python -m django check
python -m django install_assistant
```

`install_assistant` verifies:

- BG DB connectivity
- ICE reachability
- control secret presence
- crypto/key readiness

## 4. Generate BG keys

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

## 5. Migrate and run BG

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

## 6. Verify the runtime

```bash
curl -s http://127.0.0.1:18080/v1/health | python3 -m json.tool
curl -s http://127.0.0.1:18080/v1/public-key
python -m django list_ice_users
```

Useful operator commands:

```bash
python -m django install_assistant --json
python -m django sync_ice_inventory --show-current
python -m django provision_registrations
```

### Server identity between BG and FG

FG now links Murmur inventory views by BG-owned `server_key`, not by the raw
`MumbleServer.id` primary key. BG derives `server_key` from the active server
inventory contract, and FG stores inventory snapshots keyed by that stable value.

Operator checks after changing `ICE`:

1. Rebuild the BG inventory rows:

   ```bash
   python -m django sync_ice_inventory --show-current
   ```

2. Verify the active rows and their current stable keys:

   ```bash
   python -m django shell -c "from bg.state.models import MumbleServer; print([{'id': row.id, 'server_key': row.server_key, 'name': row.name, 'address': row.address, 'is_active': row.is_active} for row in MumbleServer.objects.order_by('display_order', 'name')])"
   ```

3. In FG, use the live server selector values from BG. Old bookmarked
   `?server=<numeric-id>` query strings are stale and should be discarded.

If BG logs `Server not found` for `/v1/servers/<server_key>/inventory`, repair in this order:

1. Confirm the `ICE` env is correct.
2. Re-run `sync_ice_inventory --show-current`.
3. Confirm an active `MumbleServer` row exists with the expected `server_key`.
4. Refresh FG inventory from BG so FG replaces any stale cached snapshot for that server key.

## 7. Optional systemd units

Generate unit files from the active installation:

```bash
python -m django print_systemd_bg_control --env-file ~/.env/mumble-bg > /tmp/bg-control.service
python -m django print_systemd_bg_authd --env-file ~/.env/mumble-bg > /tmp/bg-authd.service
```

Install them:

```bash
sudo install -m 0644 /tmp/bg-control.service /etc/systemd/system/bg-control.service
sudo install -m 0644 /tmp/bg-authd.service /etc/systemd/system/bg-authd.service
sudo systemctl daemon-reload
sudo systemctl enable --now bg-control bg-authd
```

## 8. Relationship to FG

FG manual deployment comes later.

The shared values FG must match are:

- BG control URL
- `BG_PSK`
- BG public key path, when FG encrypts password traffic with a BG public key file

BG does not require direct `PILOT_DBMS` access.
