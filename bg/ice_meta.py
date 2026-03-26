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
    ]
    cert = str(tls_cert or "").strip()
    key = str(tls_key or "").strip()
    ca = str(tls_ca or "").strip()
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
