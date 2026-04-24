# mumble-bg Design

Verified: `mumble-bg` `main` version `0.3.7.dev1` on `2026-04-24`.

## Purpose

`mumble-fg` owns host/UI/admin behavior.
`mumble-bg` owns runtime/state behavior.

BG exists so Murmur integration, ICE operations, authd, reconciliation, pulse, and runtime persistence stay isolated from host application data access.

## Ownership Boundary

BG owns:

- `BG_DBMS`
- Murmur server inventory and runtime registration state
- password hash material and plaintext password lifecycle during reset/set flows
- ICE integration and reconciler logic
- pulse/presence collection
- control-key bootstrap, export, and rotation
- BG-side audit rows

FG owns:

- ACL policy definition and host-side UI
- pilot snapshot generation
- host-side account and pilot reads
- host integration hooks for Cube-like apps
- control client calls into BG

Explicitly not allowed:

- FG does not read BG tables directly
- BG does not read host pilot/core tables directly
- BG does not write host-owned tables
- long-lived shared ORM behavior across repos is a defect

## Identity Model

The stable cross-system account key is `pkid`.

FG sends account-oriented snapshot data keyed by `pkid`. Each account contains:

- `account_username`
- `display_name`
- `pilot_data_hash`
- one or more characters
- exactly one main character after normalization

Operational identity rules:

- policy evaluation is account-wide, not character-row local
- pilot-facing names are human-readable display names, not `pkid`
- the login username contract for runtime registration is FG `account_username`
- Murmur registration rows are per `(server_key, pkid)`

## BG Runtime Model

BG runs with a small set of cooperating services:

- HTTP control service
- ICE authenticator daemon
- pulse/presence collector
- reconciler
- provisioning logic

BG-owned runtime rows include:

- `mumble_server`
  - one row per managed Murmur target, including address, ICE host/port, secret, virtual server id, optional TLS file paths, and stable `server_key`
- `murmur_server_inventory_snapshot`
  - last fetched per-server channel/group/ACL inventory payload and freshness metadata
- `mumble_user`
  - per-user per-server runtime registration state
- `mumble_session`
  - live and historical presence/session state observed from Murmur

## ACL and Admin Semantics

BG computes runtime eligibility from synced FG ACL rules and cached FG pilot snapshot state.

ACL precedence is:

1. pilot allow or deny
2. corporation deny
3. alliance allow

Additional rules:

- unlisted alliances are implicitly denied
- deny evaluation is account-wide
- an alt deny hit blocks the account unless overridden by a more specific allow
- `acl_admin` is pilot-only and does not imply allow
- denied pilots cannot remain effective admin
- corporation or alliance deny must clear effective admin state

BG tracks per-user admin state and synchronizes live membership when requested.

## Control Contract

FG uses BG control endpoints for runtime-affecting actions.

Core operations:

- ACL sync
- pilot snapshot sync
- reconcile/provision request
- password reset and password set
- live admin membership sync
- runtime server query for profile-panel display
- per-server inventory reads

Control authentication uses the BG control-secret/keyring model.

Preferred operator-facing names:

- `BG_PSK` for bootstrap/shared control auth
- `BG_PKI_PASSPHRASE` for BG key encryption

## Profile Panel Contract

The `/profile/` Mumble panel is visible only when the account is ACL-eligible.

Current implementation:

- FG renders one panel per available BG server
- each panel shows a fixed-text `Server` field from the BG server label/name
- if more than one eligible pilot is available, FG shows a `Mumble Authentication` selector for pilot choice

The panel displays:

- `Server`
- `Display Name`
- `Username`
- `Address`
- `Port`
- `IsAdmin` only when true

If BG is unavailable:

- `Address` shows `BG unavailable`
- password actions are disabled

## Current Direction

The current architecture is snapshot driven:

1. FG reads `PILOT_DBMS`
2. FG sends ACL rules and pilot snapshot data to BG
3. BG stores that data in `BG_DBMS`
4. BG provisions and reconciles Murmur state from its own cache plus runtime inputs
5. FG requests per-server inventory snapshots by stable `server_key` and renders the merged UI view

## Documentation Rule

Contract drift between docs and current code is a documentation bug.
