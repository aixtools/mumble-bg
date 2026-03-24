# Workflow Deployment

This document describes the current GitHub Actions deployment behavior for `mumble-bg`.

## 1. Current Workflow Files

- `.github/workflows/deploy-dev.yml`
- `.github/workflows/deploy-prod.yml`

The workflows are not identical. Dev and prod currently use different secret layouts.

## 2. Dev Workflow

The dev workflow is the cleaned path.

Required secrets:

- `TARGETHOST`
- `TARGETUSER`
- `BG_DBMS`
- `ICE`
- `BG_PSK`

Common optional values:

- `MURMUR_PROBE`
- `BG_RESET_DB_ON_DEPLOY`

`TARGETHOST` is a single hostname value.

`TARGETUSER` is JSON:

```json
{
  "user": "${WorkflowUser}",
  "key": "-----BEGIN OPENSSH PRIVATE KEY-----\\n...\\n-----END OPENSSH PRIVATE KEY-----",
  "home_dir": "~${WorkflowUser}",
  "project_dir": "~${WorkflowUser}/mumble-bg",
  "env_file": "~${WorkflowUser}/.env/mumble-bg",
  "venv_dir": "~${WorkflowUser}/.venv/mumble-bg",
  "service_units": ["bg-control", "bg-authd"]
}
```

Dev workflow currently:

- resolves `TARGETHOST` and `TARGETUSER`
- rsyncs code
- writes the target env file
- creates venv if needed
- installs requirements
- optionally bootstraps a local BG database
- runs migrations
- restarts configured service units

The dev workflow now writes `BG_DBMS` and `BG_PSK` directly instead of legacy aliases.

## 3. Prod Workflow

Current prod defaults:

- target secret: `MUMBLE_PROD_US`
- env secret: `MUMBLE_PROD_US_ENV`

Prod target secret is JSON with deploy connection and path data.
Prod env secret is JSON containing environment payload values.

Prod workflow currently:

- rsyncs code
- writes the target env file from the env JSON secret
- bootstraps system packages, venv, and systemd units on first deploy
- installs requirements
- migrates
- restarts the configured service

The remaining prod migration work is tracked in:

- [docs/prod_workflow_migration.md](./prod_workflow_migration.md)

## 4. Database Engine Note

Bootstrap defaults to PostgreSQL.

If MySQL/MariaDB is required, set:

```bash
BG_ENGINE=mysql
```

That is an override path. PostgreSQL is the default assumption.

## 5. One-Time Bootstrap vs Routine Updates

Treat these as separate concerns:

- `deploy/setup-root.sh` is the one-time root/operator bootstrap path
- GitHub workflow runs are routine update paths after bootstrap exists

The workflow does not replace all first-install operator work. It assumes the target host can already accept the deploy user, key, and service model being used.
