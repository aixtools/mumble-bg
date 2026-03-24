# Deploy Workflow

This document describes the current github deployment workflow for `mumble-bg`.
It covers:

- one-time host bootstrap
- ordinary code updates through GitHub Actions
- the runtime/deploy secret contract used by the current branch

For manual (ie, not using workflow actions) full FG + BG bring-up, control-service verification, and key-generation steps,
see `installation/installation.md`.

## Current Split

There are two different directories `./deploy` and `./.gitbub/workflows`. They focus on different problems:

- `.github/workflows/deploy-dev.yml` - This file directs the workflow action from github - to push the repo to a destination.
- `deploy/setup-root.sh` is the one-time root bootstrap path. If the user credentials are root the workflow can execute it.
If not root, then this will need to run ONCE by the root user, or using sudo.
- `deploy/unsetup-root.sh` removes the auth-service bootstrap artifacts if you need a clean reinstall. Basically, undoes the steps performed by `setup-root.sh`

## Default Layout

Current standalone defaults are:

- repo checkout: `~${WorkflowUser}/mumble-bg`
- virtualenv: `~${WorkflowUser}/.venv/mumble-bg`
- environment file: `~${WorkflowUser}/.env/mumble-bg`
- systemctl managed services: `bg-control` and `bg-authd`

## Preparing GitHub Secrets

Set secrets before running either workflow.

### BG Secrets

Required in the `mumble-bg` repo:

- `TARGETHOST:<hostname>`
  - Hostname string for the deploy target.
- `TARGETUSER`
  - JSON with SSH user/key and target paths (`user`, `key`; optional `home_dir`, `project_dir`, `env_file`, `venv_dir`, `service_name`).
- `BG_DBMS`
  - BG database JSON object.
- `ICE`
  - ICE inventory JSON list.
- `BG_PSK`
  - FG/BG control shared secret.

Common optional secrets/vars used by BG deploy:

- `MURMUR_PROBE`
- `BG_ENGINE`
- `BG_RESET_DB_ON_DEPLOY` (repo variable or secret)

Templates:

`TARGETHOST:<hostname>`

```text
bg-dev.example.net
```

`TARGETUSER`

```json
{
  "user": "cube",
  "key": "-----BEGIN OPENSSH PRIVATE KEY-----\\n...\\n-----END OPENSSH PRIVATE KEY-----",
  "home_dir": "~${WorkflowUser}",
  "project_dir": "~${WorkflowUser}/mumble-bg",
  "env_file": "~${WorkflowUser}/.env/mumble-bg",
  "venv_dir": "~${WorkflowUser}/.venv/mumble-bg",
  "service_name": "bg-authd"
}
```

`BG_DBMS`

```json
{
  "name": "authd bg",
  "host": "127.0.0.1",
  "username": "bg_username",
  "database": "bg_database",
  "password": "bg_secretPassword"
}
```

`ICE`

```json
[
  {
    "icehost": "127.0.0.1",
    "address": "voice-dev.example.net:64738",
    "name": "Country 1",
    "virtual_server_id": 1,
    "icewrite": "write-secret",
    "iceport": 6502,
    "iceread": "read-secret"
  }
]
```

`BG_PSK`

```text
your-shared-control-secret
```

### FG Secrets

Required in the `mumble-fg` repo:

- `TARGETHOST:<hostname>`
  - Same hostname value used for BG target.
- `TARGETUSER`
  - JSON with SSH user/key and FG target paths (`user`, `key`; optional `home_dir`, `project_dir`, `env_file`, `service_units`).
- `BG_PSK`
  - Same exact value as BG `BG_PSK`.

Templates:

`TARGETHOST:<hostname>`

```text
bg-dev.example.net
```

`TARGETUSER`

```json
{
  "user": "cube",
  "key": "-----BEGIN OPENSSH PRIVATE KEY-----\\n...\\n-----END OPENSSH PRIVATE KEY-----",
  "home_dir": "~${WorkflowUser}",
  "project_dir": "~${WorkflowUser}/mumble-fg",
  "env_file": "~${WorkflowUser}/Cube/.env",
  "service_units": ["cube-django", "cube-celery", "cube-celery-beat"]
}
```

`BG_PSK`

```text
your-shared-control-secret
```

## What The GitHub Workflow Does

The workflow in `.github/workflows/deploy-dev.yml` currently:

