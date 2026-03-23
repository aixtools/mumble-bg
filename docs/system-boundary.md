# System Boundary

`mumble-bg` is the private runtime side of the FG/BG split. On this branch it
owns runtime state, Murmur integration, and cached FG snapshot data, while
`mumble-fg` remains the only side that reads host/pilot data directly.

## Locked Rules

- FG and host apps do not read `BG_DBMS` directly.
- BG does not read or write host-owned pilot/core tables directly.
- FG sends ACL rules and pilot snapshot data to BG through explicit control
  endpoints.
- BG persists its own runtime/auth state and the cached pilot snapshot inside
  `BG_DBMS`.
- Cross-system actions such as password reset, provision, and registration sync
  go through the control API, not shared DB writes or shared imports.

## Database Terms

- `BG_DBMS` means the BG-owned database contract and persisted state surface.
- `PILOT_DBMS` means the host-side pilot data source that FG reads from.

Current implementation note:

- BG code and deploy scripts load `BG_DBMS` from the `BG_DBMS` env var.
- Legacy `DATABASES` values are still accepted as a compatibility fallback.

## Allowed Cross-System Flow

- FG -> BG control/probe endpoints over HTTP + JSON
- BG -> Murmur over ICE for runtime reconciliation
- optional BG -> Murmur DB probe reads for debugging/verification only

## Disallowed Cross-System Flow

- FG or host-app direct reads from BG runtime tables
- BG direct reads from `PILOT_DBMS`
- BG writes into host-owned pilot/core tables
- hidden side channels through shared ORM models across repos

## Configuration Surface

The shared runtime configuration that crosses the repo boundary is intentionally
narrow:

- `BG_DBMS`
- `ICE`
- `MURMUR_PROBE`
- control URL/secret settings used by FG to reach BG

Pilot eligibility is no longer a DB-sharing contract. FG computes and exports a
pilot snapshot, then BG stores that snapshot in BG-owned cache tables before
provision/reconcile.
