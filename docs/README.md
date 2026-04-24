# mumble-bg Documentation

Verified: `mumble-bg` `main` version `0.3.7.dev1` on `2026-04-24`.

This directory is the canonical documentation location for this repository.

Primary reference:

- [design.md](./design.md) - current architecture, runtime contracts, and security model.
- [operations.md](./operations.md) - installation, workflows, testing, and ICE/TLS guidance.

## Scope

- `mumble-bg` is the background/runtime service for Murmur integration.
- BG owns runtime state, Murmur/ICE integration, authd, reconciliation, pulse, and control/probe APIs.
- BG manages zero, one, or many Murmur servers by stable server identity.
- FG is the host-facing UI layer that sends ACL and pilot snapshot data to BG.

## Working assumptions

- `BG_DBMS` is the BG database.
- `BG_PSK` is the bootstrap control secret.
- `BG_PKI_PASSPHRASE` unlocks BG key material when encrypted.
- `MURMUR_CONTROL_URL` points FG at BG control.
- `server_key` is the durable per-server identity used by BG and FG inventory snapshots.
- `pulse` is the live presence and reconcile subsystem.

## Operator checklist

1. Read [design.md](./design.md) before changing control, inventory, or provisioning behavior.
2. Use [operations.md](./operations.md) for install, deploy, TLS, and smoke checks.
3. Keep BG/FG contracts aligned; docs drift is a bug.
