# Mumble Control

`mumble_control` is the explicit FG -> BG control path.

Its purpose is to keep the repo boundary clean:

- no direct FG reads from `BG_DBMS`
- no direct BG reads from `PILOT_DBMS`
- no BG writes into host-owned tables
- no long-term shared Python-import contract across repos

## Transport

Current control transport is HTTP + JSON served by `mumble-bg`.

Security/auth is based on the control secret:

- `MURMUR_CONTROL_PSK` for FG -> BG requests
- DB-backed control-key lifecycle state in `control_channel_key`

## Current Endpoint Surface

The live BG branch currently exposes:

- `GET /v1/health`
- `GET /v1/public-key`
- `GET /v1/servers`
- `GET /v1/registrations`
- `GET /v1/pilot/<pkid>`
- `GET /v1/pilots/<pkid>`
- `GET /v1/access-rules`
- `GET /v1/control-key/status`
- `POST /v1/access-rules/sync`
- `POST /v1/pilot-snapshot/sync`
- `POST /v1/provision`
- `POST /v1/password-reset`
- `POST /v1/registrations/sync`
- `POST /v1/registrations/contract-sync`
- `POST /v1/registrations/disable`
- `POST /v1/admin-membership/sync`
- `POST /v1/control-key/bootstrap`
- `POST /v1/control-key/rotate`

## Provisioning Sequence

The normal FG -> BG sync sequence on this branch is:

1. send ACL rules to `/v1/access-rules/sync`
2. send pilot snapshot to `/v1/pilot-snapshot/sync`
3. request reconcile/provision through `/v1/provision`

BG then evaluates eligibility from:

- synced access rules
- cached FG pilot snapshot data already stored in `BG_DBMS`

## Boundary Consequences

- FG mutating flows must go through control endpoints.
- BG probe/status reads are the verification surface for FG.
- Pilot snapshot sync replaces the older idea of BG reading pilot data from a
  shared or read-only host DB.

For the full service contract, see `docs/fg-bg-contracts.md`.
