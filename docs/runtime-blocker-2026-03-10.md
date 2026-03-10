# Runtime Blocker: March 10, 2026

Current branch state reaches the real cube-core database and gets past deploy/bootstrap issues.

Current runtime blocker:

- `authenticator/authenticator.py` fails in `get_active_servers()`
- PostgreSQL error: `psycopg2.errors.UndefinedColumn`
- failing column: `mumble_mumbleserver.virtual_server_id`

Observed query shape:

```sql
SELECT id, ice_host, ice_port, ice_secret, virtual_server_id
FROM mumble_mumbleserver
WHERE is_active = true
```

Implication:

- the target database schema does not match the current extracted code
- likely causes are:
  - the expected migration for `virtual_server_id` has not been applied
  - or the runtime is pointed at an older schema snapshot

What was already fixed before hitting this blocker:

- deploy and undeploy scripts
- systemd unit generation from the invoking checkout
- ICE slice loading
- MySQL client support and DB adapter alignment with `../monitor`
- adapter tests in `tests/test_database_adapters.py` pass under `~/.venv/codex`
