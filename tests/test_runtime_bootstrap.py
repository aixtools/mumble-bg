import os
import sys
import types
from unittest.mock import Mock, patch

from bg.authd.main import main as authd_main
from bg.control_main import main as control_main
from bg.envtools import bootstrap_bg_environment


def test_bootstrap_bg_environment_loads_bg_env_file_without_overriding(tmp_path):
    env_file = tmp_path / "mumble-bg.env"
    env_file.write_text(
        "\n".join(
            [
                "BG_KEY_PASSPHRASE='secret-passphrase'",
                "MURMUR_CONTROL_URL='http://127.0.0.1:18080'",
            ]
        ),
        encoding="utf-8",
    )

    with patch.dict(
        os.environ,
        {
            "BG_ENV_FILE": str(env_file),
            "MURMUR_CONTROL_URL": "http://override.example:9999",
        },
        clear=True,
    ):
        bootstrap_bg_environment()

        assert os.environ["DJANGO_SETTINGS_MODULE"] == "bg.settings"
        assert os.environ["BG_KEY_PASSPHRASE"] == "secret-passphrase"
        assert os.environ["MURMUR_CONTROL_URL"] == "http://override.example:9999"


def test_control_main_resolves_bind_from_environment():
    with patch.dict(
        os.environ,
        {
            "MURMUR_CONTROL_URL": "http://127.0.0.1:18080",
        },
        clear=True,
    ):
        with patch("django.core.management.execute_from_command_line") as execute:
            control_main(["--noreload"])

    execute.assert_called_once_with(
        ["django", "runserver", "127.0.0.1:18080", "--noreload"]
    )


def test_bootstrap_bg_environment_maps_fgbg_psk_to_legacy_alias(tmp_path):
    env_file = tmp_path / "mumble-bg.env"
    env_file.write_text("FGBG_PSK='fresh-shared-secret'\n", encoding="utf-8")

    with patch.dict(os.environ, {"BG_ENV_FILE": str(env_file)}, clear=True):
        bootstrap_bg_environment()

        assert os.environ["FGBG_PSK"] == "fresh-shared-secret"
        assert os.environ["MURMUR_CONTROL_PSK"] == "fresh-shared-secret"


def test_bootstrap_bg_environment_maps_legacy_psk_to_fgbg_psk(tmp_path):
    env_file = tmp_path / "mumble-bg.env"
    env_file.write_text("MURMUR_CONTROL_PSK='legacy-shared-secret'\n", encoding="utf-8")

    with patch.dict(os.environ, {"BG_ENV_FILE": str(env_file)}, clear=True):
        bootstrap_bg_environment()

        assert os.environ["FGBG_PSK"] == "legacy-shared-secret"
        assert os.environ["MURMUR_CONTROL_PSK"] == "legacy-shared-secret"


def test_authd_main_loads_bg_env_file_before_service_import(tmp_path):
    env_file = tmp_path / "mumble-bg.env"
    env_file.write_text("BG_KEY_PASSPHRASE='secret-passphrase'\n", encoding="utf-8")

    fake_service = types.ModuleType("bg.authd.service")
    fake_service.main = Mock()

    with patch.dict(os.environ, {"BG_ENV_FILE": str(env_file)}, clear=True):
        with patch.dict(sys.modules, {"bg.authd.service": fake_service}):
            authd_main()
        assert os.environ["BG_KEY_PASSPHRASE"] == "secret-passphrase"

    fake_service.main.assert_called_once_with()
