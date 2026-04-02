# Cube / cube_mumble Boundary Notes

This note records the intended direction for splitting Cube's current Mumble
feature into:

- `cube-core`
- `cube_mumble`

The package name is not final. The important part is the boundary.

## Core Decision

`cube_mumble` should become a standalone service, as self-supporting as
possible.

That means:
- it should live outside the Cube source tree
- it may run under a different Unix user
- it should not depend on in-process Django imports from Cube
- it should read from the Cube database only
- it should keep its own operational database, not exposed to Cube

Cube should still have some Mumble-related UI and admin behavior, but Cube
should not talk to ICE and should not own Murmur runtime behavior.

## High-Level Boundary

### cube-core owns

- user-facing intent
- policy
- permissions
- desired Mumble state
- requests to change that state
- the shared database contract that `cube_mumble` consumes

### cube_mumble owns

- ICE / Murmur interaction
- reconciliation against the desired state in Cube
- operational state
- runtime credentials and secrets for Mumble-facing work
- its own database

## One-Way Data Flow

The intended direction is:

1. Cube users and admins act in `cube-core`.
2. `cube-core` records desired state in the Cube database.
3. `cube_mumble` reads that desired state from the Cube database.
4. `cube_mumble` applies it to Murmur and stores runtime details in its own
   database.

The key point is:

- Cube DB is an input to `cube_mumble`.
- `cube_mumble` DB is not an input to Cube.

This keeps the coupling honest.

## Database Ownership

### Cube database

The Cube database should contain only the data `cube-core` owns and
`cube_mumble` needs to read.

That means the Cube DB should hold:
- desired account existence / activation state
- desired username / display name
- desired groups
- desired admin flags
- canonical password record for Cube-managed password auth
- server targeting and routing information
- password reset or password-set requests as commands, if Cube initiates those
- audit-friendly intent records

The Cube DB should not hold `cube_mumble` runtime state.

If Cube keeps the pilot-facing password reset / set-password flow, then the
Cube DB contract should include the Murmur-compatible password fields used by
the authenticator, for example:
- `pwhash`
- `hashfn`
- `pw_salt`
- `kdf_iterations`

Those fields are part of desired authentication state, not merely runtime
state.

### cube_mumble database

The `cube_mumble` database should hold:
- cert hashes
- connection/session history
- last-seen / last-applied sync state
- Murmur-side identifiers if needed
- internal reconciliation state
- service-local configuration and cache

Cube should not read from this database.

## What This Changes

This is stronger than the earlier "extract the Django app" idea.

The extraction target is not:
- move `modules/mumble` out
- move `mumble_authenticator` out
- keep the same ownership model somewhere else

The extraction target is:
- redesign the ownership model
- split desired state from runtime state
- keep only the desired-state and management surface in `cube-core`
- move all ICE-facing and operational behavior into `cube_mumble`

## What cube-core Needs

### 1. Mumble management UI

Cube should keep the user and admin surfaces where people express intent.

Examples:
- activate / deactivate account
- request password reset
- request custom password change, if that remains a Cube-side feature
- grant / revoke Mumble admin intent
- display desired groups / display name

These views should mutate Cube-owned desired state only.

For password changes, Cube should generate or accept the password, derive the
Murmur-compatible password record immediately, persist only the derived record,
and expose the plaintext only at the moment it must be shown back to the user.

### 2. Shared contract tables or models

Cube should own the schema that expresses what `cube_mumble` should do.

This schema should be stable, explicit, and documented.

Possible shapes:
- desired-state tables
- command / queue tables
- append-only event log plus materialized desired-state rows

The exact shape is open, but Cube should own it because it is the public
contract between the two systems.

### 3. Policy computation

Cube should continue to decide policy using Cube concepts such as:
- who the pilot is
- main character
- group memberships
- corp / alliance-derived group naming
- whether a user should have Mumble admin

`cube_mumble` should consume those decisions, not reproduce Cube policy.

That same principle applies to password hashing:
- Cube should own the canonical password record if Cube owns the password-reset
  UX
- `cube_mumble` should consume that record

### 4. Permissions and audit trail

Cube should remain the place where:
- permissions are checked
- leadership actions are authorized
- user-initiated changes are recorded
- intent history can be inspected

### 5. Mumble-agnostic extension seams

Cube still should not hard-code Mumble assumptions directly into core.

The generic extension work remains useful because the Cube-side Mumble
management surface should still plug in as an integration, not as ad hoc core
special cases.

### 6. Migration cleanup

Cube core must not keep historical migration coupling to the old in-tree
Mumble app.

This is still non-negotiable:
- if Cube is meant to be Mumble-agnostic, the `accounts -> mumble` migration
  dependency has to go

## What cube_mumble Needs

### 1. Separate repository / tree

`cube_mumble` should not live under the Cube source tree long-term.

It should be able to:
- deploy independently
- version independently
- run under a different service account
- have its own runtime packaging

### 2. Read-only access to Cube DB

`cube_mumble` should read the Cube DB contract through a read-only role.

