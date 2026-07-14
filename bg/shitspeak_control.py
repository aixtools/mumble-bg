"""HTTP client for the ShitSpeak admin control API.

The counterpart of the Ice ``server_proxy`` for ``driver='shitspeak'`` rows:
BG calls out to the voice server's node-local, mandatory-mTLS control API
(``/admin/v1/*``) instead of ZeroC Ice. Configuration lives on the
``MumbleServer`` row: ``control_url`` plus the ``control_tls_*`` client
certificate/key/CA paths.

Session ids encode the owning node in their top bits
(``node_id = session >> 20``); a multi-node cluster needs the kick/ban routed
to the owning node's endpoint. The first deployment is single-node, so this
client targets one ``control_url`` and omits the optional ``server_id``
selector (unambiguous on a single-virtual-server node; the API answers 409 if
it ever is not).
"""

import json
import logging
import ssl
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 10


class ShitSpeakControlError(RuntimeError):
    pass


class ShitSpeakControlClient:
    def __init__(self, server_config, *, timeout=_DEFAULT_TIMEOUT_SECONDS):
        base_url = str(getattr(server_config, 'control_url', '') or '').strip().rstrip('/')
        cert = str(getattr(server_config, 'control_tls_cert', '') or '').strip()
        key = str(getattr(server_config, 'control_tls_key', '') or '').strip()
        ca = str(getattr(server_config, 'control_tls_ca', '') or '').strip()

        if not base_url:
            raise ShitSpeakControlError(
                f'MumbleServer {getattr(server_config, "pk", "?")} has no control_url configured'
            )
        if not base_url.lower().startswith('https://'):
            raise ShitSpeakControlError(
                f'control_url must be https:// (the admin API is mTLS-only): {base_url!r}'
            )
        if not cert or not key:
            raise ShitSpeakControlError(
                'control_tls_cert and control_tls_key are required '
                '(the admin API rejects connections without a client certificate)'
            )

        self._base_url = base_url
        self._timeout = timeout
        self._ssl_context = self._build_ssl_context(cert, key, ca)

    @staticmethod
    def _build_ssl_context(cert: str, key: str, ca: str) -> ssl.SSLContext:
        try:
            context = ssl.create_default_context(cafile=ca or None)
            context.load_cert_chain(certfile=cert, keyfile=key)
        except (OSError, ssl.SSLError) as exc:
            raise ShitSpeakControlError(f'failed to load control TLS material: {exc}') from exc
        return context

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        url = f'{self._base_url}{path}'
        data = None
        headers = {'Accept': 'application/json'}
        if payload is not None:
            data = json.dumps(payload).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(
                request, timeout=self._timeout, context=self._ssl_context
            ) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            detail = ''
            try:
                detail = exc.read().decode('utf-8', 'replace')[:500]
            except Exception:  # noqa: BLE001
                pass
            raise ShitSpeakControlError(
                f'{method} {url} failed: HTTP {exc.code} {detail}'.strip()
            ) from exc
        except (urllib.error.URLError, OSError, ssl.SSLError) as exc:
            raise ShitSpeakControlError(f'{method} {url} failed: {exc}') from exc
        try:
            return json.loads(body.decode('utf-8')) if body else {}
        except (ValueError, UnicodeDecodeError) as exc:
            raise ShitSpeakControlError(f'{method} {url} returned invalid JSON') from exc

    # ── Ice server_proxy parity surface ─────────────────────────────────────

    def kick_user(self, session_id: int, reason: str) -> dict:
        return self._request(
            'POST', '/admin/v1/kick', {'session': int(session_id), 'reason': str(reason or '')}
        )

    def ban(
        self,
        *,
        session: int | None = None,
        cert_hash: str | None = None,
        reason: str | None = None,
        duration_secs: int | None = None,
    ) -> dict:
        payload: dict = {}
        if session is not None:
            payload['session'] = int(session)
        if cert_hash is not None:
            payload['cert_hash'] = str(cert_hash)
        if reason:
            payload['reason'] = str(reason)
        if duration_secs is not None:
            payload['duration_secs'] = int(duration_secs)
        return self._request('POST', '/admin/v1/ban', payload)

    def list_online(self) -> list:
        response = self._request('GET', '/admin/v1/online')
        users = response.get('users')
        return users if isinstance(users, list) else []

    def health(self) -> dict:
        return self._request('GET', '/admin/v1/health')
