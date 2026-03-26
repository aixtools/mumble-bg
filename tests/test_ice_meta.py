from django.test import SimpleTestCase

from bg.ice_meta import IceMetaConnectionError, build_ice_client_props, connect_meta_with_fallback


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
