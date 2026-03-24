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
        with patch("builtins.print") as print_mock:
            with patch("django.core.management.execute_from_command_line") as execute:
                control_main(["--noreload"])

    print_mock.assert_called_once_with(
        "mumble-bg control bind=127.0.0.1:18080 source=MURMUR_CONTROL_URL detail=MURMUR_CONTROL_URL literal IP",
        flush=True,
    )

    execute.assert_called_once_with(
        ["django", "runserver", "127.0.0.1:18080", "--noreload"]
    )


def test_control_main_logs_default_bind_as_fallback():
    with patch.dict(os.environ, {}, clear=True):
        with patch("builtins.print") as print_mock:
            with patch("django.core.management.execute_from_command_line") as execute:
                control_main(["--noreload"])

    print_mock.assert_called_once_with(
        "mumble-bg control MURMUR_CONTROL_URL not set, using 127.0.0.1:18080",
        flush=True,
    )
    execute.assert_called_once_with(
        ["django", "runserver", "127.0.0.1:18080", "--noreload"]
    )


def test_bootstrap_bg_environment_loads_bg_psk(tmp_path):
    env_file = tmp_path / "mumble-bg.env"
    env_file.write_text("BG_PSK='fresh-shared-secret'\n", encoding="utf-8")

    with patch.dict(os.environ, {"BG_ENV_FILE": str(env_file)}, clear=True):
        bootstrap_bg_environment()

        assert os.environ["BG_PSK"] == "fresh-shared-secret"


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
