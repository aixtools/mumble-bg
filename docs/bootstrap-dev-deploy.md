# Bootstrap Dev Deploy

This document covers the initial one-time setup for deploying `cube-monitor` from GitHub Actions to the dev host.

This is for the current standalone authenticator phase only.

## What The Workflow Does

The workflow in `.github/workflows/deploy-dev.yml`:

- rsyncs this repository to `/home/cube/cube-monitor`
- writes `/home/cube/.env/cube-monitor`
- installs Python requirements into `/home/cube/.venv/cube-monitor`
- restarts `cube-monitor-auth`

It does **not** perform the first-time systemd/bootstrap install. That is what `deploy/setup-hetzner.sh` is for.

## Assumptions

- the target machine already has the `cube` user
- Murmur / `mumble-server` is already installed and running
- PostgreSQL is already installed and reachable
- this repo is deployed as `/home/cube/cube-monitor`

## One-Time Server Setup

Run these steps on the target host once.

1. Check out the repository using HTTPS credentials available to `gh`:

```bash
sudo -u cube gh auth login --hostname github.com --git-protocol https
```

Then:

```bash
sudo -u cube gh repo clone aixtools/cube-monitor /home/cube/cube-monitor
```

If the checkout already exists:

```bash
sudo -u cube git -C /home/cube/cube-monitor fetch origin
sudo -u cube git -C /home/cube/cube-monitor switch main
sudo -u cube git -C /home/cube/cube-monitor pull --ff-only origin main
```

2. Create the environment file:

```bash
install -d -m 0755 /home/cube/.env
install -m 0600 /home/cube/cube-monitor/.env.example /home/cube/.env/cube-monitor
```

Edit `/home/cube/.env/cube-monitor` with the real database values.

3. Run the one-time setup script as root:

```bash
bash /home/cube/cube-monitor/deploy/setup-hetzner.sh
```

This script:

- ensures `/home/cube/.venv/cube-monitor`
- installs authenticator requirements
- installs `/etc/systemd/system/cube-monitor-auth.service`
- installs sudoers for service restart/status
- enables and restarts the service

4. Verify the service:

```bash
systemctl status cube-monitor-auth
journalctl -u cube-monitor-auth -n 50 --no-pager
```

## GitHub Actions Secrets

These must be configured in `aixtools/cube-monitor`:

- `HETZNER_DEV_SSH_KEY`
- `HETZNER_DEV_HOST`
- `HETZNER_DEV_USER`
- `CUBE_CORE_DATABASE_NAME`
- `CUBE_CORE_DATABASE_HOST`
- `CUBE_CORE_DATABASE_USER`
- `CUBE_CORE_DATABASE_PASSWORD`
- optional `CUBE_CORE_DATABASE_ENGINE` (`postgresql` or `mysql`, default autodetect)
- `CUBE_MMBL_AUTH_DATABASE_NAME`
- `CUBE_MMBL_AUTH_DATABASE_HOST`
- `CUBE_MMBL_AUTH_DATABASE_USER`
- `CUBE_MMBL_AUTH_DATABASE_PASSWORD`
- optional `CUBE_MMBL_AUTH_DATABASE_ENGINE` (`postgresql` or `mysql`, default `postgresql`)

## SSH Key Clarification

`HETZNER_DEV_SSH_KEY` is **not** a GitHub deploy key for cloning the repository.

It is the private SSH key that the GitHub Actions runner uses to log into the target server.

That means:

- the matching public key must be present in `/home/cube/.ssh/authorized_keys` for the user named by `HETZNER_DEV_USER`
- if `HETZNER_DEV_USER=cube`, the key must authorize SSH as `cube`

If you previously stored this key only in `ru-dash/Cube`, that does not automatically make it available to `aixtools/cube-monitor`. GitHub Actions secrets are repo-scoped unless you deliberately use organization secrets.

## After Bootstrap

Once the one-time setup exists:

- push to `main`
- GitHub Actions deploys the new code
- the workflow refreshes `/home/cube/cube-monitor`
- dependencies in `/home/cube/.venv/cube-monitor` are updated
- `cube-monitor-auth` is restarted