- resolves a deploy target from one JSON secret containing `host`, `user`, and `key`
- writes that SSH private key into the runner and records target defaults in `GITHUB_ENV`
- adds the target host to `known_hosts`
- rsyncs this repository to `<project_dir>`
- writes `<env_file>` from GitHub secrets
- creates `<venv_dir>` if missing and installs `requirements.txt`
- bootstraps `BG_DBMS` through `deploy/create-db.sh` when the BG DB host is local (`127.0.0.1` or `localhost`)
- optionally resets the local PostgreSQL BG database before migrate when `BG_RESET_DB_ON_DEPLOY` is enabled
- strips a `:reset` suffix from `BG_PSK`, writes the stripped value back to `<env_file>`, and runs `manage.py reset_murmur_control_key --yes`
- runs `manage.py migrate --noinput`
- restarts one configured systemd service, defaulting to `mumble-bg-auth`
- verifies the restarted service with `systemctl is-active`

## What The Workflow Does Not Do

The current workflow does not:

- create the deploy user
- install the target SSH public key into `authorized_keys`
- install Murmur or a database server package
- install or manage the `mumble-bg-control` systemd unit
- generate BG encryption keys or export the BG public key to FG
- deploy or configure `mumble-fg`
- trigger FG-to-BG ACL sync or pilot-snapshot sync after deploy

- `.github/workflows/deploy-dev.yml` - This file directs the workflow action from github - to push the repo to a destination.
- `deploy/setup-root.sh` is the one-time root bootstrap path. If the user credentials are root the workflow can execute it.
If not root, then this will need to run ONCE by the root user, or using sudo.
- `deploy/unsetup-root.sh` removes the auth-service bootstrap artifacts if you need a clean reinstall. Basically, undoes the steps performed by `setup-root.sh`

## Default Layout for BG

Note: BG may operate on a different TARGETDEST than FG

Current defaults for bg environment are:

- repo checkout: `~${WorkflowUser}/mumble-bg`
- virtualenv: `~${WorkflowUser}/.venv/mumble-bg`
- environment file: `~${WorkflowUser}/.env/mumble-bg`
- systemctl managed services: `bg-control` and `bg-authd`

Defaults for fg environment are owned by the application (e.g., cube)
: 
## Preparing GitHub Secrets

Set secrets before running either workflow.
Use single-value secret notation in documentation as `NAME = value`.

### BG Secrets

Required in the `mumble-bg` repo:

- `TARGETHOST`
  - Hostname string for the deploy target.
- `TARGETUSER`
  - JSON with SSH user/key and target paths (`user`, `key`; optional `home_dir`, `project_dir`, `env_file`, `venv_dir`, `service_name`).
- `BG_DBMS`
  - BG database JSON object.
- `ICE`
  - ICE inventory JSON list.
- `BG_PSK`
  - FG/BG control shared secret.

Common optional secrets/vars used by BG deploy:

- `MURMUR_PROBE`
- `BG_RESET_DB_ON_DEPLOY` (repo variable or secret)

Templates:

`TARGETHOST`

```text
bg-dev.example.net
```

`TARGETUSER`

```json
{
  "user": "${WorkflowUser}",
  "key": "-----BEGIN OPENSSH PRIVATE KEY-----\\n...\\n-----END OPENSSH PRIVATE KEY-----",
  "home_dir": "~${WorkflowUser}",
  "project_dir": "~${WorkflowUser}/mumble-bg",
  "env_file": "~${WorkflowUser}/.env/mumble-bg",
  "venv_dir": "~${WorkflowUser}/.venv/mumble-bg",
  "service_name": "bg-authd"
}
```

`BG_DBMS`

```json
{
  "name": "authd bg",
  "host": "127.0.0.1",
  "username": "bg_username",
  "database": "bg_database",
  "password": "bg_secretPassword"
}
```

`ICE`

```json
[
  {
    "icehost": "127.0.0.1",
    "address": "voice-dev.example.net:64738",
    "name": "Country 1",
    "virtual_server_id": 1,
    "icewrite": "write-secret",
    "iceport": 6502,
    "iceread": "read-secret"
  }
]
```

`BG_PSK`

```text
your-shared-control-secret
```

### FG Secrets

Required in the `mumble-fg` repo:

- `TARGETHOST`
  - Same hostname value used for BG target.
- `TARGETUSER`
  - JSON with SSH user/key and FG target paths (`user`, `key`; optional `home_dir`, `project_dir`, `env_file`, `service_units`).
- `BG_PSK`
  - Same exact value as BG `BG_PSK`.

Templates:

`TARGETHOST`

```text
bg-dev.example.net
```

`TARGETUSER`

