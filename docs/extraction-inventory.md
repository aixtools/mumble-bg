# Extraction Inventory

Source snapshot:

- repo: `cube`
- branch: `cube-newmumble-upstream`
- commit: `2869fbc8ada6010d8823f50caf52d3b1779a30a7`

Copied into this repository:

- `modules/mumble/`
- `authenticator/`

These files are copied as a rebuild baseline, not as a final package layout.

The original Cube-facing Django/UI paths have since been split out into the sibling repository `../cube-mumble`.

## Cube-Core Touchpoints Still In Cube

The following Cube-core paths still reference the in-tree Mumble implementation and will need to be redesigned or removed as extraction continues:

- `config/urls.py`
- `accounts/views.py`
- `accounts/middleware.py`
- `modules/onboarding/verification.py`
- `deploy/setup-hetzner.sh`
- `.github/workflows/deploy-dev.yml`

## Current Ownership In The Snapshot

The retained standalone snapshot now includes:

- the Django `mumble` runtime models and migrations
- ICE synchronization logic
- Murmur pulse runtime
- the standalone authenticator
- Murmur ICE slice data

The following Cube-coupled pieces were removed from this repo and moved to `../cube-mumble`:

- Mumble admin and profile UI
- Cube sidebar integration
- Celery tasks for Cube-driven group/display-name refresh
- the display-name backfill management command
- the legacy Django test module for those flows

## Rebuild Direction

The intended target is narrower than the copied code:

- `cube-core` and `cube-mumble` should keep Cube-side eligibility UI, user/admin actions, and status display
- `cube-monitor` should own server inventory, account provisioning, per-server identifiers, password application, and runtime state
- long-lived per-server Mumble auth state should not remain in Cube core

## Org Membership Semantics

- Pilot identity is `character_id`-stable, but corporation and alliance are mutable membership state.
- A pilot can move between corporations; a corporation can move between alliances.
- Alliance must therefore be refreshed from the latest character membership snapshot (or equivalent authoritative membership source), not treated as a fixed pilot attribute.
