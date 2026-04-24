# BG Testing Guide

This document groups the BG-side inspection and testing commands by dependency.

The key distinction is:

- standalone BG tests: no host emulator, Cube, or FG required
- cached-FG-data tests: no live FG process required, but BG must already hold pilot snapshot / ACL data
- end-to-end tests: require the host emulator used for integration testing, with FG installed and talking to BG

## 1. Standalone BG Tests

These can be run with only BG, its own DB, and optional local Murmur/ICE endpoints.

### Environment and install checks

- `python -m django init_bg_env`
  Creates or updates `~/.env/mumble-bg`.
- `python -m django install_assistant`
  Verifies BG DB, control URL/bind, encryption/key readiness, ICE reachability, and authd registration ability.
- `python -m django generate_bg_keypair`
  Creates BG password-encryption keys.
- `python -m django print_systemd_bg_control --env-file ~/.env/mumble-bg`
- `python -m django print_systemd_bg_authd --env-file ~/.env/mumble-bg`
  Emits systemd unit text for the current installation.

### Local Murmur / ICE harness

- `python -m django start_local_murmur`
  Starts a local Murmur test instance and writes matching `MumbleServer` rows.
- `python -m django sync_ice_inventory`
  Syncs the `ICE` env declaration into BG-owned `MumbleServer` rows.
- `python -m django list_ice_users`
  Reads current registered users from ICE and compares them to BG state.
- `python -m django probe_murmur_sqlite --sqlite-path <path>`
  Reads a local Murmur SQLite DB directly. Useful for harness/debug only.
- `python -m django verify_auth_fallback`
  Exercises authd-vs-Murmur login fallback behavior against a test setup.

### Disposable reset flag for test-only runs

For disposable local test runs, `BG_RESET_DB_ON_DEPLOY=True` may be placed in the local BG env file before running the deploy/bootstrap path.

Important constraints:

- this is test-only and is not part of the normal GitHub workflow secret model
- stop `mumble-server` before invoking the reset path
- remove or unset `BG_RESET_DB_ON_DEPLOY` after the reset run

Use it only when the target BG and Murmur data are disposable.

### Runtime observation

- `curl http://127.0.0.1:18080/v1/health`
  Verifies BG HTTP control is up.
- `curl http://127.0.0.1:18080/v1/public-key`
  Verifies BG public key publication.
- `python -m django run_murmur_pulse --once`
  Performs one pulse/reconcile pass when configured.

## 2. Tests That Need Cached FG State

These commands do not require a live FG process at execution time, but they do require BG to already have:

- synced access rules
- synced pilot snapshot data
- usually synced EVE object names/tickers

Normally that data arrives from FG, but it may also be loaded manually through BG control endpoints for test purposes.

### State comparison and provisioning

- `python -m django provision_registrations`
  Evaluates cached pilot snapshot plus ACL rules and reports planned BG registration changes.
- `python -m django provision_registrations --apply`
  Applies BG-side create/activate/deactivate changes.
- `python -m django list_acls`
  Compares ACL state between cached FG-derived data and BG registration state.
- `python -m django list_acl_to_ice`
  Compares ACL decisions to live ICE registration state.
- `python -m django sync_mumble_registrations`
  Backfills or adopts Murmur registrations for active BG users.

### BG control API reads that depend on cached FG state

- `GET /v1/access-rules`
- `GET /v1/eve-objects`
- `GET /v1/registrations`
- `GET /v1/pilot/<pkid>`
- `POST /v1/provision`

If BG has never received FG data, these endpoints will either return empty results or reflect only locally-created BG state.

## 3. End-to-End Tests That Require the Host Emulator + FG

These tests exercise the real FG/BG boundary and require the host-side app.

### ACL UI flow

- create, toggle, delete, or admin-mark ACL rules in `/mumble-ui/acl/`
- trigger `Sync BG`
- confirm BG receives:
  - access-rule sync
  - EVE-object sync
  - pilot-snapshot sync
  - provision request

### Pilot profile flow

- open `/profile/`
- verify BG server list renders in the Mumble panel
- reset or set a password through FG
- confirm BG records and propagates the change

### Host-identity and eligibility flow

- verify FG resolves the correct pilot identity from host data
- verify BG receives the expected `pkid`, username, display name, corp/alliance ids, and pilot hash
- verify denied or admin-related host ACL changes become visible in BG and Murmur

## 4. Dependency Summary

### No FG required

- env generation
- install assistant
- key generation
- local Murmur harness
- ICE inventory sync
- ICE user inspection
- direct Murmur SQLite probe
- auth fallback harness

### FG data required, but not a live FG process

- registration provisioning
- ACL comparison
- BG-vs-ICE comparison
- per-pilot registration inspection

### Live host emulator + FG required

- ACL admin UI behavior
- `/profile/` panel behavior
- end-to-end password reset/set
- full FG-to-BG sync behavior

## 5. Practical Testing Order

Recommended progression:

1. `init_bg_env`
2. `install_assistant`
3. `generate_bg_keypair`
4. `sync_ice_inventory`
5. `start_local_murmur` or real ICE-backed Murmur
6. `list_ice_users`
7. feed BG with FG data
8. `provision_registrations --apply`
9. `list_acl_to_ice`
10. end-to-end UI checks from the host emulator used for integration testing
