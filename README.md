# mumble-bg

`mumble-bg` is the runtime/control side of the FG/BG split.

It owns:

- BG runtime state in `BG_DBMS`
- Murmur registration and reconciliation
- ICE integration
- authd behavior
- cached FG pilot snapshot data
- control endpoints used by FG

It does not read host pilot/core tables directly.

## Canonical Documents

- [docs/design_spec.md](./docs/design_spec.md)
- [docs/deploy_manual.md](./docs/deploy_manual.md)
- [docs/deploy_workflow.md](./docs/deploy_workflow.md)

Treat the three documents above as authoritative for current BG behavior.

## Runtime Summary

- BG receives ACL and pilot snapshot state from FG.
- BG provisions and reconciles Mumble users from those cached inputs.
- BG is the source of truth for runtime password material and Murmur-side user state.
- BG can run as a standalone Django-backed service with separate control and authd processes.

Optional helper scripts remain under `installation/scripts/`.

## Commit Message Pre-check

Conventional Commits are enforced for new commits.

```bash
make precheck COMMIT_MSG="feat(bg): add pilot hash sync response"
git config core.hooksPath .githooks
```
