# bg.state

`bg.state` is the Django app that owns mumble-bg's persisted model layer.

It exists for three things only:

- Django app registration
- ORM models
- migrations and `manage.py` command wrappers

It is not where daemon business logic should live. That logic belongs under
`bg.authd`, `bg.pulse`, and `bg.pilot`.

## Why `bg.state`

The old extraction used `modules.mumble`, then temporarily kept the Django app
label as `mumble` during the move. Since this is now a fresh-start application,
we dropped that compatibility label.

Current app identity:

- Python path: `bg.state`
- Django app label: `state`

Reasoning:

- `state` describes what this app owns: persisted background state.
- It avoids carrying the old extraction name forward.
- It keeps daemon logic and ORM logic clearly separated.

## What Lives Here

- `bg/state/apps.py`
- `bg/state/models.py`
- `bg/state/migrations/`
- `bg/state/management/commands/`

Those command modules stay here only because Django discovers `manage.py`
commands through installed apps.

## Reverse Relation Names

The reverse relation names in `bg/state/models.py` are intentionally domain
names, not extraction leftovers:

- `User -> MumbleUser`: `mumble_registrations`
- `MumbleServer -> MumbleUser`: `mumble_registrations`
- `MumbleServer -> MumbleSession`: `murmur_sessions`
- `MumbleUser -> MumbleSession`: `murmur_sessions`

Reasoning:

- `mumble_registrations` says what the rows are, instead of generic names like
  `accounts`.
- `murmur_sessions` says these are live/history Murmur session rows, not a vague
  `presence_sessions` bucket.
- The names match the domain model we actually want to maintain going forward,
  rather than the names inherited from the original extraction.

## What Does Not Belong Here

These were intentionally moved out of `bg.state`:

- auth daemon implementation -> `bg.authd.service`
- pulse implementation -> `bg.pulse.service`
- pilot registration sync -> `bg.pilot.registrations`

That split is intentional:

- `bg.state` owns persisted state
- other `bg.*` packages own runtime behavior
