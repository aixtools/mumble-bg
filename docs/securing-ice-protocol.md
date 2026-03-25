# Securing the ICE Protocol

This project enforces TLS for background (BG) communications with Murmur ICE endpoints.

## Keypair placement

1. Generate or reuse a certificate/private key bundle under `/etc/mumble-bg/keys` (matching the deployment identity, e.g. `ice-client-cert.pem` + `ice-client-key.pem`).
2. Ensure the CA certificate that signed the client cert is also available on each ICE host (`IceSSL.CACertFile` in `mumble-server.ini`).
3. Store the private key with `chmod 600` and, if encrypted, record the passphrase in BG’s env (`BG_ICE_KEY_PASSPHRASE`) so the communicator can unlock it while remaining protected.

## Murmur/ICE requirements

- Configure every Murmur instance to listen on an `ssl` transport (`ice="ssl -h 0.0.0.0 -p 6502"`).
- Set matching `icesecretread`/`icesecretwrite` values and ensure the server trusts the CA that issued the client cert.
- The server does not generate/rotate keys automatically; you must provision the cert and update `mumble-server.ini` manually or via automation before you start BG.

## BG communicator configuration

- Pass `IceSSL.CertFile`, `IceSSL.KeyFile`, and optionally `IceSSL.CACertFile` to the communicator before connecting.
- Supply `IceSSL.KeyPassphrase` when a passphrase is used; keep it in `BG_ICE_KEY_PASSPHRASE` and push it through the deploy workflow.
- Continue to set per-server secrets (`ice_secret`) via ICE inventory JSON to protect shared secrets on top of TLS.

## Key rotation

- Unique certs per ICE endpoint are supported but optional. A single cert/CA combo simplifies rotation because you only need to update one set of files, while unique certs limit blast radius.
- Document whichever approach you choose so teammates know how to rotate and reconfigure both sides.
