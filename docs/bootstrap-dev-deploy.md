# Bootstrap Dev Deploy

This document covers the initial one-time setup for deploying `mumble-bg` from GitHub Actions to the dev host.

This is for the current standalone background-service phase only.

## What The Workflow Does

The workflow in `.github/workflows/deploy-dev.yml`:

- rsyncs this repository to `<project_dir>`
- writes `<env_file>`
- bootstraps `DATABASES.bg` via `deploy/create-db.sh` when the bg DB host is local
- installs Python requirements into `<venv_dir>`
- runs `manage.py migrate`
- restarts `mumble-bg-auth`

It does **not** perform the first-time systemd/bootstrap install. That is what `deploy/setup-hetzner.sh` is for.

## Assumptions

- the target machine already has the `<deploy_user>` user
- Murmur / `mumble-server` is already installed and running
- PostgreSQL is already installed and reachable
- this repo is deployed as `<project_dir>`

## One-Time Server Setup

Run these steps on the target host once.

1. Check out the repository using HTTPS credentials available to `gh`:

```bash
sudo -u <deploy_user> gh auth login --hostname github.com --git-protocol https
```

Then:

```bash
sudo -u <deploy_user> gh repo clone aixtools/mumble-bg <project_dir>
```

If the checkout already exists:

```bash
sudo -u <deploy_user> git -C <project_dir> fetch origin
sudo -u <deploy_user> git -C <project_dir> switch main
sudo -u <deploy_user> git -C <project_dir> pull --ff-only origin main
```

2. Create the environment file:

```bash
install -d -m 0755 /home/<deploy_user>/.env
install -m 0600 <project_dir>/.env.example <env_file>
```

Edit `<env_file>` with the real database values.

If you need to create a fresh local database/user first, use:

- [docs/database-bootstrap.md](/home/michael/prj/mumble-bg/docs/database-bootstrap.md)
- [deploy/create-db.sh](/home/michael/prj/mumble-bg/deploy/create-db.sh)

3. Run the one-time setup script as root:

```bash
APP_USER=<deploy_user> \
APP_HOME=/home/<deploy_user> \
APP_DIR=<project_dir> \
VENV_DIR=<venv_dir> \
ENV_FILE=<env_file> \
bash <project_dir>/deploy/setup-hetzner.sh
```

This script:

- ensures `<venv_dir>`
- provisions the local `mumble-bg` database/user if needed
- installs background-service requirements
- runs `manage.py migrate` for the `mumble-bg` schema
- installs `/etc/systemd/system/mumble-bg-auth.service`
- installs sudoers for service restart/status and local bg DB bootstrap
- enables and restarts the service

Database bootstrap behavior:

- uses `DATABASES.bg` from `<env_file>`
- uses optional `BG_ENGINE`, defaulting to PostgreSQL when omitted
- only bootstraps local database hosts (`127.0.0.1` or `localhost`)
- does not change the password of an already-existing database user

If the host still has stale auth service state, reset it first:

```bash
APP_USER=<deploy_user> APP_HOME=/home/<deploy_user> APP_DIR=<project_dir> VENV_DIR=<venv_dir> ENV_FILE=<env_file> bash <project_dir>/deploy/undeploy-hetzner.sh
APP_USER=<deploy_user> APP_HOME=/home/<deploy_user> APP_DIR=<project_dir> VENV_DIR=<venv_dir> ENV_FILE=<env_file> bash <project_dir>/deploy/setup-hetzner.sh
```

`deploy/undeploy-hetzner.sh` removes the current `mumble-bg-auth` systemd unit, removes the matching sudoers file, and deletes `<venv_dir>`. It intentionally keeps the repo checkout and `<env_file>`.

4. Verify the service:

```bash
systemctl status mumble-bg-auth
journalctl -u mumble-bg-auth -n 50 --no-pager
```

## GitHub Actions Secrets

See the appendix below for the exact GitHub Actions configuration values to define in `aixtools/mumble-bg`.

## SSH Key Clarification

Deploy target SSH is now provided via one JSON secret keyed by target name
(default: `CUBE_DEV_CUBE`).

