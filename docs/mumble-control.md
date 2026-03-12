# mumble_control

`mumble_control` is the explicit fg/bg control path between `mumble-fg` and
`mumble-bg`.

It exists to keep the boundary clean:

- no direct fg reads from the bg database
- no direct bg writes into host-owned tables
- no shared Python imports across repos as the long-term interface

## Recommended Transport

Current recommendation:

- HTTP + JSON
- served by `mumble-bg`
- bound to a Unix domain socket when fg and bg live on the same host

Reasoning:

- simple request/response model
- easy to call from Django views, admin actions, and tasks
- easy to secure later without changing the request schema
- avoids introducing a queue or service mesh too early

If a Unix socket is not practical at first, use:

- HTTP + JSON on `127.0.0.1`

That is acceptable as a temporary insecure mode for local dev only.

## Security Phases

Current implementation:

- write endpoints accept a control PSK via `X-Murmur-Control-PSK`
  (or `Authorization: Bearer <psk>`)
- bg resolves active PSK from:
  - DB key (`control_channel_key.shared_secret`) when set
  - otherwise `MURMUR_CONTROL_PSK` env fallback
- if neither exists, bg is in `open` mode (local bootstrap/dev only)

## Request Shape

Every write/control request should carry:

- `request_id`
- `requested_by`
- `is_super` (required for control-key lifecycle endpoints)
- `timestamp`
- command-specific payload

Suggested common envelope:

```json
{
  "request_id": "3a6ef9e4-63db-4f47-8101-ef1db3a44c06",
  "requested_by": "admin:michael",
  "timestamp": "2026-03-11T15:30:00Z",
  "payload": {}
}
```

Suggested common response:

```json
{
  "request_id": "3a6ef9e4-63db-4f47-8101-ef1db3a44c06",
  "status": "accepted",
  "message": "queued password reset for pkid 12345"
}
```

Response `status` values should be:

- `accepted`
- `completed`
- `rejected`
- `not_found`
- `failed`

## Initial Endpoints

Write/control endpoints:

- `POST /v1/password-reset`
- `POST /v1/registrations/sync`
- `POST /v1/registrations/disable`
- `POST /v1/admin-membership/sync`
- `POST /v1/control-key/bootstrap`
- `POST /v1/control-key/rotate`

Read/status endpoints:

- `GET /v1/health`
- `GET /v1/servers`
- `GET /v1/pilots/{pkid}`
- `GET /v1/control-key/status`

These are intentionally narrow. Add endpoints only when fg has a real caller.

## Endpoint Payloads

### `POST /v1/password-reset`

Request payload:

```json
{
  "pkid": 12345,
  "server_name": "de primary"
}
```

Meaning:

- fg requests that bg generate/reset local auth state for one pilot
- bg performs the mutation in its own database and returns status
- when fg supplies a password, bg accepts printable 7-bit ASCII only and rejects `'`, `"`, `` ` ``, and `\`

### `POST /v1/registrations/sync`

Request payload:

```json
{
  "pkid": 12345,
  "server_name": "de primary",
  "dry_run": false
}
```

Meaning:

- fg asks bg to reconcile one pilot registration into Murmur
- bg decides create/adopt/update behavior

### `POST /v1/registrations/disable`

Request payload:

```json
{
  "pkid": 12345,
  "server_name": "de primary"
}
```

Meaning:

- fg asks bg to disable or unregister one pilot on one server

### `POST /v1/admin-membership/sync`

Request payload:

```json
{
  "pkid": 12345,
  "server_name": "de primary",
  "admin": true,
  "session_ids": [11, 12, 13]
}
```

Meaning:

- fg asks bg to add/remove admin group membership for all listed active Murmur sessions.

The same `server_name`/`pkid` selector style is used as registration sync.

`synced_sessions` returns how many session IDs were processed.

### CLI-only control-key reset

There is intentionally no HTTP endpoint for control-key reset.

Use the CLI command instead:

```bash
python manage.py reset_murmur_control_key --yes
```

Meaning:

- resets fg/bg control PSK in DB back to `NULL`
- once DB PSK is `NULL`, auth falls back to `MURMUR_CONTROL_PSK` env (or `open` mode)

### `POST /v1/control-key/bootstrap`

Request payload:

```json
{
  "new_control_psk": "at-least-16-characters",
  "is_super": true
}
```

Meaning:

- creates first DB control PSK when none exists

### `POST /v1/control-key/rotate`

Request payload:

```json
{
  "new_control_psk": "at-least-16-characters",
  "is_super": true
}
```

Meaning:

- rotates the DB control PSK to a new value

### `GET /v1/health`

Returns:

- process health
- bg DB reachability
- control mode (`db`, `env`, `open`)

### `GET /v1/servers`

Returns bg-owned server inventory and current daemon view of those servers.

### `GET /v1/pilots/{pkid}`

Returns bg-side state for a pilot, for example:

- registration rows
- current Murmur mapping
- `registration_status`
- `admin_membership_state`
- `active_session_ids` and `active_session_count`
- `pw_lastchanged` read from the registration row timestamp
- last auth time
- last seen / last spoke if available

### `GET /v1/control-key/status`

Returns:

- whether DB control key exists
- current mode (`db`, `env`, `open`)
- last update timestamp (if DB key row exists)

## Naming Notes

- Prefer `pkid` as the stable pilot identifier in request payloads.
- `server_name` is acceptable as a transitional selector.
- Long term, fg and bg should share a stable server identifier that is not just
  display text.

## What Not To Do

- do not make fg read bg tables directly
- do not make bg poll fg tables directly
- do not use ad hoc shell commands as the long-term control surface
- do not bind the first version to one product name such as Cube or AllianceAuth
