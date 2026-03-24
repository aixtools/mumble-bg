# HTTP Surface Review

This document is a preparation note for later hardening.

It answers two questions:

- which BG URLs currently expose information when called directly
- whether FG exposes any API-like URLs

## 1. BG Surface

BG currently exposes two kinds of HTTP endpoints:

- unauthenticated GET endpoints
- control-authenticated POST endpoints

The POST endpoints use the shared control secret.
The GET endpoints do not currently require that secret.

## 2. BG Unauthenticated GET Endpoints

### Low sensitivity

- `GET /`
  Returns plain `ok`.
- `GET /v1/health`
  Returns BG status, DB reachability, control mode, and crypto readiness.
- `GET /v1/public-key`
  Returns BG's public key when configured.

### Medium sensitivity

- `GET /v1/control-key/status`
  Reveals whether control auth is in `open`, `env`, or `db` mode, plus key timestamps.
- `GET /v1/eve-objects`
  Returns BG's cached EVE object dictionary rows:
  ids, names, tickers, categories, sync times.

### High sensitivity

- `GET /v1/servers`
  Returns server inventory including user-visible address, ICE host, ICE port, and virtual server id.
- `GET /v1/access-rules`
  Returns ACL rules including deny/admin flags, notes, `created_by`, and sync timestamps.
- `GET /v1/registrations`
  Returns all active BG registration snapshots.
  This includes `pkid`, username, display name, Murmur user id, corp/alliance ids, admin flag, active session ids, and activity timestamps.
- `GET /v1/pilot/<pkid>`
- `GET /v1/pilots/<pkid>`
  Returns the same registration snapshot data, but scoped to one `pkid`.

## 3. BG Control-Authenticated POST Endpoints

These require the BG control secret in a request header or bearer token.

- `POST /v1/registrations/sync`
- `POST /v1/registrations/contract-sync`
- `POST /v1/registrations/disable`
- `POST /v1/admin-membership/sync`
- `POST /v1/password-reset`
- `POST /v1/control-key/bootstrap`
- `POST /v1/control-key/rotate`
- `POST /v1/access-rules/sync`
- `POST /v1/eve-objects/sync`
- `POST /v1/pilot-snapshot/sync`
- `POST /v1/provision`

These are the intended FG-to-BG mutation surface.

## 4. Likely Later Hardening Targets

If BG surface reduction is done later, the first candidates are:

1. protect `GET /v1/registrations`
2. protect `GET /v1/pilot/<pkid>`
3. protect `GET /v1/access-rules`
4. protect `GET /v1/servers`
5. reconsider how much detail `GET /v1/control-key/status` should expose

`GET /v1/health` and `GET /v1/public-key` are the easiest to justify as open.

## 5. Does FG Have Any API URLs?

FG does not expose a standalone control API comparable to BG.

FG is mounted as host UI under:

- `/mumble-ui/`

Within that mount, some views are API-like because they return JSON for AJAX or panel actions, but they are still host UI endpoints, not a separate service API.

### FG JSON-returning endpoints

- `POST /mumble-ui/profile/reset-password/`
- `POST /mumble-ui/profile/set-password/`
- `GET /mumble-ui/acl/search/`
- `POST /mumble-ui/acl/batch-create/`
- `GET /mumble-ui/acl/eligible/`
- `GET /mumble-ui/acl/blocked/`
- `POST /mumble-ui/acl/sync/`

Some server-specific mutation views may also return JSON in AJAX flows:

- `POST /mumble-ui/<server_id>/set-password/`

## 6. FG Exposure Model

FG differs from BG in an important way:

- FG URLs are host-session endpoints
- FG views are under Django login control
- FG mutation views are POST-only
- FG ACL views additionally require host permissions
- FG is not intended to be called directly by third-party clients

So the current concern is mainly BG, not FG.

## 7. Practical Conclusion

Current direct-call information exposure is mostly on BG GET endpoints.

FG does have JSON-returning URLs, but they are UI endpoints behind host authentication and authorization, not a public control API.
