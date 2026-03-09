# cube-mumble

Initial extraction snapshot for rebuilding Cube's Mumble integration as a standalone project.

This repository currently contains a direct code snapshot from `cube` branch `cube-newmumble-upstream` at commit `2869fbc8ada6010d8823f50caf52d3b1779a30a7`.

Copied baseline paths:

- `modules/mumble`
- `authenticator`
- `templates/mumble`

This is not the target architecture. The copied code is here to preserve the current implementation while `cube-mumble` is rebuilt around the newer boundary:

- `cube-core` owns Cube-side UI and policy inputs
- `cube-mumble` owns Mumble server inventory, ICE interactions, and per-server state
- `PKID` is the stable Cube-side identity key

See [docs/extraction-inventory.md](/home/michael/prj/cube-mumble/docs/extraction-inventory.md) for what was copied and what still remains in Cube core.

## Standalone Deploy Defaults

For the current standalone authenticator phase, the default layout is:

- repo checkout: `/home/cube/cube-mumble`
- virtualenv: `/home/cube/.venv/cube-mumble`
- environment file: `/home/cube/.env/cube-mumble`
- systemd unit: `cube-mumble-auth.service`

Relevant files:

- [deploy/setup-hetzner.sh](/home/michael/prj/cube-mumble/deploy/setup-hetzner.sh)
- [deploy/systemd/cube-mumble-auth.service](/home/michael/prj/cube-mumble/deploy/systemd/cube-mumble-auth.service)
- [.github/workflows/deploy-dev.yml](/home/michael/prj/cube-mumble/.github/workflows/deploy-dev.yml)
- [docs/bootstrap-dev-deploy.md](/home/michael/prj/cube-mumble/docs/bootstrap-dev-deploy.md)

`deploy/setup-hetzner.sh` is the one-time root install path. The GitHub workflow is for ordinary code updates after that setup exists.

## Read-only Pilot Contract

- `authenticator.PilotIdentity(character_id, character_name, corporation_id, alliance_id, corporation_name, alliance_name, corporation_ticker, alliance_ticker)`
- `authenticator.list_cube_pilot_identities() -> list[PilotIdentity]`

- `character_name` is used for display naming in Mumble.
- `corporation_name` and `alliance_name` are now carried through from cube-core.
- `corporation_ticker` and `alliance_ticker` remain supported in the contract and default to empty strings when cube-core does not provide them.

This contract update aligns with Cube core behavioral changes introduced in Cube PR #74.

- Membership semantics:
  - `character_id` (PKID) is stable.
  - A pilot can change corporation over time.
  - A corporation can change alliance over time.
  - Therefore `alliance_id` is membership-state, not an immutable identity attribute.
  - cube-mumble should always treat `alliance_id` as a snapshot from cube-core and refresh it whenever character org state is refreshed.

## Environment Contracts

- `CUBE_CORE_*` = read-only Cube-core source DB used by the authenticator.
- `CUBE_MMBL_AUTH_*` = cube-mumble-owned DB used for local migrations and runtime tables.

```bash
python manage.py migrate
```

uses `CUBE_MMBL_AUTH_*` and keeps local schema independent of cube-core.
