from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase

from bg.state.management.commands.start_local_murmur import LocalMurmurHarness


class StartLocalMurmurIniTest(SimpleTestCase):
    def _make_harness(self, root_dir: Path) -> LocalMurmurHarness:
        harness = LocalMurmurHarness(
            root_dir=root_dir,
            server_name="Local BG Test",
            bind_host="127.0.0.1",
            probe_host="127.0.0.1",
            ice_host="127.0.0.1",
            address_host="127.0.0.1",
            client_port=46969,
            ice_port=6503,
            ice_secret="test-secret",
            server_id=1,
        )
        object.__setattr__(harness, "use_ssl", True)
        return harness

    def test_ssl_ini_writes_ice_section_and_ice_ssl_properties(self):
        with TemporaryDirectory() as tmpdir:
            root_dir = Path(tmpdir)
            harness = self._make_harness(root_dir)

            root_dir.mkdir(parents=True, exist_ok=True)
            Path(harness.paths.cert_path).write_text("cert")
            Path(harness.paths.key_path).write_text("key")

            harness._write_ini()

            ini_text = Path(harness.paths.ini_path).read_text()

        self.assertIn('ice="ssl -h 127.0.0.1 -p 6503"', ini_text)
        self.assertIn("[Ice]\nIce.Plugin.IceSSL=IceSSL:createIceSSL", ini_text)
        self.assertIn(f"IceSSL.CertFile={root_dir / 'cert.pem'}", ini_text)
        self.assertIn(f"IceSSL.KeyFile={root_dir / 'key.pem'}", ini_text)
        self.assertIn(f"IceSSL.CAs={root_dir / 'cert.pem'}", ini_text)
        self.assertNotIn("IceSSL.CACertFile", ini_text)
