# System Boundary

This repository is a private runtime for Mumble authentication, ICE integration,
and related automated decision-making.

These constraints are locked:

- No direct DB coupling from `eveo` into this repo.
- No writes from this repo into `eveo_core` tables.
- All cross-system actions go through explicit interfaces or messages, including
  password reset requests.

## Ownership

- `eveo_core` is authoritative and read-only from the perspective of this repo.
- This repo owns its private runtime/auth database and its daemon state.
- The UI/admin integration layer (`mumble-fg`) mediates operator actions and
  presentation across systems.

## Allowed Cross-System Flow

- This repo may read instruction/state from `eveo_core` through explicit
  read-only contracts.
- UI/admin actions that must affect this repo should arrive through explicit
  interfaces/messages, not direct DB access.
- Data collected by runtime daemons in this repo may be surfaced to the UI layer
  only through explicit interfaces/messages.

The current fg/bg control contract is documented in
[docs/mumble-control.md](/home/michael/prj/mumble-bg/docs/mumble-control.md).

## Murmur Contract

The shared Murmur configuration is split into two structured JSON secrets:

- `ICE`
- `MURMUR_PROBE`

`ICE` is the required ICE/runtime contract.

Shape:

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

Required fields per server:

- `host`
- `virtual_server_id`
- `icewrite`

Optional fields per server:

- `name`
- `iceport`
- `iceread`

Rules:

- `name` defaults to `host:virtual_server_id` when omitted.
- `icewrite` is the required control path for `authd`.
- `iceread` is optional and is intended for `pulse` or other read-only ICE access.
- If `iceread` is omitted, `icewrite` may be reused.
- `iceport` may be supplied, but bg should discover it when absent.

`MURMUR_PROBE` is the optional Murmur DB probe/debug contract.

Shape:

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

Required fields per probe target:

- `host`
- `username`
- `database`
- `password`

Optional fields per probe target:

- `name`
- `dbport`
- `dbengine`

Rules:

- `name` defaults to `host` when omitted.
- `MURMUR_PROBE` is optional and debug-only.
- If `MURMUR_PROBE` is absent, normal ICE operation still proceeds.
- `dbport` and `dbengine` may be supplied, but bg should discover them when absent.

## Pilot Eligibility Decision Tables

FG pushes access-control decision tables to BG via the control channel:

- **allowed_access**: alliance IDs (in or out)
- **blocked_access**: corp IDs, pilot IDs (within allowed alliances)

Precedence: pilot > corp > alliance (most specific wins). A pilot-level allow
overrides a corp block. Block checks are account-wide — if the main or any alt
matches a block, the entire account is denied unless a pilot-level allow
overrides it.

BG stores its own copy of these tables and autonomously provisions accounts.

## Disallowed Cross-System Flow

- No direct reads by `eveo` from this repo's private database.
- No direct writes by this repo into `eveo_core`.
- No migrations in this repo for tables owned by `eveo_core`.
