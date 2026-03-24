# Prod Workflow Migration Project

Temporary document. Delete this file after the prod workflows are cleaned and `docs/deploy_workflow.md` is updated to the final steady-state behavior.

## Purpose

Dev workflows now use the cleaned secret/runtime contract. Prod still uses older secret shapes and legacy control/env names.

This document tracks the remaining migration work for prod deployment.

## Target State

Prod SHALL converge on the same core conventions used by dev:

- `TARGETHOST` as a single hostname secret
- `TARGETUSER` as the deploy-target JSON secret
- `BG_DBMS` instead of `DATABASES`
- `BG_PSK` instead of `FGBG_PSK` / `MURMUR_CONTROL_PSK`
- service-unit lists instead of single legacy service-name assumptions

## BG Prod Migration Work

### 1. Replace target/env secret split

Current prod BG uses:

- `MUMBLE_PROD_US`
- `MUMBLE_PROD_US_ENV`

Migration goal:

- keep `TARGETUSER` for connection/path details
- stop requiring a separate JSON env secret object when direct repo/env secrets are sufficient

### 2. Remove legacy env names

Current prod BG still writes:

- `DATABASES`
- `MURMUR_CONTROL_PSK`

Migration goal:

- write `BG_DBMS`
- write `BG_PSK`
- keep runtime reset handling on `BG_PSK:reset`

### 3. Align service-unit model

Current prod BG still assumes a single configured service name.

Migration goal:

- accept `service_units`
- restart/check both control and authd units when configured
- make unit naming consistent with the chosen service convention

## FG Prod Migration Work

### 1. Replace single target JSON secret

Current prod FG still uses `CUBE_PROD_CUBE`.

Migration goal:

- move to `TARGETHOST`
- move to `TARGETUSER`

### 2. Remove legacy control-secret handling

Current prod FG still relies on the older workflow model and does not use the cleaned `BG_PSK` dev path.

Migration goal:

- use `BG_PSK` only
- remove `FGBG_PSK` / `MURMUR_CONTROL_PSK` workflow handling

### 3. Decide bootstrap scope

Open decision:

- keep prod workflow as code-sync plus package bootstrap only
- or extend prod workflow to run `migrate` and `collectstatic`

This is intentionally left open until the desired prod operational boundary is confirmed.

## Completion Criteria

This document may be deleted when all of the following are true:

1. FG prod uses `TARGETHOST`, `TARGETUSER`, and `BG_PSK`.
2. BG prod uses `TARGETHOST`, `TARGETUSER`, `BG_DBMS`, and `BG_PSK`.
3. Legacy workflow names `FGBG_PSK`, `MURMUR_CONTROL_PSK`, and `DATABASES` are gone from prod workflow code.
4. `docs/deploy_workflow.md` in BG and FG describe prod as current behavior rather than migration work.
