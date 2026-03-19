# Installation Materials

Canonical sequence is in `installation/installation.md`.

Helper scripts are in `installation/scripts/`:

- `bg_preflight.sh` - validates BG config, checks, and migration state
- `bg_runtime_verify.sh` - validates BG runtime endpoints and ICE user listing
- `fg_env_check.sh` - validates FG-side control env variables in the Cube shell
- `init_bg_env.sh` - creates `~/.env/mumble-bg` from a complete first-time template
- `shell_export.sh` - prints shell-safe `export KEY='value'` lines for difficult characters
- `scan_env_values.sh` - scans a completed env file and proposes shell-safe export rewrites for tricky values

All scripts are check-oriented and safe to run repeatedly.
