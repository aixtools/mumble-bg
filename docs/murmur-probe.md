# Murmur Probe Draft

This note defines the intended object model for optional read-only access to the Murmur server database.

The Murmur database is not part of normal `mumble-bg` operation.

Normal mode:

- `authd` talks to Murmur only via ICE
- `pulse` talks to Murmur only via ICE
- no Murmur DB reads are required
- no Murmur DB writes are allowed

Debug / verification mode:

- `mumble-bg` may read the Murmur DB to confirm that ICE actions had the expected effect
- Murmur DB access is optional
- missing or unavailable Murmur DB must never block `authd` or `pulse`

## Required vs Optional Data Sources

- `cube-core` DB
  - required
  - read-only
  - startup-blocking if unavailable

- `mumble-bg` DB
  - required
  - read/write
  - startup-blocking if unavailable

- Murmur DB
  - optional
  - read-only
  - never startup-blocking

## Object Model

Use a separate probe interface instead of treating the Murmur DB as a third normal application database.

Core types:

- `ProbeStatus`
  - `verified`
  - `mismatch`
  - `did_not_operate`
  - `error`

- `ProbeResult`
  - `status: ProbeStatus`
  - `target: str`
  - `reason: str`
  - `details: dict[str, object]`

- `MurmurProbe`
  - abstract interface for verification-only reads

- `NullMurmurProbe`
  - returned when Murmur DB config is absent, disabled, or unavailable
  - never raises for expected "not configured" situations
  - always returns `did_not_operate`

- `SqlMurmurProbe`
  - concrete read-only probe using Murmur's backing database
  - may have engine-specific implementations if needed:
    - `PostgresMurmurProbe`
    - `MySqlMurmurProbe`

## Interface Sketch

Suggested shape:

```python
from dataclasses import dataclass, field
from enum import StrEnum


class ProbeStatus(StrEnum):
    VERIFIED = "verified"
    MISMATCH = "mismatch"
    DID_NOT_OPERATE = "did_not_operate"
    ERROR = "error"


@dataclass(frozen=True)
class ProbeResult:
    status: ProbeStatus
    target: str
    reason: str = ""
    details: dict[str, object] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status is ProbeStatus.VERIFIED

    @property
    def non_blocking(self) -> bool:
        return self.status in {ProbeStatus.VERIFIED, ProbeStatus.DID_NOT_OPERATE}


class MurmurProbe:
    def verify_registration(self, *, server_id: int, username: str, mumble_userid: int | None) -> ProbeResult:
        raise NotImplementedError

    def verify_unregister(self, *, server_id: int, username: str, mumble_userid: int | None) -> ProbeResult:
        raise NotImplementedError

    def verify_session(self, *, server_id: int, session_id: int, username: str | None = None) -> ProbeResult:
        raise NotImplementedError

    def verify_admin_membership(self, *, server_id: int, session_id: int, expected_is_admin: bool) -> ProbeResult:
        raise NotImplementedError
```

The methods should be narrow and explicit. This is a verifier, not a second operational backend.

## Expected Behavior

`NullMurmurProbe`:

- if Murmur DB env is missing
- or feature flag disables probe mode
- or debug mode is off
- returns:
  - `ProbeResult(status="did_not_operate", reason="murmur probe not configured")`

`SqlMurmurProbe`:

- performs read-only queries
- if data matches expectations:
  - returns `verified`
- if query succeeds but state does not match:
  - returns `mismatch`
- if query fails unexpectedly:
  - returns `error`

Important rule:

- `mismatch` and `error` are diagnostic results
- they do not directly break normal auth or pulse flows
- they are for logs, admin views, and operator debugging

## Call Pattern

Normal service logic should look like this:

```python
result = murmur_probe.verify_registration(
    server_id=server_id,
    username=username,
    mumble_userid=mumble_userid,
)

if result.status == ProbeStatus.MISMATCH:
    logger.warning("murmur probe mismatch: %s", result)
elif result.status == ProbeStatus.ERROR:
    logger.warning("murmur probe error: %s", result)
```

Not like this:

```python
result = murmur_probe.verify_registration(...)
if not result.ok:
    raise RuntimeError("stop authd")
```

The Murmur probe must remain non-blocking.

## Placement

Recommended package layout:

- `bg/probe/__init__.py`
- `bg/probe/base.py`
- `bg/probe/null.py`
- `bg/probe/murmur_sql.py`

If the implementation stays small, a single module is also acceptable:

- `bg/probe.py`

I would not put this in `bg/db.py`, because:

- it is not part of the required DB layer
- it has different failure semantics
- it is verification-oriented, not operational

## Configuration

Recommended approach:

- normal operation requires no Murmur DB probe secret at all
- probe mode turns on only if optional `MURMUR_PROBE` data is present
- ICE connectivity itself is described separately by `ICE`

Suggested secret shape for `MURMUR_PROBE`:

```json
[
  {
    "name": "optional label",
    "host": "127.0.0.1",
    "username": "mumble",
    "database": "mumble_db",
    "password": "secret",
    "dbport": 5432,
    "dbengine": "postgres"
  }
]
```

Required per probe target:

- `host`
- `username`
- `database`
- `password`

Optional per probe target:

- `name`
- `dbport`
- `dbengine`

If `name` is omitted:

- default it to `host`

If `MURMUR_PROBE` is absent:

- instantiate `NullMurmurProbe`

## What To Verify

Good probe targets:

- registration exists after ICE registration/update
- registration disappears after ICE unregister
- expected Murmur user id is present
- live session row appears or disappears as expected
- admin group membership reflects expected state

Bad probe targets:

- anything required for normal authentication decisions
- anything that would make `authd` refuse valid users just because probe mode is unavailable

## Recommended Next Step

Implement the interface first with only:

- `ProbeStatus`
- `ProbeResult`
- `MurmurProbe`
- `NullMurmurProbe`

Then wire callers to accept a probe object and ignore `did_not_operate`.

Only after that should the SQL-backed Murmur probe be added.
