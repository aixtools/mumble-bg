# Extraction Inventory

Source snapshot:

- repo: `cube`
- branch: `cube-newmumble-upstream`
- commit: `2869fbc8ada6010d8823f50caf52d3b1779a30a7`

Copied into this repository:

- `modules/mumble/`
- `authenticator/`
- `templates/mumble/`

These files are copied as a rebuild baseline, not as a final package layout.

## Cube-Core Touchpoints Still In Cube

The following Cube-core paths still reference the in-tree Mumble implementation and will need to be redesigned or removed as extraction continues:

- `config/urls.py`
- `accounts/views.py`
- `accounts/middleware.py`
- `modules/onboarding/verification.py`
- `deploy/setup-hetzner.sh`
- `.github/workflows/deploy-dev.yml`

## Current Ownership In The Snapshot

The copied snapshot includes:

- the Django `mumble` app
- Mumble admin and profile UI
- ICE synchronization logic
- Murmur pulse runtime
- the standalone authenticator
- Murmur ICE slice data

## Rebuild Direction

The intended target is narrower than the copied code:

- `cube-core` should keep only Cube-side eligibility UI, user/admin actions, and status display
- `cube-monitor` should own server inventory, account provisioning, per-server identifiers, password application, and runtime state
- long-lived per-server Mumble auth state should not remain in Cube core

## Org Membership Semantics

- Pilot identity is `character_id`-stable, but corporation and alliance are mutable membership state.
- A pilot can move between corporations; a corporation can move between alliances.
- Alliance must therefore be refreshed from the latest character membership snapshot (or equivalent authoritative membership source), not treated as a fixed pilot attribute.
