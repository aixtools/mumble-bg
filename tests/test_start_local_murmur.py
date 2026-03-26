from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase

from bg.state.management.commands.start_local_murmur import LocalMurmurHarness


class StartLocalMurmurIniTest(SimpleTestCase):
    def _make_harness(self, root_dir: Path, *, instance_number: int) -> LocalMurmurHarness:
        return LocalMurmurHarness(
            root_dir=root_dir,
            server_name="Local BG Test",
            client_bind_host="",
            probe_host="127.0.0.1",
            ice_host="127.0.0.1",
            ice_bind_host="",
            address_host="127.0.0.1",
            client_port=26521,
            ice_port=26501,
            ice_secret="test-secret",
            server_id=1,
            instance_number=instance_number,
        )

    def test_odd_instance_writes_ssl_ice_section_and_properties(self):
        with TemporaryDirectory() as tmpdir:
            root_dir = Path(tmpdir)
            harness = self._make_harness(root_dir, instance_number=1)

            root_dir.mkdir(parents=True, exist_ok=True)
            Path(harness.paths.cert_path).write_text("cert")
            Path(harness.paths.key_path).write_text("key")

            harness._write_ini()

            ini_text = Path(harness.paths.ini_path).read_text()

        self.assertIn("host=\n", ini_text)
        self.assertIn('ice="ssl -h 0.0.0.0 -p 26501"', ini_text)
        self.assertIn("[Ice]\nIce.Plugin.IceSSL=IceSSL:createIceSSL", ini_text)
        self.assertIn(f"IceSSL.CertFile={root_dir / 'cert.pem'}", ini_text)
        self.assertIn(f"IceSSL.KeyFile={root_dir / 'key.pem'}", ini_text)
        self.assertIn(f"IceSSL.CAs={root_dir / 'cert.pem'}", ini_text)
        self.assertNotIn("IceSSL.CACertFile", ini_text)

    def test_even_instance_writes_tcp_ice_endpoint_without_ice_section(self):
        with TemporaryDirectory() as tmpdir:
            root_dir = Path(tmpdir)
            harness = self._make_harness(root_dir, instance_number=2)

            root_dir.mkdir(parents=True, exist_ok=True)
            Path(harness.paths.cert_path).write_text("cert")
            Path(harness.paths.key_path).write_text("key")

            harness._write_ini()

            ini_text = Path(harness.paths.ini_path).read_text()

        self.assertIn("host=\n", ini_text)
        self.assertIn('ice="tcp -h 127.0.0.1 -p 26501"', ini_text)
        self.assertNotIn("[Ice]", ini_text)
        self.assertNotIn("Ice.Plugin.IceSSL", ini_text)
