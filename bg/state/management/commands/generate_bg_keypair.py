"""Generate BG keypair for password transit encryption.

Usage:
    python manage.py generate_bg_keypair [--key-dir /etc/mumble-bg/keys]

Passphrase is read from BG_KEY_PASSPHRASE env var or prompted interactively.
"""

import getpass
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Generate RSA keypair for BG password encryption'

    def add_arguments(self, parser):
        parser.add_argument(
            '--key-dir',
            default=os.environ.get('BG_KEY_DIR', '/etc/mumble-bg/keys'),
            help='Directory to write keys (default: /etc/mumble-bg/keys)',
        )
        parser.add_argument(
            '--key-size',
            type=int,
            default=4096,
            help='RSA key size in bits (default: 4096)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Overwrite existing keypair',
        )

    def handle(self, **options):
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization

        key_dir = Path(options['key_dir'])
        private_path = key_dir / 'private_key.pem'
        public_path = key_dir / 'public_key.pem'

        if private_path.exists() and not options['force']:
            raise CommandError(
                f'{private_path} already exists. Use --force to overwrite.'
            )

        passphrase = os.environ.get('BG_KEY_PASSPHRASE', '').strip()
        if not passphrase:
            passphrase = getpass.getpass('Enter passphrase for private key: ')
            confirm = getpass.getpass('Confirm passphrase: ')
            if passphrase != confirm:
                raise CommandError('Passphrases do not match.')
        if not passphrase:
            raise CommandError('Passphrase cannot be empty.')

        key_size = options['key_size']
        self.stdout.write(f'Generating {key_size}-bit RSA keypair...')

        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size,
        )

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.BestAvailableEncryption(
                passphrase.encode('utf-8')
            ),
        )

        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        key_dir.mkdir(parents=True, exist_ok=True)

        private_path.write_bytes(private_pem)
        private_path.chmod(0o600)

        public_path.write_bytes(public_pem)
        public_path.chmod(0o644)

        self.stdout.write(self.style.SUCCESS(f'Private key: {private_path} (mode 0600)'))
        self.stdout.write(self.style.SUCCESS(f'Public key:  {public_path} (mode 0644)'))
        self.stdout.write('')
        self.stdout.write('Distribute the public key to FG for password encryption.')
        self.stdout.write('Set BG_KEY_PASSPHRASE in the BG environment file.')
