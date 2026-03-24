# FG/BG Design Specification

This document is written as the design contract the FG/BG split is expected to satisfy.

## 1. Purpose

The Mumble integration is split into two components:

- `mumble-fg` SHALL own host/UI/admin behavior.
- `mumble-bg` SHALL own runtime/state behavior.

BG exists so Murmur integration, ICE operations, authd, reconciliation, and runtime persistence are isolated from host application data access.

## 2. Boundary Rules

- BG SHALL own `BG_DBMS`.
- BG SHALL NOT read host pilot/core tables directly.
- BG SHALL NOT write host-owned tables.
- FG SHALL send ACL and pilot snapshot state to BG over explicit APIs.
- BG SHALL expose runtime control/probe APIs to FG.
- Shared cross-repo ORM behavior SHALL be treated as a defect.

## 3. BG-Owned State

BG SHALL own and persist:

- access rules copied from FG
- cached pilot snapshot rows copied from FG
- Murmur server inventory
- Murmur user/runtime registration state
- BG audit rows

Stable runtime identity SHALL be `pkid`.

Human-facing presentation values may be derived from:

- FG snapshot data
- BG cached ESI lookups when needed for corp/alliance naming and ticker resolution

## 4. Inputs from FG

BG SHALL accept at least:

- full ACL sync
- full pilot snapshot sync
- reconcile/provision requests
- password set/reset requests
- live admin-membership sync requests

ACL sync contract:

- full-table replacement on BG
- validation before apply
- ACL audit row only when the effective rule set changes

Pilot snapshot contract:

- full account-oriented payload keyed by `pkid`
- one account contains main and alt character state
- BG replaces its snapshot cache when the incoming payload changes

## 5. Eligibility and Provisioning

BG SHALL compute runtime eligibility from:

- synced FG ACL rules
- cached FG pilot snapshot state

ACL precedence SHALL be:

1. pilot allow/deny
2. corporation deny
3. alliance allow

Additional rules:

- unlisted alliances are implicitly denied
- deny evaluation is account-wide
- an alt deny hit blocks the account unless overridden by a more-specific allow
- `acl_admin` is pilot-only and SHALL NOT imply allow

Provisioning results:

- eligible + missing -> create BG and Murmur user
- eligible + inactive -> reactivate
- blocked + active -> disable
- blocked + missing -> no-op

Disabled users SHALL remain present in Murmur and BG state rather than being deleted.

## 6. Password and Authentication Contract

- BG SHALL generate and store password hash material.
- The same generated plaintext password SHALL be used for Murmur registration/update.
- BG SHALL audit password reset/set outcomes.
- BG SHALL support control-service password operations even when authd is not the active login path.

Preferred crypto/env naming:

- `BG_PSK` for FG/BG control authentication
- `BG_PKI_PASSPHRASE` for BG key encryption

Compatibility aliases may exist in code, but the preferred operator-facing names are the ones above.

## 7. Murmur and ICE Contract

BG SHALL own:

- ICE inventory
- Murmur user reconciliation
- live admin group membership sync
- optional Murmur DB probe reads for diagnostics only

One BG instance SHALL be able to manage zero, one, or many ICE targets.

When no ICE targets exist:

- BG control APIs SHALL still be reachable
- install/preflight checks SHALL report that no ICE endpoints are defined

## 8. Pilot and Admin Semantics

BG SHALL track per-user admin state and synchronize live membership when requested.

Rules:

- `acl_admin` is valid only on pilot rules
- denied pilots SHALL NOT remain admin
- corporation/alliance deny MUST clear effective admin state

Pilot-facing profile behavior expected by FG/BG together:

- one pilot account may expose many available servers
- selector label SHALL be `Server`
- option text SHALL come from the BG server label/name
- human-visible Mumble identity SHALL use resolved pilot/org naming, not internal `pkid`

## 9. Audit and Failure Semantics

- BG audit SHALL be append-only.
- Pilot-related BG audit events SHALL include create, enable, disable, password reset, login, and display-name update.
- Partial success SHALL be surfaced explicitly rather than hidden.

Examples:

- password hash updated but Murmur sync failed
- ACL sync noop but reconcile still performed
- ICE unreachable on one server while other servers continue to reconcile
