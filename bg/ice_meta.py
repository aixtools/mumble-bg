from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IceMetaAttempt:
    protocol: str
    category: str
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

    def attempt_for(self, protocol: str) -> IceMetaAttempt | None:
        for attempt in self.attempts:
            if attempt.protocol == protocol:
                return attempt
        return None


def _ice_tls_flag(value: str) -> bool:
    return bool((value or "").strip())


def ice_client_tls_status(*, tls_cert: str = "", tls_key: str = "", tls_ca: str = "") -> dict[str, bool]:
    cert = (tls_cert or os.environ.get("BG_ICE_CERT_PATH", "")).strip()
    key = (tls_key or os.environ.get("BG_ICE_KEY_PATH", "")).strip()
    ca = (tls_ca or os.environ.get("BG_ICE_CA_PATH", "")).strip()
    key_pass = os.environ.get("BG_ICE_KEY_PASSPHRASE", "").strip()
    return {
        "ice_cert_present": _ice_tls_flag(cert),
        "ice_key_present": _ice_tls_flag(key) or _ice_tls_flag(cert),
        "ice_ca_present": _ice_tls_flag(ca) or _ice_tls_flag(cert),
        "ice_key_passphrase_present": _ice_tls_flag(key_pass),
        "ice_cert_exists": bool(cert) and Path(cert).exists(),
        "ice_key_exists": bool(key) and Path(key).exists(),
        "ice_ca_exists": bool(ca) and Path(ca).exists(),
    }


def classify_ice_connection_error(error: str) -> str:
    lowered = str(error or "").lower()
    if "certificate required" in lowered:
        return "client_certificate_required"
    if any(token in lowered for token in ("certificate verify failed", "unknown ca", "bad certificate", "certificate unknown")):
        return "certificate_rejected"
    if "connection refused" in lowered:
        return "connect_refused"
    if "timeout" in lowered:
        return "connect_timeout"
    if any(token in lowered for token in ("no route to host", "network is unreachable", "host is down")):
        return "unreachable"
    if any(token in lowered for token in ("protocolexception", "ssl", "tls")):
        return "ssl_handshake_failed"
    return "unknown"


def ice_connection_hint(*, attempts: tuple[IceMetaAttempt, ...]) -> str:
    ssl_attempt = next((attempt for attempt in attempts if attempt.protocol == "ssl"), None)
    tcp_attempt = next((attempt for attempt in attempts if attempt.protocol == "tcp"), None)
    if ssl_attempt and ssl_attempt.category == "client_certificate_required":
        return "remote ICE requires a client certificate; configure BG_ICE_CERT_PATH/BG_ICE_KEY_PATH and ensure the server trusts BG's CA"
    if ssl_attempt and ssl_attempt.category == "certificate_rejected":
        return "remote ICE rejected BG's client certificate; verify BG_ICE_CA_PATH and the server trust chain"
    if tcp_attempt and tcp_attempt.category in {"connect_timeout", "connect_refused", "unreachable"}:
        return "tcp fallback is not reachable; verify the remote ICE tcp listener, firewall, and bind address"
    return "verify BG ICE client TLS settings and the remote ICE ssl/tcp listener configuration"


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
            attempts.append(
                IceMetaAttempt(
                    protocol=protocol,
                    category=classify_ice_connection_error(str(exc)),
                    error=str(exc),
                )
            )
    raise IceMetaConnectionError(host=host, port=int(port), attempts=tuple(attempts))
