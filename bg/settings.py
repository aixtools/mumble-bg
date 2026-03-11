"""
Minimal Django settings for mumble-bg-owned tables.

The runtime auth daemon still reads Cube-core via SQL directly.
This settings module is for `manage.py migrate` and local ownership of
mumble-bg runtime schema in `MMBL_BG_*`.
"""

import os
import socket

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


SECRET_KEY = 'mumble-bg-dev'
DEBUG = True
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'modules.mumble',
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


DATABASE_HOST = os.environ.get('MMBL_BG_DATABASE_HOST', 'localhost')
DATABASE_ENGINE = _detect_database_engine(DATABASE_HOST)

if DATABASE_ENGINE.startswith('mysql'):
    DB_ENGINE = 'django.db.backends.mysql'
else:
    DB_ENGINE = 'django.db.backends.postgresql'

DATABASES = {
    'default': {
        'ENGINE': DB_ENGINE,
        'NAME': os.environ.get('MMBL_BG_DATABASE_NAME', 'MMBL_BG'),
        'HOST': DATABASE_HOST,
        'USER': os.environ.get('MMBL_BG_DATABASE_USER', 'cube'),
        'PASSWORD': os.environ.get('MMBL_BG_DATABASE_PASSWORD', ''),
    }
}

AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