```json
{
  "user": "${WorkflowUser}",
  "key": "-----BEGIN OPENSSH PRIVATE KEY-----\\n...\\n-----END OPENSSH PRIVATE KEY-----",
  "home_dir": "~${WorkflowUser}",
  "project_dir": "~${WorkflowUser}/mumble-fg",
  "env_file": "~${WorkflowUser}/Cube/.env",
  "service_units": ["cube-django"]
}
```

Service-units note:

- `service_units` assumes the main host application is already configured under the same `TARGETUSER` credentials.
- `TARGETUSER` must be allowed to run `sudo systemctl restart ...` for listed units.
- In this example, only `cube-django` is required.

`BG_PSK`

```text
your-shared-control-secret
```

## Branch-Specific Runtime Contract

On this branch, BG no longer reads pilot data directly from a pilot/host database.
FG pushes the pilot snapshot to BG over the control API, and BG stores that snapshot
in BG-owned tables before reconcile/provision.

That means the deploy-time database concept is now `BG_DBMS`. The workflow
reads that config from the `BG_DBMS` secret/env value. Legacy `DATABASES`
values are still accepted as a compatibility fallback.

Minimal shape:

```json
{
  "name": "authd bg",
  "host": "127.0.0.1",
  "username": "bg_username",
  "database": "bg_database",
  "password": "bg_secretPassword"
}
```

Required `BG_DBMS` fields:

- `host`
- `username`
- `database`
- `password`

Optional `BG_DBMS` fields:

- `name`

## One-Time Server Bootstrap

Run these steps once on the target host before relying on GitHub Actions updates.

### 1. Put the repo on the target host

`deploy/setup-root.sh` expects a repo checkout at `<project_dir>`.
Use a normal clone or copy the repository there by some other operator-controlled means.

Example:

```bash
sudo -u <deploy_user> git clone https://github.com/aixtools/mumble-bg.git <project_dir>
```

If the checkout already exists:

```bash
sudo -u <deploy_user> git -C <project_dir> fetch origin
sudo -u <deploy_user> git -C <project_dir> switch main
sudo -u <deploy_user> git -C <project_dir> pull --ff-only origin main
```

### 2. Create the BG environment file

Create the parent directory and env file expected by the bootstrap script:

```bash
install -d -m 0755 /home/<deploy_user>/.env
install -m 0600 /dev/null <env_file>
```

At minimum, define:

- `BG_DBMS`
- `ICE`

Optional deploy/runtime values:

- `MURMUR_PROBE`
- `BG_RESET_DB_ON_DEPLOY`
- `BG_PSK`
- `BG_KEY_PASSPHRASE`
- `BG_ENGINE` (optional runtime override only; default bootstrap engine is PostgreSQL, set `BG_ENGINE=mysql` only when needed)

If you want the guided first-time env workflow and key-generation checks, use
`installation/installation.md` and `python -m django init_bg_env` instead of
building the file entirely by hand.

### 3. Run the one-time root bootstrap

```bash
APP_USER=<deploy_user> \
APP_HOME=/home/<deploy_user> \
APP_DIR=<project_dir> \
VENV_DIR=<venv_dir> \
ENV_FILE=<env_file> \
bash <project_dir>/deploy/setup-root.sh
```

This script currently:

- ensures `python3` and `python3-venv` are installed
- installs a PostgreSQL DB client by default (override with `BG_ENGINE=mysql` only when needed)
- creates `<venv_dir>` if missing
- bootstraps a local BG database when the current `BG_DBMS` host is local
- installs Python requirements
- runs `manage.py migrate --noinput`
- installs `/etc/sudoers.d/mumble-bg`
- installs and enables `/etc/systemd/system/mumble-bg-auth.service`
- restarts `mumble-bg-auth`

### 4. Verify the installed service

```bash
systemctl status mumble-bg-auth
journalctl -u mumble-bg-auth -n 50 --no-pager
```

If you also want BG-side readiness checks from the app itself:

```bash
set -a
source <env_file>
set +a
<venv_dir>/bin/python <project_dir>/manage.py install_assistant
```

### 5. If bootstrap state is stale, reset and re-run

```bash
APP_USER=<deploy_user> \
APP_HOME=/home/<deploy_user> \
APP_DIR=<project_dir> \
VENV_DIR=<venv_dir> \
ENV_FILE=<env_file> \
bash <project_dir>/deploy/unsetup-root.sh

APP_USER=<deploy_user> \
APP_HOME=/home/<deploy_user> \
APP_DIR=<project_dir> \
VENV_DIR=<venv_dir> \
ENV_FILE=<env_file> \
bash <project_dir>/deploy/setup-root.sh
```

