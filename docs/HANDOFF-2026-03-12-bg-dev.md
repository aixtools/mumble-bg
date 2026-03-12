# Handoff: 2026-03-12 FG/BG (mumble-bg focus)

Date: 2026-03-12  (UTC reference)

This handoff supersedes `/home/michael/prj/repository/mumble-bg/history/HANDOFF-2026-03-11-bg-dev.md` for current session status.

## Summary
- BG control plane is in place for mutation endpoints and secret bootstrap/rotation flow.
- FG remains on standalone-first contract validation path; no host-specific Cube/AllianceAuth UI behavior required for now.
- New work completed in this session: **background pulse reconciliation framework** added to BG.
- No PR is required yet; current changes are committed locally for extension.

## Repos
- BG: `/home/michael/prj/mumble-bg` (branch `main`)
- FG: `/home/michael/prj/mumble-fg` (branch `main`)
- Historical handoff vault: `/home/michael/prj/repository/mumble-bg/history/`

## BG Current branch/status
- HEAD: `3874cd7`
- Message: `Add bg pulse registration reconciliation mode`
- Working tree: clean
- Merged branches: only `main` appears on merge list; no other local branches are merged.

## FG Current branch/status
- HEAD: `6889044` on `main`
- Working tree: clean

## Done

### 1) BG reconcile framework (new)
Commit added:
- `[3874cd7] Add bg pulse registration reconciliation mode`

Files:
- `bg/pulse/reconciler.py` (new)
- `bg/pulse/main.py`
- `bg/state/management/commands/run_murmur_pulse.py`
- `bg/state/management/commands/reconcile_murmur_users.py` (new)

Capabilities:
- Added OO reconciliation engine in `MurmurRegistrationReconciler`.
- Reconciler computes intended vs live registration diff for active `MumbleUser` entries per `MumbleServer`.
- Introduced:
  - `MurmurReconcilePlan`
  - `MurmurReconcileResult`
  - `MurmurDesiredAction`
  - `MurmurReconcileAction` (`create`/`delete`)
  - `MurmurReconcileError`
- Added Ice adapter abstraction:
  - `_MurmurServerAdapter` handles connection/disconnect and register/update/unregister operations.
- Added commands:
  - `manage.py run_murmur_pulse --reconcile`
  - `manage.py run_murmur_pulse --reconcile --json/--apply`
  - `manage.py reconcile_murmur_users [--apply] [--json] [--server-id N]`
- Default reconcile behavior is dry-run; `--apply` triggers mutations.
- Diff output includes dry-run/apply counts and per-server errors.

### 2) Control and contract work from earlier sessions still active in history
- BG control + PSK/secret/rotation endpoints and probe read enrichments are present and in service.
- FG and BG migration-related deploy reset logic has been added in previous commits.
- Deployment environment target config switched to JSON secret object style (host/user/key target name pattern), and BG now supports both env var and secret paths.

## To-Dos (tomorrow)

Priority: finalize `bg/pulse` integration path and begin FG call-through.

1. Expand reconciliation to include Murmur registration lifecycle semantics
   - Decide whether `registerUser` vs `updateRegistration` should happen for all creates with collisions.
   - Verify username collision handling and cert hash migration behavior.
2. Add robust unit/integration tests for reconcile path
   - Mockable adapter test for plan generation.
   - Dry-run and apply scenarios per server.
   - Failure path coverage (missing server config, ICE unavailable, duplicate names).
3. Add FG-facing pathway if/when required
- Decide whether FG should call `run_murmur_pulse --reconcile` directly or use a new FG endpoint wrapper later.
4. Standalone integration smoke run
   - Bring BG + FG up on local ports and run reconcile dry-run/apply on fixture data.
   - Validate no direct writes to ICE unless FG intent is explicit.
5. Operational hardening
   - Add clearer admin logging for reconcile failures.
   - Add explicit pre-flight validation command for ICE/virtual server selection.

## Learned / Discovered

- `MurmurRegistrationReconciler` currently ties to DB active state only; it does not yet branch on host context or fg-supplied server hints.
- The ICE adapter picks a virtual server only by:
  - configured `virtual_server_id`, or
  - auto-select if only one server is booted.
  Multi-server endpoints without `virtual_server_id` will fail early.
- Username matching in diffing uses casefolded, trimmed matching and may normalize collisions.
- `reconcile_murmur_users` and `run_murmur_pulse --reconcile` overlap behavior; only one may be needed long term.
- No end-to-end FG↔BG pulse test was completed in this round.
- No dedicated reconcile tests exist yet; only syntax/compile checks were done.

## Risks
- Unverified destructive behavior in apply mode on production-like data.
- ICE library availability / connectivity remains external dependency for any apply run.
- Delete actions are currently based solely on live registrations not present in local desired set.
  If Murmur has out-of-band registrations this logic is intentionally strict.
- No idempotent reconciliation transaction boundary across multiple server rows yet.

## Useful commands
- Compile check:
  - `source ~/.venv/codex/bin/activate && python -m py_compile bg/pulse/main.py bg/pulse/reconciler.py bg/state/management/commands/run_murmur_pulse.py bg/state/management/commands/reconcile_murmur_users.py`
- Dry-run reconcile:
  - `source ~/.venv/mumble-bg/bin/activate && python manage.py run_murmur_pulse --reconcile --json`
- Apply reconcile for one server (explicit):
  - `source ~/.venv/mumble-bg/bin/activate && python manage.py run_murmur_pulse --reconcile --apply --server-id 1`
- Alternate command path:
  - `source ~/.venv/mumble-bg/bin/activate && python manage.py reconcile_murmur_users --server-id 1 --json`

## Next-Session Decision Checklist
- Which merge direction first: continue adding FG integration against `main`, or finalize and test BG reconcile primitives first?
- Should reconciliation be exposed to operator scheduling (periodic job) or only manual FG-driven flow?
- For safety: confirm whether to keep deletion of stale registrations enabled by default.

## Contract reminder for tomorrow
- Keep FG and BG validation standalone-first.
- fg should not read bg DB directly.
- bg should remain authority for Murmur control mutations and control auth verification.
