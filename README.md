# mumble-bg

Initial extraction snapshot for rebuilding Cube's Mumble integration as a standalone project.

This repository currently contains a direct code snapshot from `cube` branch `cube-newmumble-upstream` at commit `2869fbc8ada6010d8823f50caf52d3b1779a30a7`.

Copied baseline paths:

- `modules/mumble`
- the old `authenticator/` package, now rehomed under `bg/`

The original Cube-facing Django/UI files have now been split back out into the sibling repository `../mumble-fg`.

This is not the target architecture. The copied code is here to preserve the current implementation while `mumble-bg` is rebuilt around the newer boundary:

- `cube-core` and `mumble-fg` own Cube-side UI and policy inputs
- `mumble-bg` owns Mumble background services, ICE interactions, and per-server state
- `PKID` is the stable Cube-side identity key

The locked boundary rules are documented in [docs/system-boundary.md](/home/michael/prj/mumble-bg/docs/system-boundary.md).

The bg-owned Django app and model naming choices are documented in
[docs/bg-state.md](/home/michael/prj/mumble-bg/docs/bg-state.md).

The explicit fg/bg control path is documented in
[docs/mumble-control.md](/home/michael/prj/mumble-bg/docs/mumble-control.md).

See [docs/extraction-inventory.md](/home/michael/prj/mumble-bg/docs/extraction-inventory.md) for what was copied and what still remains in Cube core.

## Installation Guides

Use the repo-local installation materials:

- `installation/README.md`
- `installation/installation.md`
- `installation/scripts/`

## Standalone Deploy Defaults

For the current standalone background-service phase, the default layout is:

- repo checkout: `/home/cube/mumble-bg`
- virtualenv: `/home/cube/.venv/mumble-bg`
- environment file: `/home/cube/.env/mumble-bg`
- systemd unit: `mumble-bg-auth.service`

Relevant files:

- [deploy/setup-hetzner.sh](/home/michael/prj/mumble-bg/deploy/setup-hetzner.sh)
- [deploy/undeploy-hetzner.sh](/home/michael/prj/mumble-bg/deploy/undeploy-hetzner.sh)
- [deploy/systemd/mumble-bg-auth.service](/home/michael/prj/mumble-bg/deploy/systemd/mumble-bg-auth.service)
- [.github/workflows/deploy-dev.yml](/home/michael/prj/mumble-bg/.github/workflows/deploy-dev.yml)
- [docs/bootstrap-dev-deploy.md](/home/michael/prj/mumble-bg/docs/bootstrap-dev-deploy.md)

`deploy/setup-hetzner.sh` is the one-time root install path. The GitHub workflow is for ordinary code updates after that setup exists.

## Pilot Eligibility Rules

BG receives access-control decision tables from FG via the control channel and
independently provisions Mumble accounts by evaluating the pilot source against these rules.

### Decision Tables (received from FG)

- **Allowed alliances** — an alliance is either in or out (no partial alliance access)
- **Blocked corps** — corps within an allowed alliance that are denied access
- **Blocked pilots** — individual pilots within an allowed alliance that are denied access
- **Allowed pilots** — individual pilot overrides that rescue access even when their corp is blocked

### Precedence (most specific wins)

1. **Pilot allow/block** overrides everything
2. **Corp block** applies if no pilot-level override exists
3. **Alliance allow** is the baseline

A blocked corp within an allowed alliance denies that corp's members — but an
explicit pilot-level allow for a specific member of that corp restores their access.

### Account-wide enforcement

Block checks apply across the **entire account**, not just the main character.
If the main **or any alt** matches a blocked corp or pilot ID, the whole account
is denied — unless a pilot-level allow overrides it.

## Read-only Pilot Contract

- `bg.authd.service.PilotIdentity(character_id, character_name, corporation_id, alliance_id, corporation_name, alliance_name, corporation_ticker, alliance_ticker)`
- `bg.authd.service.list_pilot_identities() -> list[PilotIdentity]`

- `character_name` is used for display naming in Mumble.
- `corporation_name` and `alliance_name` are now carried through from the pilot source.
- `corporation_ticker` and `alliance_ticker` remain supported in the contract and default to empty strings when cube-core does not provide them.

This contract update aligns with Cube core behavioral changes introduced in Cube PR #74.

- Membership semantics:
  - `character_id` (PKID) is stable.
  - A pilot can change corporation over time.
  - A corporation can change alliance over time.
  - Therefore `alliance_id` is membership-state, not an immutable identity attribute.
  - mumble-bg should always treat `alliance_id` as a snapshot from cube-core and refresh it whenever character org state is refreshed.

## Environment Contracts

- `DATABASES` = JSON object containing the read-only `pilot` DB config and the owned `bg` DB config.
- `ICE` = JSON list describing required ICE connectivity for `authd` and `pulse`.
- `MURMUR_PROBE` = optional JSON list for Murmur DB probe/debug targets.

```bash
python manage.py migrate
```

uses `DATABASES.bg` and keeps local schema independent of the pilot source DB.

### ICE Inventory Sync

`mumble-bg` keeps runtime ICE targets in `mumble_server` rows. The `ICE` env var
is now a sync source for that inventory:

- `bg.authd` automatically performs additive sync from `ICE` into `mumble_server`
  on startup.
- manual operator sync is available via:

```bash
python manage.py sync_ice_inventory
```

Useful command variants:

```bash
python manage.py sync_ice_inventory --dry-run --show-env
python manage.py sync_ice_inventory --show-current
python manage.py sync_ice_inventory --replace
```

`--show-current` prints active and inactive `mumble_server` rows as JSON.

### Install/Deployment Assistant

Run the no-argument preflight assistant:

```bash
python manage.py install_assistant
```

It reports:
- pilot DB connectivity
- bg DB connectivity
- ICE endpoint connectivity (from `ICE` env, or active `mumble_server` rows if `ICE` is empty)
- `none_defined` when no ICE endpoints exist

JSON output is available with:

```bash
python manage.py install_assistant --json
```

## Release Cleanup Note

Before the first real release, remove historical references to the old table names
`mumble_mumbleserver`, `mumble_mumbleuser`, and `mumble_mumblesession` from
handoff notes and transition docs. The fresh-start owned schema in this repo now
uses `mumble_server`, `mumble_user`, and `mumble_session`.
