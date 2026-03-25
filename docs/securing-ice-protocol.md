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

## Registering the IceSSL plugin

Even with the certificate/key files in place, Murmur still needs to load the IceSSL plugin before the communicator starts. Add the following flat properties to `mumble-server.ini` so that Ice registers the plugin automatically:

```
Ice.Plugin.IceSSL=IceSSL:createIceSSL
IceSSL.CertFile=/etc/mumble-server/certs/server.pfx
IceSSL.CACertFile=/etc/mumble-server/certs/ca.pem
IceSSL.Password=<passphrase-if-required>
```

`Ice.Plugin.IceSSL` is the only new entry; the other lines mirror the cert bundle you already provision for TLS. Once Murmur sees those keys it will log that IceSSL is initialized and will listen on `ssl://` endpoints.

## Verifying IceSSL is present

Use these quick checks on the target host to confirm the murmur binary has IceSSL:

```
# Binary symbols (should print lines containing IceSSL if present)
strings /usr/bin/mumble-server | grep -i IceSSL | head

# Linked libraries (look for libIceSSL alongside libIce)
ldd /usr/bin/mumble-server | grep -i ice

# Safe runtime probe; succeeds silently when IceSSL is available
mumble-server -ini /etc/mumble/mumble-server.ini -supw test >/tmp/murmur-icescan.log 2>&1
grep -i ices ssl /tmp/murmur-icescan.log
# Expect to see IceSSL plugin lines or ssl listener messages; if you see
# EndpointParseException for ssl endpoints, IceSSL is not built in.
```

## Key rotation

- Unique certs per ICE endpoint are supported but optional. A single cert/CA combo simplifies rotation because you only need to update one set of files, while unique certs limit blast radius.
- Document whichever approach you choose so teammates know how to rotate and reconfigure both sides.

## Troubleshooting recap

If Ice still rejects your `ssl://` endpoints, keep these friendly reminders handy:

1. The `.deb` itself doesn’t bundle IceSSL; it simply depends on `libzeroc-ice3.7t64`. Install that package (or let the package manager satisfy the dependency) so `libIceSSL` is available on the host.
2. `Ice.Plugin.IceSSL=IceSSL:createIceSSL` must appear in `mumble-server.ini` before the communicator initializes. Without it the cert/key values remain unused and no TLS listener is started.
3. Double-check that `IceSSL.CertFile`, `IceSSL.CACertFile`, and `IceSSL.Password` (when the key is encrypted) point at the files already mentioned in your BG environment (`BG_ICE_CERT_PATH`, `BG_ICE_CA_PATH`, `BG_ICE_KEY_PASSPHRASE`).
4. After restarting Murmur, scan the log for the IceSSL plugin banner and run `strings /usr/bin/mumble-server | grep -i IceSSL` or `ldd /usr/bin/mumble-server | grep -i ice` to confirm the plugin symbols are present.

Take those four steps together and the TLS listener will behave predictably, even if different agents have different expectations about what the `.deb` ships.
