from django.test import SimpleTestCase
from unittest.mock import patch

from bg.authd.service import _log_ice_meta_connection_failure
from bg.ice_meta import IceMetaAttempt, IceMetaConnectionError


class AuthdDiagnosticsTest(SimpleTestCase):
    @patch(
        "bg.authd.service.ice_client_tls_status",
        return_value={
            "ice_cert_present": False,
            "ice_key_present": False,
            "ice_ca_present": False,
            "ice_key_passphrase_present": False,
            "ice_cert_exists": False,
            "ice_key_exists": False,
            "ice_ca_exists": False,
        },
    )
    def test_logs_classified_ice_failure(self, _mock_tls_status):
        exc = IceMetaConnectionError(
            host="18.208.88.177",
            port=6502,
            attempts=(
                IceMetaAttempt(
                    protocol="ssl",
                    category="client_certificate_required",
                    error="tlsv13 alert certificate required",
                ),
                IceMetaAttempt(
                    protocol="tcp",
                    category="connect_timeout",
                    error="timeout",
                ),
            ),
        )

        with self.assertLogs("bg.authd.service", level="ERROR") as captured:
            _log_ice_meta_connection_failure(
                exc,
                server_id=2,
                ice_host="18.208.88.177",
                ice_port=6502,
            )

        output = "\n".join(captured.output)
        self.assertIn("server_id=2", output)
        self.assertIn("ssl_result=client_certificate_required", output)
        self.assertIn("tcp_result=connect_timeout", output)
        self.assertIn("ice_cert_present=False", output)
        self.assertIn("hint=remote ICE requires a client certificate", output)
