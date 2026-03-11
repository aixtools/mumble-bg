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

## Disallowed Cross-System Flow

- No direct reads by `eveo` from this repo's private database.
- No direct writes by this repo into `eveo_core`.
- No migrations in this repo for tables owned by `eveo_core`.
