# Bootstrap Dev Deploy

This document covers the initial one-time setup for deploying `mumble-bg` from GitHub Actions to the dev host.

This is for the current standalone background-service phase only.

## What The Workflow Does

The workflow in `.github/workflows/deploy-dev.yml`:

- rsyncs this repository to `/home/cube/mumble-bg`
- writes `/home/cube/.env/mumble-bg`
- bootstraps `DATABASES.bg` via `deploy/create-db.sh` when the bg DB host is local
- installs Python requirements into `/home/cube/.venv/mumble-bg`
- runs `manage.py migrate`
- restarts `mumble-bg-auth`

It does **not** perform the first-time systemd/bootstrap install. That is what `deploy/setup-hetzner.sh` is for.

## Assumptions

- the target machine already has the `cube` user
- Murmur / `mumble-server` is already installed and running
- PostgreSQL is already installed and reachable
- this repo is deployed as `/home/cube/mumble-bg`

## One-Time Server Setup

Run these steps on the target host once.

1. Check out the repository using HTTPS credentials available to `gh`:

```bash
sudo -u cube gh auth login --hostname github.com --git-protocol https
```

Then:

```bash
sudo -u cube gh repo clone aixtools/mumble-bg /home/cube/mumble-bg
```

If the checkout already exists:

```bash
sudo -u cube git -C /home/cube/mumble-bg fetch origin
sudo -u cube git -C /home/cube/mumble-bg switch main
sudo -u cube git -C /home/cube/mumble-bg pull --ff-only origin main
```

2. Create the environment file:

```bash
install -d -m 0755 /home/cube/.env
install -m 0600 /home/cube/mumble-bg/.env.example /home/cube/.env/mumble-bg
```

Edit `/home/cube/.env/mumble-bg` with the real database values.

If you need to create a fresh local database/user first, use:

- [docs/database-bootstrap.md](/home/michael/prj/mumble-bg/docs/database-bootstrap.md)
- [deploy/create-db.sh](/home/michael/prj/mumble-bg/deploy/create-db.sh)

3. Run the one-time setup script as root:

```bash
bash /home/cube/mumble-bg/deploy/setup-hetzner.sh
```

This script:

- ensures `/home/cube/.venv/mumble-bg`
- provisions the local `mumble-bg` database/user if needed
- installs background-service requirements
- runs `manage.py migrate` for the `mumble-bg` schema
- installs `/etc/systemd/system/mumble-bg-auth.service`
- installs sudoers for service restart/status and local bg DB bootstrap
- enables and restarts the service

Database bootstrap behavior:

- uses `DATABASES.bg` from `/home/cube/.env/mumble-bg`
- uses optional `BG_ENGINE`, defaulting to PostgreSQL when omitted
- only bootstraps local database hosts (`127.0.0.1` or `localhost`)
- does not change the password of an already-existing database user

If the host still has stale auth service state, reset it first:

```bash
bash /home/cube/mumble-bg/deploy/undeploy-hetzner.sh
bash /home/cube/mumble-bg/deploy/setup-hetzner.sh
```

`deploy/undeploy-hetzner.sh` removes the current `mumble-bg-auth` systemd unit, removes the matching sudoers file, and deletes `/home/cube/.venv/mumble-bg`. It intentionally keeps the repo checkout and `/home/cube/.env/mumble-bg`.

4. Verify the service:

```bash
systemctl status mumble-bg-auth
journalctl -u mumble-bg-auth -n 50 --no-pager
```

## GitHub Actions Secrets

See the appendix below for the exact GitHub Actions configuration values to define in `aixtools/mumble-bg`.

## SSH Key Clarification

`HETZNER_DEV_SSH_KEY` is **not** a GitHub deploy key for cloning the repository.

It is the private SSH key that the GitHub Actions runner uses to log into the target server.

That means:

- the matching public key must be present in `/home/cube/.ssh/authorized_keys` for the user named by `HETZNER_DEV_USER`
- if `HETZNER_DEV_USER=cube`, the key must authorize SSH as `cube`

If you previously stored this key only in `ru-dash/Cube`, that does not automatically make it available to `aixtools/mumble-bg`. GitHub Actions secrets are repo-scoped unless you deliberately use organization secrets.

## After Bootstrap

Once the one-time setup exists:

- push to `main`
- GitHub Actions deploys the new code
- the workflow refreshes `/home/cube/mumble-bg`
- dependencies in `/home/cube/.venv/mumble-bg` are updated
- `mumble-bg-auth` is restarted

## Appendix: GitHub Actions Configuration

Required runtime/deploy:

- `HETZNER_DEV_SSH_KEY`
- `HETZNER_DEV_HOST`
- `HETZNER_DEV_USER`

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
| `HETZNER_DEV_SSH_KEY` | |
| `HETZNER_DEV_HOST` | |
| `HETZNER_DEV_USER` | |

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
