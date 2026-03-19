# Installation Materials

Canonical sequence is in `installation/installation.md`.

Preferred install/ops flow is wheel-first with Django management commands:
- `python -m django init_bg_env`
- `python -m django shell_export KEY VALUE...`
- `python -m django install_assistant`
- `python -m django list_ice_users`
- `python -m django print_systemd_bg_control --env-file ~/.env/mumble-bg`
- `python -m django print_systemd_bg_authd --env-file ~/.env/mumble-bg`

JSON env note: if a value must contain a literal apostrophe, encode it as `\\u0027` in JSON. Example: `"'MyPrettyS3rcet'"` should be `"\\u0027MyPrettyS3rcet\\u0027"`.

Optional source-checkout helper wrappers are in `installation/scripts/`:

- `bg_preflight.sh` - validates BG config, checks, and migration state
- `bg_runtime_verify.sh` - validates BG runtime endpoints and ICE user listing
- `fg_env_check.sh` - validates FG-side control env variables in the Cube shell
- `init_bg_env.sh` - creates `~/.env/mumble-bg` from a complete first-time template
- `shell_export.sh` - prints shell-safe `export KEY='value'` lines for difficult characters
- `scan_env_values.sh` - scans a completed env file and proposes shell-safe export rewrites for tricky values

All scripts are check-oriented and safe to run repeatedly.
