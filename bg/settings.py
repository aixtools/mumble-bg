"""
Minimal Django settings for mumble-bg-owned tables.

BG now owns its runtime schema plus the cached FG pilot snapshot.
This settings module is for `manage.py migrate` and local ownership of
mumble-bg state configured through `BG_DBMS`.
"""

import os
import socket

from bg.db import db_config_from_env

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


SECRET_KEY = 'mumble-bg-dev'
DEBUG = True
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'bg.state.apps.StateConfig',
]

MIDDLEWARE = []

ROOT_URLCONF = 'bg.urls'
WSGI_APPLICATION = 'bg.wsgi.application'


def _candidate_hosts(host):
    requested = (host or '').strip() or '127.0.0.1'
    if requested.lower() == 'localhost':
        return ['127.0.0.1', 'localhost']
    return [requested]


def _port_open(host, port):
    try:
        with socket.create_connection((host, port), timeout=0.2):
            return True
    except OSError:
        return False


def _detect_database_engine(host):
    for candidate in _candidate_hosts(host):
        if _port_open(candidate, 5432):
            return 'postgresql'
        if _port_open(candidate, 3306):
            return 'mysql'
    return 'postgresql'


# BG_USE_SQLITE: use sqlite for BG's owned state tables (MumbleUser, AccessRule,
# MumbleServer, cached pilot snapshot, etc.). Set to a file path, e.g.
# /tmp/bg-test.sqlite3.
_BG_SQLITE_PATH = os.environ.get('BG_USE_SQLITE', '').strip()

if _BG_SQLITE_PATH:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': _BG_SQLITE_PATH,
        }
    }
else:
    BG_DATABASE = db_config_from_env(
        'BG_DBMS',
        'bg',
        default_database='MMBL_BG',
        default_host='localhost',
        default_username='cube',
        legacy_env_var='DATABASES',
    )

    DATABASE_HOST = BG_DATABASE.host
    DATABASE_ENGINE = _detect_database_engine(DATABASE_HOST)

    if DATABASE_ENGINE.startswith('mysql'):
        DB_ENGINE = 'django.db.backends.mysql'
    else:
        DB_ENGINE = 'django.db.backends.postgresql'

    DATABASES = {
        'default': {
            'ENGINE': DB_ENGINE,
            'NAME': BG_DATABASE.name,
            'HOST': DATABASE_HOST,
            'USER': BG_DATABASE.user,
            'PASSWORD': BG_DATABASE.password,
        }
    }

AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
