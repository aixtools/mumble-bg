# FG/BG Troubleshooting Checklist and FAQ

This guide is for debugging runtime integration issues between `mumble-fg` (in Cube) and `mumble-bg`.

## Quick Checklist

Run these in order before deeper debugging:

1. Verify BG health and runtime checks:
   - `python manage.py install_assistant`
   - `python manage.py list_ice_users`
   - `curl -sS http://127.0.0.1:18080/v1/health | python3 -m json.tool`

2. Verify BG control/authd are running:
   - `ps -ef | rg 'bg.authd|bg.control_main'`
   - `ss -ltn | rg 18080`
   - Check logs:
     - `/tmp/mumble-bg-authd-debug-0320.log`
     - `/tmp/mumble-bg-control-debug-0320.log`

3. Verify Cube/FG env has required control variables:
   - `rg -n '^(OPTIONAL_APPS|MURMUR_CONTROL_URL|FGBG_PSK|MURMUR_CONTROL_PSK)=' /home/cube/Cube/.env`
   - `OPTIONAL_APPS` must include `mumble_ui.apps.MumbleUiConfig`.
   - `MURMUR_CONTROL_URL` must point to BG control endpoint.
   - `FGBG_PSK` must match BG.

4. Verify BG env has matching control secret:
   - `rg -n '^(MURMUR_CONTROL_URL|FGBG_PSK|MURMUR_CONTROL_PSK|DJANGO_SETTINGS_MODULE)=' ~/.env/mumble-bg`

5. Run explicit FG-to-BG ACL sync diagnostic from Cube:
   - `python manage.py sync_mumble_acl --traceback`

6. Correlate request path:
   - If ACL sync fails but BG control log has no request, Cube likely never reached BG (bad URL, service down, network path).
   - If BG logs request and rejects it, check PSK/auth mismatch and payload errors.

## Incident Walkthrough: ACL Sync Failed

This is the exact failure chain we observed and how each step fixed it.

1. Symptom from Cube:
   - `python manage.py sync_mumble_acl --traceback`
   - Error: `Control request failed (400): Bad Request`

2. BG control log had no matching request:
   - Meaning FG/Cube was not calling the intended BG endpoint.

3. Root cause #1: wrong FG fallback URL.
   - FG was defaulting to `http://127.0.0.1:8000`.
   - Fix:
     - Set Cube env: `MURMUR_CONTROL_URL=http://127.0.0.1:18080`
     - Update FG fallback default to `http://127.0.0.1:18080` in `fg/control.py`.

4. Next symptom:
   - Error changed to `Control endpoint unreachable: [Errno 111] Connection refused`
   - Meaning URL was now correct, but BG control was down.

5. Root cause #2: BG control process not running.
   - Fix:
     - Start BG control and verify listener on `127.0.0.1:18080`.

6. Next symptom:
   - Error changed to `500 Internal Server Error`.
   - BG traceback showed:
     - `relation "bg_access_rule_audit" does not exist`

7. Root cause #3: schema drift (migration recorded as applied, table missing).
   - `state.0000_initial` was marked `[X]`, but `bg_access_rule_audit` table did not exist.
   - Fix:
     - Create missing table via Django schema editor (`AccessRuleSyncAudit`) as one-off DB repair.
     - No migration file is created by this repair step.

8. Final validation:
   - Re-run:
     - `python manage.py sync_mumble_acl --traceback`
   - Success:
     - `ACL synchronized to BG (...)`

## FAQ

### Q: ACL sync fails, but BG logs show nothing. Why?

Most likely Cube cannot reach BG control at all.

Typical causes:
- `MURMUR_CONTROL_URL` missing in Cube env.
- `MURMUR_CONTROL_URL` points to wrong host/port.
- BG control process is not running.

Useful checks:
- `python manage.py sync_mumble_acl --traceback` (from Cube)
- `curl -sS "$MURMUR_CONTROL_URL/v1/health"` (from Cube host/shell)

### Q: ACL sync returns 500 with `relation "bg_access_rule_audit" does not exist`. Why?

This is DB schema drift: Django migration state says applied, but the physical table is missing.

Why this breaks ACL sync:
- BG writes an ACL sync audit row during `/v1/access-rules/sync`.
- Missing `bg_access_rule_audit` causes server-side `ProgrammingError`, returning HTTP 500.

Recovery:
- Confirm mismatch:
  - `python manage.py showmigrations state`
  - Inspect tables in DB (or via `manage.py shell`) and verify `bg_access_rule_audit` is missing.
- Repair:
  - Create the missing model table once with Django schema editor for `AccessRuleSyncAudit`.
- Re-run:
  - `python manage.py sync_mumble_acl --traceback`

### Q: ACL sync reaches BG but fails auth. Why?

Usually shared secret mismatch:
- `FGBG_PSK` in Cube does not exactly match BG `FGBG_PSK`.

Check both files directly and compare exact values (including quoting/whitespace handling):
- `/home/cube/Cube/.env`
- `~/.env/mumble-bg`

### Q: `install_assistant` is OK, but UI sync still fails. What next?

`install_assistant` validates BG-side readiness. UI sync also depends on Cube/FG env and network path.

Run:
- BG side: `python manage.py install_assistant`
- Cube side: `python manage.py sync_mumble_acl --traceback`
- Then compare BG control log timestamps around the sync attempt.

### Q: Cube fails at startup with `ModuleNotFoundError: mumble_ui`.

FG wheel is not installed in Cube's active venv (or `OPTIONAL_APPS` is misconfigured).

Fix:
- Install the `mumble-fg` wheel into the same venv used by Cube service/runserver.
- Ensure `OPTIONAL_APPS` includes `mumble_ui.apps.MumbleUiConfig`.

### Q: Which command is best for fast ACL sync diagnosis?

`python manage.py sync_mumble_acl --traceback` from Cube.

Why:
- It bypasses UI and directly executes the FG-to-BG control call.
- It surfaces actionable stack traces and request failures quickly.

## Minimal Incident Capture

When reporting an integration issue, include:
- Output of `python manage.py install_assistant`
- Output of `python manage.py sync_mumble_acl --traceback`
- BG logs around the failure window:
  - `/tmp/mumble-bg-control-debug-0320.log`
  - `/tmp/mumble-bg-authd-debug-0320.log`
- Relevant env lines from:
  - `/home/cube/Cube/.env`
  - `~/.env/mumble-bg`
