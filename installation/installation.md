# FG + BG Installation Plan

This is the recommended sequence for installing `mumble-fg` (in Cube) and `mumble-bg` (standalone).

## 1. Create BG working directory + venv, activate, and install wheel

From the BG host:

```bash
mkdir -p ~/mumble-bg
cd ~/mumble-bg
python3 -m venv .venv/mumble-bg
source .venv/mumble-bg/bin/activate
pip install --upgrade pip
pip install --upgrade --force-reinstall mumble_bg-<version>-py3-none-any.whl
```

Immediately set settings-module so you do not need `--settings=bg.settings` on every command:

```bash
export DJANGO_SETTINGS_MODULE=bg.settings
```

## 2. Create and load BG env file (first-time recommended)

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

Env formatting rule for JSON variables (`DATABASES`, `ICE`, `MURMUR_PROBE`): keep them valid JSON and shell-parseable. If a JSON string value must include a literal apostrophe, encode it as `\\u0027` inside JSON. Example: `"'MyPrettyS3rcet'"` must be represented as `"\\u0027MyPrettyS3rcet\\u0027"`. This avoids shell quote parsing issues in `.env`.

## 3. Run BG preflight checks

```bash
python -m django check
python -m django install_assistant
python -m django showmigrations state
```

Required env at this stage includes your DB/ICE/control settings.  
For first-time installs that will use encrypted BG keys, set:

```bash
export BG_KEY_PASSPHRASE='<passphrase>'
```

On first install, `install_assistant` is expected to show `Encryption` as inactive/partial until keys are generated.

## 4. Apply BG migrations

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

`generate_bg_keypair` behavior:
- If `BG_KEY_PASSPHRASE` is set and non-empty, an encrypted private key is generated.
- If `BG_KEY_PASSPHRASE` is missing/empty, command prompts: `Generate passwordless keypair? [y/N]`.
- `N` aborts key generation. `y` creates a passwordless private key.

After key generation, re-run:

```bash
python -m django install_assistant
```

`Encryption` should now report active.

If the private key is encrypted (recommended), `BG_KEY_PASSPHRASE` must be set for:
- `python -m django check`
- `python -m django install_assistant`
- `python -m django runserver ...`
- runtime control operations requiring decryption

## 6. Start BG services before FG install

```bash
python -m django runserver 127.0.0.1:18080
python -m bg.authd
```

To keep `authd` running while continuing in the same shell, use:

```bash
# press Ctrl-Z while authd is in foreground
bg
```

## 7. Verify BG runtime and ICE visibility

```bash
curl -s http://127.0.0.1:18080/v1/health | python -m json.tool
curl -s http://127.0.0.1:18080/v1/public-key
python -m django list_ice_users
```

Health output should report crypto readiness when configured:
- `has_public_key=true`
- `can_decrypt=true` (when passphrase/private key are loaded)

## 8. Install or upgrade FG wheel in Cube venv

From the Cube host:

```bash
pip install --upgrade --force-reinstall mumble_fg-<version>-py3-none-any.whl
```

## 9. Validate FG control env vars in Cube shell

```bash
env | rg '^OPTIONAL_APPS='
env | rg '^MURMUR_CONTROL_URL='
env | rg '^MURMUR_CONTROL_PSK='
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
- Source-checkout helpers still exist under `installation/scripts/` for operators who prefer wrapper scripts, but they are optional.
