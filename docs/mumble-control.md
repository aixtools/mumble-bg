# mumble_control

`mumble_control` is the explicit fg/bg control path between `mumble-fg` and
`mumble-bg`.

It exists to keep the boundary clean:

- no direct fg reads from the bg database
- no direct bg writes into host-owned tables
- no shared Python imports across repos as the long-term interface

## Test Contract (Standalone First)

Before integrating into any host product (Cube, AllianceAuth, or other), fg/bg
must be validated as a standalone pair.

Required testing order:

1. bring up bg HTTP endpoints directly
2. call bg control/probe endpoints with PSK over HTTP
3. point fg control client to standalone bg base URL
4. verify fg mutating flows route only through bg control endpoints and are
   validated by bg probe reads
5. only then wire fg into host URL/sidebar/panel surfaces

This rule prevents host routing/configuration issues from masking fg/bg contract
regressions.

Suggested local standalone run:

```bash
cd ~/git/mumble-bg
source ~/.venv/mumble-bg/bin/activate
python manage.py migrate --noinput
python manage.py runserver 127.0.0.1:18080
```

Then probe:

```bash
curl -sS http://127.0.0.1:18080/v1/health
curl -sS -H "X-Murmur-Control-PSK: <psk>" http://127.0.0.1:18080/v1/control-key/status
curl -sS -H "X-Murmur-Control-PSK: <psk>" http://127.0.0.1:18080/v1/servers
```

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
- `POST /v1/registrations/contract-sync`
- `POST /v1/registrations/disable`
- `POST /v1/admin-membership/sync`
- `POST /v1/control-key/bootstrap`
- `POST /v1/control-key/rotate`

Read/status endpoints:

- `GET /v1/health`
- `GET /v1/servers`
- `GET /v1/registrations`
- `GET /v1/pilots/{pkid}`
- `GET /v1/control-key/status`

Eligibility decision table endpoints:

- `POST /v1/access-rules/sync`
- `GET /v1/access-rules`

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

### `POST /v1/registrations/contract-sync`

Request payload:

```json
{
  "pkid": 12345,
  "server_name": "de primary",
  "evepilot_id": 90000001,
  "corporation_id": 98000001,
  "alliance_id": 99000001,
  "kdf_iterations": 120000,
  "is_super": true
}
```

Meaning:

- fg requests bg to persist registration contract metadata for one pilot/server row
- endpoint is superuser-gated (`is_super` required and must be true)
- accepts any subset of these fields: `evepilot_id`, `corporation_id`, `alliance_id`, `kdf_iterations`
- probe reads (`GET /v1/pilots/{pkid}`) are the source of truth for verification after updates

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
  "groups": "corp,alliance,admin",
  "session_ids": [11, 12, 13]
}
```

Meaning:

- fg asks bg to persist admin membership state for one pilot/server row.
- when `groups` is supplied, bg also persists the authd group string used for future logins.
- bg updates all listed active Murmur sessions immediately when possible.

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

### `GET /v1/registrations`

Returns bg-owned active registration rows across all pilots and servers for FG
operator views.

### `GET /v1/pilots/{pkid}`

Returns bg-side state for a pilot, for example:

- registration rows
- current Murmur mapping
- `registration_status`
- `admin_membership_state`
- `display_name`
- `evepilot_id`, `corporation_id`, `alliance_id`
- `hashfn`, `kdf_iterations`
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

## Pilot Eligibility Decision Tables

BG receives access-control decision tables from FG via the control channel and
independently provisions Mumble accounts by evaluating the pilot source against
these rules.

### Tables (received from FG, stored locally by BG)

- **Allowed alliances** — an alliance is either in or out. Unlisted alliances are implicitly denied.
- **Denied corps** — corps within an allowed alliance that are denied access.
- **Denied pilots** — individual pilots denied regardless of alliance/corp status.
- **Allowed pilots** — individual overrides that rescue access even when corp or alliance is denied.

### Precedence (most specific wins)

1. **Pilot allow/deny** overrides everything
2. **Corp deny** applies if no pilot-level override exists
3. **Alliance allow** is the baseline (unlisted alliances are implicitly denied)

A denied corp within an allowed alliance blocks that corp's members — but an
explicit pilot-level allow for a specific member of that corp restores their
access. This gives admins surgical control: allow an alliance, deny a
problematic corp, but still whitelist specific trusted pilots from that corp.

### Account-wide enforcement

Deny checks apply across the **entire account**, not just the main character.
If the main **or any alt** matches a deny rule (alliance, corp, or pilot), the
whole account is denied — unless a pilot-level allow overrides it.

### Ownership

- FG owns the decision tables (admin panel for submitting IDs)
- FG pushes decision tables to BG via control channel
- BG stores its own copy and autonomously provisions `bg_user` rows
- BG is self-sufficient for provisioning once it has the rules

### `POST /v1/access-rules/sync`

Request payload:

```json
{
  "is_super": true,
  "rules": [
    {"entity_id": 99000001, "entity_type": "alliance", "deny": false, "note": "Main alliance"},
    {"entity_id": 98000001, "entity_type": "corporation", "deny": true, "note": "Problematic corp"},
    {"entity_id": 90000001, "entity_type": "pilot", "deny": false, "note": "Trusted pilot in denied corp"}
  ]
}
```

Meaning:

- FG pushes the full eligibility decision table to BG
- this is a full-table sync: rules not in the payload are deleted from BG
- superuser-gated (`is_super` required)
- TODO: when BG-side sync auditing is added, append a sync audit record only if
  the incoming rule set actually changes BG state

### `GET /v1/access-rules`

Returns the current access rule set stored in BG.

## What Not To Do

- do not make fg read bg tables directly
- do not make bg poll fg tables directly
- do not use ad hoc shell commands as the long-term control surface
- do not bind the first version to one product name such as Cube or AllianceAuth