That secret is **not** a GitHub deploy key for cloning this repository.

It is the private SSH key + host/user metadata that the GitHub Actions runner
uses to log into the target server.

That means:

- the matching public key must be present in `<home_dir>/.ssh/authorized_keys`
  for the user specified in the target JSON
- if `user` is `<deploy_user>`, the key must authorize SSH as `<deploy_user>`

If you previously stored this key only in `another repository`, that does not automatically make it available to `aixtools/mumble-bg`. GitHub Actions secrets are repo-scoped unless you deliberately use organization secrets.

## After Bootstrap

Once the one-time setup exists:

- push to `main`
- GitHub Actions deploys the new code
- the workflow refreshes `<project_dir>`
- dependencies in `<venv_dir>` are updated
- `mumble-bg-auth` is restarted

## Appendix: GitHub Actions Configuration

Required runtime/deploy:

- deploy target JSON secret (default secret name: `CUBE_DEV_CUBE`)
- optional workflow-dispatch input: `deploy_target_name`

- `DATABASES`

- `ICE`

Optional runtime/debug:

- `MURMUR_PROBE`

Optional provisioning-only:

- `BG_ENGINE`

Recommended `BG_ENGINE` values:

- `psql`
- `mysql`

`DATABASES` is a JSON object with `pilot` and `bg` entries:

```json
{
  "pilot": {
    "name": "pilot",
    "host": "127.0.0.1",
    "username": "pilot_user",
    "database": "pilot_db",
    "password": "change_me"
  },
  "bg": {
    "name": "mumble-bg",
    "host": "127.0.0.1",
    "username": "mumble_bg",
    "database": "bg_data",
    "password": "change_me"
  }
}
```

Required top-level keys:

- `pilot`
- `bg`

Required fields for `pilot` and `bg`:

- `host`
- `username`
- `database`
- `password`

Optional fields for `pilot` and `bg`:

- `name`
- `engine`

`ICE` is a JSON list of Murmur ICE definitions. Each item uses this shape:

```json
[
  {
    "name": "optional label",
    "host": "127.0.0.1",
    "virtual_server_id": 1,
    "icewrite": "write-secret",
    "iceport": 6502,
    "iceread": "read-secret"
  }
]
```

Required per server:

- `host`
- `virtual_server_id`
- `icewrite`

Optional per server:

- `name`
- `iceport`
- `iceread`

Notes:

- `name` defaults to `host:virtual_server_id` when omitted.
- `iceread` is optional; if omitted, bg may reuse `icewrite`.
- `iceport` may be provided, but bg should discover it when absent.

`MURMUR_PROBE` is a JSON list of optional Murmur DB probe definitions. Each item uses this shape:

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

Notes:

- `name` defaults to `host` when omitted.
- `MURMUR_PROBE` is optional and debug-only.
- If `MURMUR_PROBE` is absent, normal operation still proceeds over ICE only.
- `dbengine` and `dbport` may be provided, but bg should discover them when absent.

## Appendix: Fill-In Table

**Host Access**

| Secret | Value |
| --- | --- |
| `CUBE_DEV_CUBE` | `{"host":"<deploy_host>","user":"<deploy_user>","key":"-----BEGIN OPENSSH PRIVATE KEY-----\\n...\\n-----END OPENSSH PRIVATE KEY-----"}` |

Target JSON shape:

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

Optional target JSON fields:

- `home_dir` (default `/home/<user>`)
- `project_dir` (default `<home_dir>/mumble-bg`)
- `env_file` (default `<home_dir>/.env/mumble-bg`)
- `venv_dir` (default `<home_dir>/.venv/mumble-bg`)
- `service_name` (default `mumble-bg-auth`)

**Databases**

| Secret | Value |
| --- | --- |
| `DATABASES` | |
| `BG_ENGINE` | |

**Murmur ICE**

| Secret | Value |
| --- | --- |
| `ICE` | |

**Murmur Probe**

| Secret | Value |
| --- | --- |
| `MURMUR_PROBE` | |