`deploy/unsetup-root.sh` removes:

- the `mumble-bg-auth` systemd unit
- the matching sudoers file
- `<venv_dir>`

It intentionally keeps:

- the repo checkout
- `<env_file>`

## Control Service And Key Material

The auth-only bootstrap above is narrower than the full install guide.

If you need:

- `mumble-bg-control`
- `/v1/public-key`
- encrypted password transit from FG to BG

then you still need the key-generation and control-service steps from
`installation/installation.md`.

Useful helpers already present in this repo:

- `deploy/generate-keypair.sh`
- `deploy/export-public-key.sh`
- `deploy/systemd/mumble-bg-control.service`

The current GitHub workflow restarts only one service. By default that is
`mumble-bg-auth`. If you deploy a control service separately, account for that
explicitly; the current workflow does not restart both services for you.

## GitHub Actions Configuration

Required deploy configuration:

- deploy target JSON secret, identified by a host-user label, default label `CUBE_DEV_CUBE`
- `BG_DBMS`
- `ICE`

Optional deploy/runtime configuration:

- `MURMUR_PROBE`
- `BG_RESET_DB_ON_DEPLOY`
- `BG_PSK`
- `BG_ENGINE` (optional runtime override only; default bootstrap engine is PostgreSQL)

### Deploy Target Host-User Label

The deploy target is selected by a host-user label. The default label is
`CUBE_DEV_CUBE`, which is a GitHub-secret-safe host-user label.

Default target secret example:

```json
{
  "host": "<deploy_host>",
  "user": "<deploy_user>",
  "key": "-----BEGIN OPENSSH PRIVATE KEY-----\\n...\\n-----END OPENSSH PRIVATE KEY-----",
  "home_dir": "/home/<deploy_user>",
  "project_dir": "/home/<deploy_user>/mumble-bg",
  "env_file": "/home/<deploy_user>/.env/mumble-bg",
  "venv_dir": "/home/<deploy_user>/.venv/mumble-bg",
  "service_name": "mumble-bg-auth"
}
```

Required target fields:

- `host`
- `user`
- `key`

Optional target fields:

- `home_dir`
- `project_dir`
- `env_file`
- `venv_dir`
- `service_name`

Defaults:

- `home_dir`: `/home/<user>`
- `project_dir`: `<home_dir>/mumble-bg`
- `env_file`: `<home_dir>/.env/mumble-bg`
- `venv_dir`: `<home_dir>/.venv/mumble-bg`
- `service_name`: `mumble-bg-auth`

### ICE Secret Shape

`ICE` is a JSON list. Each server entry currently uses this shape:

```json
[
  {
    "icehost": "localhost",
    "address": "voice.yourhost.tld:64738",
    "name": "Mumble Server Name in Dialogs",
    "virtual_server_id": 1,
    "icewrite": "bg_iceWriteSecret",
    "iceport": 6502,
    "iceread": "bg_iceReadSecret"
  }
]
```

Required per server:

- `icehost`
- `address`
- `virtual_server_id`
- `icewrite`

Optional per server:

- `name`
- `iceport`
- `iceread`

### Murmur Probe Secret Shape

`MURMUR_PROBE` is optional and debug-only. Each probe entry uses this shape:

```json
[
  {
    "name": "optional label",
    "host": "127.0.0.1",
    "username": "mumble",
    "database": "mumble_db",
    "password": "secret",
    "dbport": 5432,
    "dbengine": "postgres"
  }
]
```

Required per probe target:

- `host`
- `username`
- `database`
- `password`

Optional per probe target:

- `name`
- `dbport`
- `dbengine`

### `BG_PSK` Notes

- when set, the workflow writes it into `<env_file>`
- if the value ends with `:reset`, deploy strips the suffix for runtime and runs `manage.py reset_murmur_control_key --yes`
- this supports a one-shot control-key reset during deploy without leaving the suffix in runtime config
- GitHub secret and runtime env variable should both use `BG_PSK`

## After Bootstrap

Once one-time bootstrap exists:

- push updates to the tracked branch
- GitHub Actions refreshes `<project_dir>`
- the workflow rewrites `<env_file>` from secrets
- dependencies in `<venv_dir>` are updated
- database migrations are applied
- the configured service is restarted and checked

Operator follow-up after deploy is still separate:

- verify service health and logs
- if needed, verify FG can reach BG control
- run FG-side sync so ACL rules and the pilot snapshot are present before reconcile
