# Non-secret settings (safe to commit).
# Secrets should be provided via environment variables or an external settings file.

import os


def _env(name: str, default: str | int | bool | None = None):
    value = os.environ.get(name)
    if value is None:
        return default
    if isinstance(default, bool):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(default, int):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return value

ALLIANCE_ID = _env("ALLIANCE_ID", 99013537)
ALLIANCE_TICKER = _env("ALLIANCE_TICKER", None)
AUTH_DBPREFIX = _env("AUTH_DBPREFIX", "")
CUBE_DBPREFIX = _env("CUBE_DBPREFIX", "")

# Optional logging
LOG_LEVEL = _env("LOG_LEVEL", "INFO")
LOG_FILE = _env("LOG_FILE", None)

# ICE connection
ICE_HOST = _env("ICE_HOST", "127.0.0.1")
ICE_PORT = _env("ICE_PORT", 6502)
ICE_SECRET = _env("ICE_SECRET", None)
ICE_INI_PATH = _env("ICE_INI_PATH", None)
# ICE_PYTHONPATH intentionally disabled for now.
# We currently rely on bundled ICE modules shipped with the package
# for Mumble 1.5 compatibility.
# ICE_PYTHONPATH = _env("ICE_PYTHONPATH", None)
ICE_HOSTS = _env(
    "ICE_HOSTS",
    _env("ICEHOST", None),
)

# Mumble connection
PYMUMBLE_SERVER_ID = _env("PYMUMBLE_SERVER_ID", 1)
PYMUMBLE_SERVER = _env("PYMUMBLE_SERVER", ICE_HOST)
PYMUMBLE_PORT = _env("PYMUMBLE_PORT", 64738)
PYMUMBLE_USER = _env("PYMUMBLE_USER", "monitor")
PYMUMBLE_PASSWD = _env("PYMUMBLE_PASSWD", "")
PYMUMBLE_CERT_FILE = _env("PYMUMBLE_CERT_FILE", ".tmp/monitor_cert.pem")
PYMUMBLE_KEY_FILE = _env("PYMUMBLE_KEY_FILE", ".tmp/monitor_key.pem")
MUMBLE_DB_NAME = _env("MUMBLE_DB_NAME", "mumble_db")
MUMBLE_DB_HOST = _env("MUMBLE_DB_HOST", ICE_HOST)
MUMBLE_DB_PORT = _env("MUMBLE_DB_PORT", 3306)
MUMBLE_DB_USER = _env("MUMBLE_DB_USER", "mumble")
MUMBLE_DB_PASSWORD = _env("MUMBLE_DB_PASSWORD", "yourPW")

# Database
EVE_HOST = _env("EVE_HOST", None)
EVE_PORT = _env("EVE_PORT", None)
EVE_DB = _env("EVE_DB", None)
EVE_USER = _env("EVE_USER", None)
EVE_PASSWORD = _env("EVE_PASSWORD", None)

AUTH_DB = _env("AUTH_DB", EVE_DB or "aa_db")
AUTH_USER = _env("AUTH_USER", EVE_USER or "aa_user")
AUTH_PASSWORD = _env(
    "AUTH_PASSWORD",
    EVE_PASSWORD or "fill-with-valid-password",
)
AUTH_HOST = _env("AUTH_HOST", EVE_HOST or "127.0.0.1")
AUTH_PORT = _env("AUTH_PORT", EVE_PORT or "3306")

CUBE_DB = _env("CUBE_DB", EVE_DB or "cube_db")
CUBE_USER = _env("CUBE_USER", EVE_USER or "cube_user")
CUBE_PASSWORD = _env(
    "CUBE_PASSWORD",
    EVE_PASSWORD or "fill-with-valid-password",
)
CUBE_HOST = _env("CUBE_HOST", EVE_HOST or "127.0.0.1")
CUBE_PORT = _env("CUBE_PORT", EVE_PORT or "5432")

