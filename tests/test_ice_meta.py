import tempfile
from django.test import SimpleTestCase

from bg.ice_meta import (
    IceMetaAttempt,
    IceMetaConnectionError,
    build_ice_client_props,
    classify_ice_connection_error,
    connect_meta_with_fallback,
    ice_client_tls_status,
    ice_connection_hint,
)


class _FakeProxy:
    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        self.context = None

    def ice_context(self, context):
        self.context = context
        return self


class _FakeCommunicator:
    def __init__(self):
        self.proxies = []

    def stringToProxy(self, endpoint: str):
        proxy = _FakeProxy(endpoint)
        self.proxies.append(proxy)
        return proxy


class _FakeMetaPrx:
    failures = {}

    @classmethod
    def checkedCast(cls, proxy):
        outcome = cls.failures.get(proxy.endpoint)
        if isinstance(outcome, Exception):
            raise outcome
        if outcome is None:
            return {"endpoint": proxy.endpoint, "context": proxy.context}
        return outcome


class _FakeM:
    MetaPrx = _FakeMetaPrx


class IceMetaFallbackTest(SimpleTestCase):
    def test_build_ice_client_props_always_enables_ssl_plugin(self):
        props = build_ice_client_props()

        self.assertIn("--Ice.Plugin.IceSSL=IceSSL:createIceSSL", props)
        self.assertIn("--IceSSL.VerifyPeer=0", props)

    def test_connect_meta_with_fallback_tries_ssl_then_tcp(self):
        communicator = _FakeCommunicator()
        _FakeMetaPrx.failures = {
            "Meta:ssl -h 127.0.0.1 -p 6502": RuntimeError("ssl failed"),
        }

        meta, protocol, attempts = connect_meta_with_fallback(
            communicator,
            _FakeM,
            host="127.0.0.1",
            port=6502,
            secret="shared-secret",
        )

        self.assertEqual(protocol, "tcp")
        self.assertEqual([attempt.protocol for attempt in attempts], ["ssl"])
        self.assertEqual(meta["endpoint"], "Meta:tcp -h 127.0.0.1 -p 6502")
        self.assertEqual(meta["context"], {"secret": "shared-secret"})

    def test_connect_meta_with_fallback_reports_both_failures(self):
        communicator = _FakeCommunicator()
        _FakeMetaPrx.failures = {
            "Meta:ssl -h 127.0.0.1 -p 6502": RuntimeError("ssl failed"),
            "Meta:tcp -h 127.0.0.1 -p 6502": RuntimeError("tcp failed"),
        }

        with self.assertRaises(IceMetaConnectionError) as exc_info:
            connect_meta_with_fallback(communicator, _FakeM, host="127.0.0.1", port=6502)

        message = str(exc_info.exception)
        self.assertIn("ssl: ssl failed", message)
        self.assertIn("tcp: tcp failed", message)
        self.assertEqual(exc_info.exception.attempt_for("ssl").category, "ssl_handshake_failed")
        self.assertEqual(exc_info.exception.attempt_for("tcp").category, "unknown")

    def test_classify_ice_connection_error_detects_client_certificate_required(self):
        category = classify_ice_connection_error(
            "SSL protocol error during read: tlsv13 alert certificate required: SSL alert number 116"
        )
        self.assertEqual(category, "client_certificate_required")

    def test_classify_ice_connection_error_detects_connection_refused(self):
        category = classify_ice_connection_error("::Ice::ConnectFailedException: Connection refused")
        self.assertEqual(category, "connect_refused")

    def test_ice_connection_hint_prefers_client_certificate_guidance(self):
        exc = IceMetaConnectionError(
            host="127.0.0.1",
            port=6502,
            attempts=(
                IceMetaAttempt(
                    protocol="ssl",
                    category="client_certificate_required",
                    error="tls alert certificate required",
                ),
                IceMetaAttempt(
                    protocol="tcp",
                    category="connect_timeout",
                    error="timeout",
                ),
            ),
        )
        attempts = exc.attempts
        self.assertIn("client certificate", ice_connection_hint(attempts=attempts))

    def test_ice_client_tls_status_reports_file_presence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cert = f"{tmpdir}/cert.pem"
            key = f"{tmpdir}/key.pem"
            ca = f"{tmpdir}/ca.pem"
            for path in (cert, key, ca):
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write("x")
            status = ice_client_tls_status(tls_cert=cert, tls_key=key, tls_ca=ca)
        self.assertTrue(status["ice_cert_present"])
        self.assertTrue(status["ice_key_present"])
        self.assertTrue(status["ice_ca_present"])
        self.assertTrue(status["ice_cert_exists"])
        self.assertTrue(status["ice_key_exists"])
        self.assertTrue(status["ice_ca_exists"])
