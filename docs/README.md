# mumble-bg Documentation

This directory is the canonical documentation location for this repository.

Primary reference:

- [consolidated.md](./consolidated.md) — current runtime, deployment, and integration notes.
- [workflow-deploy.md](./workflow-deploy.md) — one-time bootstrap and routine GitHub Actions deploy flow.
- [system-boundary.md](./system-boundary.md) — current FG/BG boundary and DB ownership rules.
- [bg-state.md](./bg-state.md) — persisted state owned by `bg.state` and `BG_DBMS`.
- [mumble-control.md](./mumble-control.md) — explicit FG -> BG control path and endpoint surface.
- [extraction-inventory.md](./extraction-inventory.md) — extraction baseline and current repo ownership split.
- [fg-bg-contracts.md](./fg-bg-contracts.md) — explicit and implicit FG/BG interaction contracts.
- [fg-bg-troubleshooting.md](./fg-bg-troubleshooting.md) — operator checklist and FAQ for FG/BG runtime debugging.

Historical documents are archived in:

- [history/mumble-bg](../../repository/history/mumble-bg)

Keep `consolidated.md` current, use the topic docs above for stable detail, and
treat all files under `history/` as historical reference.
