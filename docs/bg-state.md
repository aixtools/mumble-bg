# bg.state

`bg.state` is the Django app that owns persisted `mumble-bg` state.

It is responsible for:

- Django app registration
- ORM models
- migrations
- Django management commands that operate on persisted state

Runtime behavior belongs elsewhere, primarily under `bg.authd`, `bg.pilot`,
and other service modules.

## What It Owns

On this branch, `bg.state` owns the tables behind `BG_DBMS`, including:

- `mumble_server`
- `mumble_user`
- `mumble_session`
- `bg_access_rule`
- `bg_access_rule_audit`
- `bg_pilot_account`
- `bg_pilot_character`
- `bg_pilot_snapshot_audit`
- `control_channel_key`
- `bg_audit`

That means `bg.state` now owns both:

- BG runtime/auth state
- cached FG pilot snapshot state used for eligibility/provision

## What Does Not Belong Here

These responsibilities should stay out of `bg.state`:

- auth daemon business logic
- control API request orchestration
- Murmur reconciliation logic
- FG-host adapter logic

The split is intentional:

- `bg.state` owns persisted `BG_DBMS` state
- service modules own runtime behavior

## Current Naming

`BG_DBMS` is the BG-owned database contract and current env/config name.
