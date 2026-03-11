# Bootstrap Dev Deploy

This document covers the initial one-time setup for deploying `mumble-bg` from GitHub Actions to the dev host.

This is for the current standalone background-service phase only.

## What The Workflow Does

The workflow in `.github/workflows/deploy-dev.yml`:

- rsyncs this repository to `/home/cube/mumble-bg`
- writes `/home/cube/.env/mumble-bg`
- installs Python requirements into `/home/cube/.venv/mumble-bg`
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
- installs background-service requirements
- installs `/etc/systemd/system/mumble-bg-auth.service`
- installs sudoers for service restart/status
- enables and restarts the service

If the host still has stale auth service state, reset it first:

```bash
bash /home/cube/mumble-bg/deploy/undeploy-hetzner.sh
bash /home/cube/mumble-bg/deploy/setup-hetzner.sh
```

`deploy/undeploy-hetzner.sh` removes both legacy and current auth systemd units, removes the matching sudoers files, and deletes `/home/cube/.venv/mumble-bg`. It intentionally keeps the repo checkout and `/home/cube/.env/mumble-bg`.

4. Verify the service:

```bash
systemctl status mumble-bg-auth
journalctl -u mumble-bg-auth -n 50 --no-pager
```

## GitHub Actions Secrets

These must be configured in `aixtools/mumble-bg`:

- `HETZNER_DEV_SSH_KEY`
- `HETZNER_DEV_HOST`
- `HETZNER_DEV_USER`
- `CUBE_CORE_DATABASE_NAME`
- `CUBE_CORE_DATABASE_HOST`
- `CUBE_CORE_DATABASE_USER`
- `CUBE_CORE_DATABASE_PASSWORD`
- optional `CUBE_CORE_DATABASE_ENGINE` (`postgresql` or `mysql`, default autodetect)
- `MMBL_BG_DATABASE_NAME`
- `MMBL_BG_DATABASE_HOST`
- `MMBL_BG_DATABASE_USER`
- `MMBL_BG_DATABASE_PASSWORD`
- optional provisioning-only `MMBL_BG_DATABASE_ENGINE` for `deploy/create-db.sh`

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
