"""
Minimal Django settings for cube-mumble-owned tables.

The runtime auth daemon still reads Cube-core via SQL directly.
This settings module is for `manage.py migrate` and local ownership of
cube-mumble runtime schema in `CUBE_MMBL_AUTH_*`.
"""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


SECRET_KEY = 'cube-mumble-dev'
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

DATABASE_ENGINE = (os.environ.get('CUBE_MMBL_AUTH_DATABASE_ENGINE', 'postgresql') or 'postgresql').strip().lower()

if DATABASE_ENGINE.startswith('mysql'):
    DB_ENGINE = 'django.db.backends.mysql'
else:
    DB_ENGINE = 'django.db.backends.postgresql'

DATABASES = {
    'default': {
        'ENGINE': DB_ENGINE,
        'NAME': os.environ.get('CUBE_MMBL_AUTH_DATABASE_NAME', 'CUBE-MMBL-AUTH'),
        'HOST': os.environ.get('CUBE_MMBL_AUTH_DATABASE_HOST', 'localhost'),
        'USER': os.environ.get('CUBE_MMBL_AUTH_DATABASE_USER', 'cube'),
        'PASSWORD': os.environ.get('CUBE_MMBL_AUTH_DATABASE_PASSWORD', ''),
    }
}

AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
