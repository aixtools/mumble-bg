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
