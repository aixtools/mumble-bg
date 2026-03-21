# Installation Materials

Canonical sequence is in `installation/installation.md`.
Troubleshooting checklist/FAQ is in `docs/fg-bg-troubleshooting.md`.

Preferred install/ops flow is wheel-first with Django management commands:
- `python -m django init_bg_env`
- `python -m django shell_export KEY VALUE...`
- `python -m django install_assistant`
- `python -m django list_ice_users`
- `python -m django print_systemd_bg_control --env-file ~/.env/mumble-bg`
- `python -m django print_systemd_bg_authd --env-file ~/.env/mumble-bg`

Terminology note: `BG_DBMS` is the owned BG database contract and current env
variable name. Legacy `DATABASES` values are still accepted as a compatibility
fallback.

JSON env note: if a value must contain a literal apostrophe, encode it as `\\u0027` in JSON. Example: `"'MyPrettyS3rcet'"` should be `"\\u0027MyPrettyS3rcet\\u0027"`.
ICE note: `address` without `:port` means default Mumble client port `64738`; use `address:port` to override it. `name` is the FG/profile title and defaults to `address`.

Optional source-checkout helper wrappers are in `installation/scripts/`:

- `bg_preflight.sh` - validates BG config, checks, and migration state
- `bg_runtime_verify.sh` - validates BG runtime endpoints and ICE user listing
- `fg_env_check.sh` - validates FG-side control env variables in the Cube shell
- `init_bg_env.sh` - creates `~/.env/mumble-bg` from a complete first-time template
- `shell_export.sh` - prints shell-safe `export KEY='value'` lines for difficult characters
- `scan_env_values.sh` - scans a completed env file and proposes shell-safe export rewrites for tricky values

All scripts are check-oriented and safe to run repeatedly.
