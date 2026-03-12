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

That is acceptable as a temporary insecure mode as long as the contract stays
the same and authentication can be added later.

## Security Phases

Phase 1:

- Unix socket only, protected by filesystem permissions
- or `127.0.0.1` only, with no auth yet

Phase 2:

- add a shared secret or HMAC signature header

Phase 3:

- if fg and bg become remote, keep the same API and move to HTTPS with mTLS or
  signed service credentials

The important rule is that the transport may evolve, but the command contract
should stay stable.

## Request Shape

Every write/control request should carry:

- `request_id`
- `requested_by`
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
- `POST /v1/pulse/reconcile`
- `POST /v1/psk/reset`

Read/status endpoints:

- `GET /v1/health`
- `GET /v1/servers`
- `GET /v1/pilots/{pkid}`

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

### `POST /v1/pulse/reconcile`

Request payload:

```json
{
  "server_name": "de primary",
  "once": true
}
```

Meaning:

- fg asks bg to run a one-shot pulse reconciliation pass

### `POST /v1/psk/reset`

Request payload:

```json
{
  "server_name": "de primary"
}
```

Meaning:

- fg requests that bg clears the stored ICE secret (`ice_secret`) for the selected server so next
  startup can fall back to environment/default key material.

### `GET /v1/health`

Returns:

- process health
- bg DB reachability
- pilot DB reachability
- optional probe availability

### `GET /v1/servers`

Returns bg-owned server inventory and current daemon view of those servers.

### `GET /v1/pilots/{pkid}`

Returns bg-side state for a pilot, for example:

- registration rows
- current Murmur mapping
- `pw_lastchanged` read from the registration row timestamp
- last auth time
- last seen / last spoke if available

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