That matters because it forces a cleaner interface:
- Cube expresses intent
- `cube_mumble` consumes intent
- `cube_mumble` does not mutate Cube-owned state behind Cube's back

This still works if Cube stores Murmur-compatible password hashes. In that
model, `cube_mumble` reads the canonical password record from Cube instead of
owning it privately.

### 3. Its own operational DB

`cube_mumble` should own a separate database for runtime state.

This keeps:
- Mumble runtime details
- session tracking
- reconciliation internals

out of Cube's domain model.

### 4. ICE and Murmur ownership

All ICE-facing behavior should live in `cube_mumble`.

That includes:
- account reconciliation
- password application
- group application
- admin flag application
- session / pulse / presence logic
- daemon / worker runtime

Cube should not call ICE directly.

### 5. Reconciliation loop

`cube_mumble` should behave like a reconciler:
- read desired state from Cube
- compare against its own applied state and Murmur reality
- converge Murmur toward desired state
- record runtime results locally

### 6. Failure isolation

If `cube_mumble` is down:
- Cube should still boot
- Cube should still let authorized users express intent
- the shared contract should queue up the desired state
- reconciliation should resume when `cube_mumble` comes back

## Shared Contract Principles

The Cube DB contract should be:
- explicit
- versionable
- readable without importing Cube code
- audit-friendly
- resilient to replay / retry

Bad contract patterns:
- sharing internal Django models by convention
- requiring `cube_mumble` to import Cube Python code
- storing runtime-only state in Cube tables
- letting `cube_mumble` write operational results back into Cube-owned rows

Good contract patterns:
- documented tables or views
- command records with timestamps and ids
- desired-state rows with clear ownership
- immutable or append-only history where useful

## Implications for Existing Code

The current in-tree Mumble code is mixed across two concerns:

- Cube-side intent and management
- Mumble-side execution and runtime state

That split needs to be made explicit before or during extraction.

In practice that means:
- some parts of current `modules/mumble` likely stay in Cube in redesigned form
- most of `mumble_authenticator`, ICE code, and pulse logic move to
  `cube_mumble`
- current models will likely need to be split rather than simply moved

One explicit exception: the canonical password record may stay in Cube if Cube
continues to own the user-facing password reset flow.

## Password Hashing Note

The `leo-auth` research already established the important password details:

- old `bcrypt-sha256` rows are not the right long-term model
- Murmur-compatible password records use PBKDF2-HMAC-SHA384
- the stored record includes:
  - `pwhash`
  - `hashfn`
  - `pw_salt`
  - `kdf_iterations`

So if pilots reset or set passwords in Cube, Cube should derive and store that
same Murmur-compatible record.

That lets `cube_mumble` authenticate against Cube-owned desired state without
needing Cube to store plaintext passwords.

## Separate Open Question: Murmur-Local Backup

There is still a separate question if `cube_mumble` should also maintain a
Murmur-local backup registration over ICE.

Why this matters:
- the authenticator can verify against Cube-stored Murmur-compatible hashes
  without needing plaintext later
- but Murmur ICE registration calls expect plaintext when provisioning or
  updating a local password on the Murmur side

So there are two valid designs:

1. External-auth-only primary design
   - Cube stores the canonical Murmur-compatible password record
   - `cube_mumble` reads and verifies against that record
   - no long-lived plaintext channel is needed

2. External auth plus Murmur-local backup registration
   - Cube still stores the canonical Murmur-compatible password record
   - but a reset/set-password flow also needs a one-time plaintext handoff for
     the ICE registration update path

That second design is possible, but it is a distinct requirement and should not
be hidden inside the basic Cube DB contract discussion.

## Suggested Extraction Order

1. Clean Cube core so it no longer hard-codes Mumble assumptions directly.
2. Remove the old migration coupling from Cube core.
3. Define the Cube DB contract that `cube_mumble` will read.
4. Split current Mumble models into Cube-owned desired state vs
   `cube_mumble`-owned runtime state.
5. Keep Cube-side management UI in Cube, but make it write only Cube-owned
   desired state / commands.
6. Move ICE, pulse, authenticator, and reconciliation logic into
   `cube_mumble`.
7. Give `cube_mumble` its own DB and read-only Cube DB access.
8. Remove any remaining direct ICE usage from Cube.

## Suggested PR Slicing

### PR 1: Cube core cleanup

- remove direct Mumble assumptions from Cube core where they do not belong
- introduce generic extension seams where needed
- remove the old migration dependency

### PR 2: Cube contract introduction

- add Cube-owned desired-state / command schema
- convert Cube UI and admin flows to write that schema
- keep behavior local for now where necessary, but pivot ownership to Cube

### PR 3: cube_mumble service extraction

- create the separate service/repo
- move ICE and runtime logic there
- make it read Cube state and maintain its own DB

### PR 4: Final decoupling

- remove Cube's remaining direct runtime/ICE behavior
- trim compatibility glue
- tighten docs and operational setup

## Guiding Principle

Cube should own intent.

`cube_mumble` should own execution.

Anything that blurs that line should be treated as design debt.
