# Deploy And Workflow Inventory

This repository was bootstrapped from the in-tree Cube Mumble implementation. The first standalone deploy defaults now live here, but Cube still carries the legacy deploy wiring that should be removed later.

## Where The Current Deploy Logic Lives

In `cube`, the current Mumble-related deployment logic is still split across:

- `deploy/setup-hetzner.sh`
- `.github/workflows/deploy-dev.yml`

Older Docker wiring also exists on the `cube-newmumble-upstream` source branch, but that path was already removed from current `cube` `main` and should not be treated as the target deployment model.

## Mumble-Owned Deploy Behavior In Cube Today

### Hetzner Setup

`cube/deploy/setup-hetzner.sh` currently owns:

- sudoers entry allowing restart of `cube-mumble-auth`
- creation of a dedicated `mumble_authenticator` virtualenv
- installation of the `cube-mumble-auth` systemd service
- enabling that service on boot

The current service definition is effectively:

- working directory: `.../mumble_authenticator`
- env file: `.../.env`
- exec: `.../mumble_authenticator/venv/bin/python .../mumble_authenticator/authenticator.py`

### GitHub Actions

`cube/.github/workflows/deploy-dev.yml` currently owns:

- rsync of the whole Cube repo to the server
- installation of `mumble_authenticator` dependencies
- restart of `cube-mumble-auth`

This means Cube currently deploys the Mumble backend as part of the Cube app deploy, even though it is logically a separate runtime.

## Standalone Default Layout

The default standalone layout for this repository is:

- repo checkout: `/home/cube/cube-monitor`
- virtualenv: `/home/cube/.venv/cube-monitor`
- environment file: `/home/cube/.env/cube-monitor`
- service name: `cube-mumble-auth`

## What Moves To cube-mumble

When `cube-mumble` becomes the real standalone project, it should own:

- its own deploy scripts under `deploy/`
- its own GitHub Actions workflows under `.github/workflows/`
- its own systemd service definitions
- its own virtualenv setup and dependency installation
- its own restart/health-check flow

That future deploy should manage at least:

- the Mumble authenticator daemon
- any Murmur pulse / reconciliation service that remains part of the standalone runtime

## What Should Stay In cube-core

`cube-core` should keep only:

- deployment of the Cube web app and Celery services
- Cube DB schema and migrations
- Cube-side UI and admin policy inputs

It should stop deploying or supervising `cube-mumble` runtime processes.

## Environment / Secret Contract

The extracted authenticator currently expects:

- `DATABASE_NAME`
- `DATABASE_HOST`
- `DATABASE_PORT`
- `DATABASE_USER`
- `DATABASE_PASSWORD`
- optional `MUMBLE_ICE_SLICE`

That is still the old model where it reads Cube's Mumble tables directly.

The intended target model is different:

- `cube-mumble` should use its own runtime/private DB
- `cube-mumble` should get read-only credentials for the Cube DB
- any writeback or command channel should be explicit and not rely on Cube deploying the service

## What Not To Carry Forward

Do not treat the old Docker path as required deployment state.

The current target is:

- rsync checkout to `/home/cube/cube-monitor`
- install requirements into `/home/cube/.venv/cube-monitor`
- manage the systemd unit from this repository
- use `deploy/setup-hetzner.sh` once as root, then use the GitHub workflow for routine updates
