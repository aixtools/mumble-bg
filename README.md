# cube-mumble

Initial extraction snapshot for rebuilding Cube's Mumble integration as a standalone project.

This repository currently contains a direct code snapshot from `cube` branch `cube-newmumble-upstream` at commit `2869fbc8ada6010d8823f50caf52d3b1779a30a7`.

Copied baseline paths:

- `modules/mumble`
- `mumble_authenticator`
- `templates/mumble`

This is not the target architecture. The copied code is here to preserve the current implementation while `cube-mumble` is rebuilt around the newer boundary:

- `cube-core` owns Cube-side UI and policy inputs
- `cube-mumble` owns Mumble server inventory, ICE interactions, and per-server state
- `PKID` is the stable Cube-side identity key

See [docs/extraction-inventory.md](/home/michael/prj/cube-mumble/docs/extraction-inventory.md) for what was copied and what still remains in Cube core.

## Standalone Deploy Defaults

For the current standalone authenticator phase, the default layout is:

- repo checkout: `/home/cube/cube-monitor`
- virtualenv: `/home/cube/.venv/cube-monitor`
- environment file: `/home/cube/.env/cube-monitor`
- systemd unit: `cube-mumble-auth.service`

Relevant files:

- [deploy/setup-hetzner.sh](/home/michael/prj/cube-mumble/deploy/setup-hetzner.sh)
- [deploy/systemd/cube-mumble-auth.service](/home/michael/prj/cube-mumble/deploy/systemd/cube-mumble-auth.service)
- [.github/workflows/deploy-dev.yml](/home/michael/prj/cube-mumble/.github/workflows/deploy-dev.yml)

`deploy/setup-hetzner.sh` is the one-time root install path. The GitHub workflow is for ordinary code updates after that setup exists.
