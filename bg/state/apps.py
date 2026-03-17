from django.apps import AppConfig


class StateConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'bg.state'

    def ready(self):
        from bg import crypto
        try:
            crypto.initialize()
        except Exception:
            import logging
            logging.getLogger('bg.crypto').exception('Failed to initialize crypto')