DATABASES = {
    "mumble_mysql": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": MUMBLE_DB_NAME,
        "USER": MUMBLE_DB_USER,
        "PASSWORD": MUMBLE_DB_PASSWORD,
        "HOST": MUMBLE_DB_HOST,
        "PORT": str(_env("MYSQL_PORT", MUMBLE_DB_PORT)),
        "OPTIONS": {
            "charset": "utf8mb4",
            "connect_timeout": 5,
            **(
                {
                    "ssl": {
                        key: value
                        for key, value in {
                            "ca": _env("MYSQL_SSL_CA", ""),
                            "cert": _env("MYSQL_SSL_CERT", ""),
                            "key": _env("MYSQL_SSL_KEY", ""),
                        }.items()
                        if str(value or "").strip()
                    }
                }
                if any(
                    str(value or "").strip()
                    for value in (
                        _env("MYSQL_SSL_CA", ""),
                        _env("MYSQL_SSL_CERT", ""),
                        _env("MYSQL_SSL_KEY", ""),
                    )
                )
                else {}
            ),
        },
    },
    "mumble_psql": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": MUMBLE_DB_NAME,
        "USER": MUMBLE_DB_USER,
        "PASSWORD": MUMBLE_DB_PASSWORD,
        "HOST": MUMBLE_DB_HOST,
        "PORT": str(_env("PSQL_PORT", 5432)),
        "OPTIONS": {
            "connect_timeout": 10,
            "options": "-c statement_timeout=30000",
        },
        "MONITOR_SSLROOTCERT": _env("PSQL_SSLROOTCERT", ""),
    },
    "mysql": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": AUTH_DB,
        "USER": AUTH_USER,
        "PASSWORD": AUTH_PASSWORD,
        "HOST": AUTH_HOST,
        "PORT": AUTH_PORT,
        "OPTIONS": {
            "charset": "utf8mb4",
            "connect_timeout": 5,
            **(
                {
                    "ssl": {
                        key: value
                        for key, value in {
                            "ca": _env("MYSQL_SSL_CA", ""),
                            "cert": _env("MYSQL_SSL_CERT", ""),
                            "key": _env("MYSQL_SSL_KEY", ""),
                        }.items()
                        if str(value or "").strip()
                    }
                }
                if any(
                    str(value or "").strip()
                    for value in (
                        _env("MYSQL_SSL_CA", ""),
                        _env("MYSQL_SSL_CERT", ""),
                        _env("MYSQL_SSL_KEY", ""),
                    )
                )
                else {}
            ),
        },
    },
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": CUBE_DB,
        "USER": CUBE_USER,
        "PASSWORD": CUBE_PASSWORD,
        "HOST": CUBE_HOST,
        "PORT": CUBE_PORT,
        "OPTIONS": {
            "connect_timeout": 10,
            "options": "-c statement_timeout=30000",
        },
        "MONITOR_SSLROOTCERT": _env("PSQL_SSLROOTCERT", ""),
    },
    # "sqlite3": {
    #     "ENGINE": "django.db.backends.sqlite3",
    #     "NAME": "mydatabase",
    # },
}

# Misc runtime behavior
JANICE_API_KEY = _env("JANICE_API_KEY", "FAKE-JANICE-API-KEY-EXAMPLE-0000")
JANICE_MARKET = _env("JANICE_MARKET", "2")
JANICE_PRICING = _env("JANICE_PRICING", "sell")
JANICE_VARIANT = _env("JANICE_VARIANT", "immediate")
JANICE_DAYS = _env("JANICE_DAYS", "0")
ITEM_PRICE_CACHE_BACKEND = _env("ITEM_PRICE_CACHE_BACKEND", "json")
ITEM_PRICE_CACHE_FILE = _env(
    "ITEM_PRICE_CACHE_FILE", "/var/tmp/monitor-item-price-cache.json"
)
ITEM_PRICE_CACHE_TTL_SECONDS = _env("ITEM_PRICE_CACHE_TTL_SECONDS", 3600)
