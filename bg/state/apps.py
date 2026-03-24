from django.apps import AppConfig


class StateConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'bg.state'

    def ready(self):
        import logging
        from bg import crypto
        logger = logging.getLogger('bg.crypto')
        try:
            crypto.initialize()
        except TypeError as exc:
            if 'Password was not given but private key is encrypted' in str(exc):
                logger.warning(
                    'Crypto not fully initialized: encrypted private key present but '
                    'BG_PKI_PASSPHRASE is not set'
                )
            else:
                logger.exception('Failed to initialize crypto')
        except Exception:
            logger.exception('Failed to initialize crypto')
