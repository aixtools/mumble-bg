# Extraction Inventory

This repository began as an extraction snapshot from the older in-tree Mumble
implementation in Cube.

Source snapshot:

- repo: `cube`
- branch: `cube-newmumble-upstream`
- commit: `2869fbc8ada6010d8823f50caf52d3b1779a30a7`

## What Was Copied Into `mumble-bg`

- `modules/mumble/`
- the old `authenticator/` package, rehomed under `bg/`

Those files were copied as a rebuild baseline, not as the final package layout.

## What Moved To `mumble-fg`

The Cube-facing Django/UI pieces were split out into the sibling repo:

- admin and profile UI
- sidebar integration
- host-facing tasks and extension hooks
- display-name backfill command
- host-coupled test coverage for FG flows

## Current Ownership Direction

The target split on this branch is:

- `mumble-fg`
  - host/UI/admin integration
  - ACL modeling and pilot snapshot export
  - the only side that reads host/pilot data directly

- `mumble-bg`
  - Murmur runtime services
  - registration/provisioning state
  - cached FG snapshot state
  - BG-owned runtime database (`BG_DBMS`)

## Important Architectural Shift

Older extraction notes assumed BG could read a host-side pilot DB through a
shared DB contract. That is no longer the branch direction here.

Current branch behavior is:

- FG reads `PILOT_DBMS`
- FG pushes pilot snapshot data to BG over the control API
- BG stores that snapshot in BG-owned cache tables inside `BG_DBMS`

That keeps the repo boundary API-oriented instead of DB-coupled.
