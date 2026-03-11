# Deploy And Workflow Inventory

This repository was bootstrapped from the in-tree Mumble background implementation. The first standalone deploy defaults now live here, but Cube still carries the legacy deploy wiring that should be removed later.

## Where The Current Deploy Logic Lives

In `cube`, the current Mumble-related deployment logic is still split across:

- `deploy/setup-hetzner.sh`
- `.github/workflows/deploy-dev.yml`

Older Docker wiring also exists on the `cube-newmumble-upstream` source branch, but that path was already removed from current `cube` `main` and should not be treated as the target deployment model.

## Mumble-Owned Deploy Behavior In Cube Today

### Hetzner Setup

`cube/deploy/setup-hetzner.sh` currently owns:

- sudoers entry allowing restart of `mumble-bg-auth`
- creation of a dedicated `mumble-bg` virtualenv
- installation of the `mumble-bg-auth` systemd service
- enabling that service on boot

The current service definition is effectively:

- working directory: `.../mumble-bg`
- env file: `.../.env`
- exec: `.../.venv/mumble-bg/bin/python -m bg.authd`

### GitHub Actions

`cube/.github/workflows/deploy-dev.yml` currently owns:

- rsync of the whole Cube repo to the server
- installation of `mumble-bg` dependencies
- restart of `mumble-bg-auth`

This means Cube currently deploys the Mumble backend as part of the Cube app deploy, even though it is logically a separate runtime.

## Standalone Default Layout

The default standalone layout for this repository is:

- repo checkout: `/home/cube/mumble-bg`
- virtualenv: `/home/cube/.venv/mumble-bg`
- environment file: `/home/cube/.env/mumble-bg`
- service name: `mumble-bg-auth`

## What Moves To mumble-bg

When `mumble-bg` becomes the real standalone project, it should own:

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

It should stop deploying or supervising `mumble-bg` runtime processes.

The extracted Cube-facing Django code now lives in the sibling repository `../mumble-fg` rather than in this repo.

## Environment / Secret Contract

The extracted background service currently expects:

- `CUBE_CORE_DATABASE_NAME`
- `CUBE_CORE_DATABASE_HOST`
- `CUBE_CORE_DATABASE_USER`
- `CUBE_CORE_DATABASE_PASSWORD`
- optional `CUBE_CORE_DATABASE_ENGINE` (`postgresql` or `mysql`, default autodetect)

That is the model where it reads Cube core for pilot identity and uses `MMBL_BG_*` for its own runtime tables.

The target split model is:

- `mumble-bg` should use its own runtime/private DB
- `mumble-bg` should get read-only credentials for the Cube DB using `CUBE_CORE_*`
- the owned schema in this repo should use `MMBL_BG_*`
- any writeback or command channel should be explicit and not rely on Cube deploying the service

## What Not To Carry Forward

Do not treat the old Docker path as required deployment state.

The current target is:

- rsync checkout to `/home/cube/mumble-bg`
- install requirements into `/home/cube/.venv/mumble-bg`
- manage the systemd unit from this repository
- use `deploy/setup-hetzner.sh` once as root, then use the GitHub workflow for routine updates
