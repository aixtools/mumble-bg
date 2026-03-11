This directory contains the bundled Murmur ICE slice used by `mumble-bg`.

Source:
- upstream project: Mumble / Murmur
- file: `MumbleServer.ice`

Reason for bundling:
- `mumble-bg` needs a stable local copy so `bg.authd` and other ICE-aware helpers can load the same slice without relying on host-specific paths or environment variables

Maintenance note:
- when updating Murmur compatibility, replace `MumbleServer.ice` from the appropriate upstream source and keep this note accurate
