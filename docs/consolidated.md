# mumble-bg Consolidated Documentation

This document is the active, consolidated operating document for the `mumble-bg` repository. It replaces the topic docs now archived in
[history/mumble-bg](../../repository/history/mumble-bg).

## Purpose and Scope

- `mumble-bg` owns runtime authentication/authz daemon behavior, Murmur API/probe flows, and reconciliation tasks.
- BG should remain a separate service from host apps.
- No shared host write-path assumptions; contracts are API-oriented.

## Runtime Boundaries

- Private BG runtime DB for state, keys, users, and session data.
- Host-facing FG should interact via control/probe endpoints.
- Murmur process integration is intentionally separated from host/admin UI concerns.

## Deployment and Operations

- Use [workflow-deploy.md](./workflow-deploy.md) for the current deploy/bootstrap flow.
- Archive deploy/playbook docs remain historical reference only.
- Confirm service startup, DB migration, and control channel secrets are aligned before running operator actions.
- Treat direct DB access from host as invalid; host integrations should use contract endpoints.

## Documentation Layout

- [consolidated.md](./consolidated.md) is canonical.
- [workflow-deploy.md](./workflow-deploy.md) covers current deploy/bootstrap workflow.
- [system-boundary.md](./system-boundary.md), [bg-state.md](./bg-state.md), [mumble-control.md](./mumble-control.md), and [extraction-inventory.md](./extraction-inventory.md) remain active companion docs.
- [history/mumble-bg](../../repository/history/mumble-bg) stores historical docs.

## Archive

- [history/mumble-bg/HANDOFF-2026-03-12-bg-dev.md](../../repository/history/mumble-bg/HANDOFF-2026-03-12-bg-dev.md)
- [history/mumble-bg/bg-state.md](../../repository/history/mumble-bg/bg-state.md)
- [history/mumble-bg/bootstrap-dev-deploy.md](../../repository/history/mumble-bg/bootstrap-dev-deploy.md)
- [history/mumble-bg/database-bootstrap.md](../../repository/history/mumble-bg/database-bootstrap.md)
- [history/mumble-bg/deploy-inventory.md](../../repository/history/mumble-bg/deploy-inventory.md)
- [history/mumble-bg/extraction-inventory.md](../../repository/history/mumble-bg/extraction-inventory.md)
- [history/mumble-bg/mumble-control.md](../../repository/history/mumble-bg/mumble-control.md)
- [history/mumble-bg/murmur-probe.md](../../repository/history/mumble-bg/murmur-probe.md)
- [history/mumble-bg/system-boundary.md](../../repository/history/mumble-bg/system-boundary.md)
- [repository/mumble-bg/docs/HANDOFF-2026-03-12-done-todo-learned.md](../../repository/mumble-bg/docs/HANDOFF-2026-03-12-done-todo-learned.md)
- [repository/mumble-bg/history/HANDOFF-2026-03-11-bg-dev.md](../../repository/mumble-bg/history/HANDOFF-2026-03-11-bg-dev.md)
- [repository/mumble-bg/history/HANDOFF-2026-03-11-bg-entrypoints.md](../../repository/mumble-bg/history/HANDOFF-2026-03-11-bg-entrypoints.md)
- [repository/mumble-bg/history/HANDOFF-2026-03-11.md](../../repository/mumble-bg/history/HANDOFF-2026-03-11.md)
- [repository/mumble-bg/history/HANDOFF-2026-03-12-bg-dev.md](../../repository/mumble-bg/history/HANDOFF-2026-03-12-bg-dev.md)
- [repository/mumble-bg/history/pilot-mumble-tables-renamed-2026-03-11.sql](../../repository/mumble-bg/history/pilot-mumble-tables-renamed-2026-03-11.sql)
- [repository/mumble-bg/history/pilot-mumble_mumble-tables-2026-03-11.sql](../../repository/mumble-bg/history/pilot-mumble_mumble-tables-2026-03-11.sql)
- [repository/mumble-bg/history/runtime-blocker-2026-03-10.md](../../repository/mumble-bg/history/runtime-blocker-2026-03-10.md)
