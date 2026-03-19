# FG + BG Installation Plan

This is the recommended sequence for installing `mumble-fg` (in Cube) and `mumble-bg` (standalone).

## 1. Install or upgrade BG wheel in BG venv

From the BG host:

```bash
pip install --upgrade --force-reinstall mumble_bg-<version>-py3-none-any.whl
```

## 2. Create and load BG env file (first-time recommended)

From BG repo root:

```bash
python -m django init_bg_env
```

Edit `~/.env/mumble-bg`, then load it:

```bash
set -a
source ~/.env/mumble-bg
set +a
```

Default command pattern after loading env:

```bash
python -m django <command>
```

Fallback one-off pattern (if env is not loaded):

```bash
python -m django <command> --settings=bg.settings
```

For values with difficult shell characters, generate safe export lines with:

```bash
python -m django shell_export ICE_SECRET "'CubeiNive'"
```

Then paste the output into your env file.

To scan a completed env file and propose shell-safe rewrites for tricky values:

```bash
python -m django scan_env_values --file ~/.env/mumble-bg
```

## 3. Run BG preflight checks

From BG repo root:

```bash
bash installation/scripts/bg_preflight.sh
```

This runs:
- `python -m django check`
- `python -m django install_assistant`
- `python -m django showmigrations state`

Required env at this stage includes your DB/ICE/control settings.  
For first-time installs that will use encrypted BG keys, set:

```bash
export BG_KEY_PASSPHRASE='<passphrase>'
```

## 4. Apply BG migrations

From BG repo root:

```bash
python -m django migrate
```

## 5. First-time key generation (required before FG encrypted password flow)

Create key directory (one-time):

```bash
sudo mkdir -p /etc/mumble-bg/keys
sudo chown -R "$USER":"$USER" /etc/mumble-bg
sudo chmod 700 /etc/mumble-bg /etc/mumble-bg/keys
```

Generate BG keypair:

```bash
python -m django generate_bg_keypair --key-dir /etc/mumble-bg/keys
```

If the private key is encrypted (recommended), `BG_KEY_PASSPHRASE` must be set for:
- `python -m django check`
- `python -m django install_assistant`
- `python -m django runserver ...`
- runtime control operations requiring decryption

## 6. Start BG HTTP control runtime

```bash
python -m django runserver 127.0.0.1:18080
```

## 7. Verify BG runtime and ICE visibility

From BG repo root:

```bash
bash installation/scripts/bg_runtime_verify.sh
```

This checks:
- `GET /v1/health`
- `GET /v1/public-key`
- `python -m django list_ice_users`

Health output should report crypto readiness when configured:
- `has_public_key=true`
- `can_decrypt=true` (when passphrase/private key are loaded)

## 8. Install or upgrade FG wheel in Cube venv

From the Cube host:

```bash
pip install --upgrade --force-reinstall mumble_fg-<version>-py3-none-any.whl
```

## 9. Validate FG control env vars in Cube shell

From Cube repo root:

```bash
bash ../mumble-bg/installation/scripts/fg_env_check.sh
```

Required runtime env:
- `OPTIONAL_APPS` includes `mumble_ui.apps.MumbleUiConfig`
- `MURMUR_CONTROL_URL` points to BG control endpoint
- `MURMUR_CONTROL_PSK` matches BG control secret

## 10. Apply FG migration and restart Cube

```bash
python manage.py migrate mumble_fg
python manage.py collectstatic
```

Restart Cube runtime (service or runserver for your environment).

## 11. First control sync from FG

From FG ACL UI, run `Sync BG`.

Expected behavior:
- ACL table sync
- eligibility provisioning
- Murmur reconcile

Even if ACL rules are unchanged, provisioning/reconcile can still run.

## 12. Validate end state

Check three surfaces:
- FG UI (`/mumble-ui/acl/`, `/profile/`)
- BG state via API/management commands
- Murmur via ICE user listing (`list_ice_users`)

## Notes

- `python -m django help <command>` only confirms registration; it does not execute the command.
- Update-only note: if `pip install` runs while a dev `runserver` is active, autoreload can produce transient command errors. Stop services first during updates, then restart cleanly after install.
