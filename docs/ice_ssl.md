<!-- SPDX-License-Identifier: BSD-3-Clause -->
# Ice over SSL

This short guide explains what Murmur needs in order to speak Ice over TLS.

## 1. Load the IceSSL plugin

Murmur does not default to TLS even when `libIceSSL` exists. The IceSSL transport must be registered before the communicator is initialized. Add the following key/value pairs to your `mumble-server.ini` (no `[sections]`—just flat properties):

```
Ice.Plugin.IceSSL=IceSSL:createIceSSL
IceSSL.CertFile=/etc/mumble-server/certs/server.pfx
IceSSL.CAs=/etc/mumble-server/certs/ca.pem
IceSSL.Password=<passphrase-if-needed>
```

`Ice.Plugin.IceSSL` registers the plugin; the remaining lines point to your certificate bundle, CA chain, and optional passphrase. Once those values are present Murmur logs should show the IceSSL plugin loading and `ssl://…` endpoints become usable.

## 2. Verify on startup

After applying the change restart `mumble-server` and watch the log for an `IceSSL` plugin registration message. Use your Ice client and request an SSL endpoint to confirm the TLS listener is offered. If Ice fails to start, the communicator will log why it could not open the certificate files or decrypt the private key.

