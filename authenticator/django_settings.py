"""
Minimal Django settings for mumble-bg-owned tables.

The runtime auth daemon still reads Cube-core via SQL directly.
This settings module is for `manage.py migrate` and local ownership of
mumble-bg runtime schema in `MMBL_BG_*`.
"""

import os

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

ROOT_URLCONF = 'authenticator.urls'
WSGI_APPLICATION = 'authenticator.wsgi.application'


def _env(*names, default=''):
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


DATABASE_ENGINE = _env(
    'MMBL_BG_DATABASE_ENGINE',
    'CUBE_MMBL_AUTH_DATABASE_ENGINE',
    default='postgresql',
).strip().lower()

if DATABASE_ENGINE.startswith('mysql'):
    DB_ENGINE = 'django.db.backends.mysql'
else:
    DB_ENGINE = 'django.db.backends.postgresql'

DATABASES = {
    'default': {
        'ENGINE': DB_ENGINE,
        'NAME': _env('MMBL_BG_DATABASE_NAME', 'CUBE_MMBL_AUTH_DATABASE_NAME', default='MMBL_BG'),
        'HOST': _env('MMBL_BG_DATABASE_HOST', 'CUBE_MMBL_AUTH_DATABASE_HOST', default='localhost'),
        'USER': _env('MMBL_BG_DATABASE_USER', 'CUBE_MMBL_AUTH_DATABASE_USER', default='cube'),
        'PASSWORD': _env('MMBL_BG_DATABASE_PASSWORD', 'CUBE_MMBL_AUTH_DATABASE_PASSWORD', default=''),
    }
}

AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
