import pytest

from bg.db import PilotDBError
from bg.ice_inventory import parse_ice_env


def test_parse_ice_env_uses_name_for_display_title():
    entries = parse_ice_env(
        """
        [
          {
            "icehost": "127.0.0.1",
            "address": "localhost:64738",
            "name": "Main Comms",
            "virtual_server_id": 1,
            "icewrite": "secret",
            "iceport": 6502
          }
        ]
        """
    )

    assert len(entries) == 1
    assert entries[0].name == "Main Comms"
    assert entries[0].address == "localhost:64738"
    assert entries[0].ice_host == "127.0.0.1"


def test_parse_ice_env_defaults_name_to_address():
    entries = parse_ice_env(
        """
        [
          {
            "icehost": "127.0.0.1",
            "address": "127.0.0.1:64738",
            "virtual_server_id": 1,
            "icewrite": "secret",
            "iceport": 6502
          }
        ]
        """
    )

    assert len(entries) == 1
    assert entries[0].name == "127.0.0.1:64738"


def test_parse_ice_env_accepts_legacy_label_as_fallback():
    entries = parse_ice_env(
        """
        [
          {
            "icehost": "127.0.0.1",
            "address": "127.0.0.1:64738",
            "label": "Legacy Label",
            "virtual_server_id": 1,
            "icewrite": "secret",
            "iceport": 6502
          }
        ]
        """
    )

    assert len(entries) == 1
    assert entries[0].name == "Legacy Label"


def test_parse_ice_env_requires_separate_icehost_and_address():
    with pytest.raises(PilotDBError, match="missing required address"):
        parse_ice_env(
            """
            [
              {
                "icehost": "127.0.0.1",
                "virtual_server_id": 1,
                "icewrite": "secret",
                "iceport": 6502
              }
            ]
            """
        )


def test_parse_ice_env_accepts_tls_fields():
    entries = parse_ice_env(
        """
        [
          {
            "icehost": "127.0.0.1",
            "address": "127.0.0.1:64738",
            "virtual_server_id": 1,
            "icewrite": "secret",
            "iceport": 6502,
            "ice_tls_cert": "/tmp/cert.pem",
            "ice_tls_key": "/tmp/key.pem",
            "ice_tls_ca": "/tmp/ca.pem"
          }
        ]
        """
    )

    assert entries[0].ice_tls_cert == "/tmp/cert.pem"
    assert entries[0].ice_tls_key == "/tmp/key.pem"
    assert entries[0].ice_tls_ca == "/tmp/ca.pem"
