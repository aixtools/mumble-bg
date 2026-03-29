from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class IceMetaAttempt:
    protocol: str
    error: str


class IceMetaConnectionError(RuntimeError):
    def __init__(self, *, host: str, port: int, attempts: tuple[IceMetaAttempt, ...]):
        self.host = host
        self.port = int(port)
        self.attempts = attempts
        details = "; ".join(f"{attempt.protocol}: {attempt.error}" for attempt in attempts) or "no attempts recorded"
        super().__init__(
            f"could not connect to ICE meta at {host}:{int(port)} via ssl or tcp. Attempts: {details}"
        )


def build_ice_client_props(*, tls_cert: str = "", tls_key: str = "", tls_ca: str = "") -> list[str]:
    props = [
        "--Ice.ImplicitContext=Shared",
        "--Ice.Default.EncodingVersion=1.0",
        "--Ice.Plugin.IceSSL=IceSSL:createIceSSL",
        "--IceSSL.VerifyPeer=0",
        "--Ice.ACM.Client.Heartbeat=3",
    ]
    cert = (tls_cert or os.environ.get("BG_ICE_CERT_PATH", "")).strip()
    key = (tls_key or os.environ.get("BG_ICE_KEY_PATH", "")).strip()
    ca = (tls_ca or os.environ.get("BG_ICE_CA_PATH", "")).strip()
    if cert:
        props.append(f"--IceSSL.CertFile={cert}")
    if key:
        props.append(f"--IceSSL.KeyFile={key}")
    elif cert:
        props.append(f"--IceSSL.KeyFile={cert}")
    if ca:
        props.append(f"--IceSSL.CAs={ca}")
    elif cert:
        props.append(f"--IceSSL.CAs={cert}")
    key_pass = os.environ.get("BG_ICE_KEY_PASSPHRASE", "").strip()
    if key_pass:
        props.append(f"--IceSSL.Password={key_pass}")
    return props


def rewrite_proxy_host(communicator, proxy, host: str, port: int):
    """Rewrite a server proxy's endpoints to use a specific host/port.

    Murmur embeds its local bind address in server proxies returned by
    getBootedServers(). When the server is behind NAT, that address is
    unreachable from the BG host.  This rewrites the proxy to route
    through the known-good host from the BG inventory.
    """
    identity = proxy.ice_getIdentity()
    endpoint = f"ssl -h {host} -p {int(port)}:tcp -h {host} -p {int(port)}"
    new_proxy = communicator.stringToProxy(f"{communicator.identityToString(identity)}:{endpoint}")
    new_proxy = new_proxy.ice_encodingVersion(proxy.ice_getEncodingVersion())
    return type(proxy).uncheckedCast(new_proxy)


def connect_meta_with_fallback(communicator, M, *, host: str, port: int, secret: str = ""):
    attempts: list[IceMetaAttempt] = []
    for protocol in ("ssl", "tcp"):
        endpoint = f"Meta:{protocol} -h {host} -p {int(port)}"
        try:
            proxy = communicator.stringToProxy(endpoint)
            if secret:
                proxy = proxy.ice_context({"secret": secret})
            meta = M.MetaPrx.checkedCast(proxy)
            if not meta:
                raise RuntimeError("checkedCast returned no meta proxy")
            return meta, protocol, tuple(attempts)
        except Exception as exc:  # noqa: BLE001
            attempts.append(IceMetaAttempt(protocol=protocol, error=str(exc)))
    raise IceMetaConnectionError(host=host, port=int(port), attempts=tuple(attempts))
