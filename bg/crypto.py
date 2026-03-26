"""PKI and password encryption for the fg/bg control channel.

BG owns a keypair. The public key is shared with FG so it can encrypt
passwords before transit. BG decrypts using the private key, whose
passphrase is loaded from the environment only (never from DB or config).

Optional at-rest password storage uses AES-256-GCM with a key derived
from the same passphrase.
"""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_private_key = None
_public_key = None
_public_key_pem: bytes | None = None
_storage_key: bytes | None = None
_initialized = False


# ------------------------------------------------------------------
# Passphrase loading (SSLPassPhraseDialog pattern)
# ------------------------------------------------------------------

def _get_passphrase() -> bytes:
    """Load passphrase from systemd credentials or env var."""
    cred_dir = os.environ.get('CREDENTIALS_DIRECTORY')
    if cred_dir:
        cred_path = Path(cred_dir) / 'bg-key-passphrase'
        if cred_path.exists():
            return cred_path.read_bytes().rstrip(b'\n')

    val = os.environ.get('BG_PKI_PASSPHRASE', '').strip()
    if val:
        return val.encode('utf-8')

    legacy = os.environ.get('BG_KEY_PASSPHRASE', '').strip()
    if legacy:
        logger.warning('BG_KEY_PASSPHRASE is deprecated; use BG_PKI_PASSPHRASE instead')
        return legacy.encode('utf-8')

    return b''


# ------------------------------------------------------------------
# Initialization
# ------------------------------------------------------------------

def _default_key_dir() -> Path:
    return Path(os.environ.get('BG_KEY_DIR', '/etc/mumble-bg/keys'))


def initialize(*, key_dir: Path | str | None = None) -> bool:
    """Load keypair and derive storage key. Called once at startup.

    Returns True if crypto is available, False if no key material found.
    """
    global _private_key, _public_key, _public_key_pem, _storage_key, _initialized

    from cryptography.hazmat.primitives.serialization import (
        load_pem_private_key,
        load_pem_public_key,
        Encoding,
        PublicFormat,
    )

    if key_dir is None:
        key_dir = _default_key_dir()
    key_dir = Path(key_dir)

    private_path = key_dir / 'private_key.pem'
    public_path = key_dir / 'public_key.pem'

    if not public_path.exists():
        logger.info('No public key at %s — crypto disabled', public_path)
        _initialized = True
        return False

    _public_key_pem = public_path.read_bytes()
    _public_key = load_pem_public_key(_public_key_pem)

    if private_path.exists():
        passphrase = _get_passphrase()
        _private_key = load_pem_private_key(
            private_path.read_bytes(),
            password=passphrase or None,
        )
        logger.info('Loaded private key from %s', private_path)

        # Derive AES storage key from passphrase
        if passphrase:
            salt_path = key_dir / 'storage.salt'
            if salt_path.exists():
                salt = salt_path.read_bytes()
            else:
                salt = os.urandom(16)
                salt_path.write_bytes(salt)
                logger.info('Generated storage salt at %s', salt_path)
            _storage_key = _derive_storage_key(passphrase, salt)
    else:
        logger.info('No private key at %s — decrypt/storage disabled', private_path)

    _initialized = True
    return True


def _derive_storage_key(passphrase: bytes, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=1_000_000,
    )
    return kdf.derive(passphrase)


# ------------------------------------------------------------------
# Public accessors
# ------------------------------------------------------------------

def is_available() -> bool:
    return _initialized and _public_key is not None


def can_decrypt() -> bool:
    return _initialized and _private_key is not None


def can_store_encrypted() -> bool:
    return _initialized and _storage_key is not None


def get_public_key_pem() -> bytes:
    if _public_key_pem is None:
        raise RuntimeError('Crypto not initialized or no public key available')
    return _public_key_pem


# ------------------------------------------------------------------
# Transit encryption (RSA-OAEP/SHA-256)
# ------------------------------------------------------------------

def encrypt_password(plaintext: str, public_key_pem: bytes | None = None) -> str:
    """Encrypt a password for transit. Returns base64-encoded ciphertext."""
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives import hashes, serialization

    if public_key_pem is not None:
        key = serialization.load_pem_public_key(public_key_pem)
    elif _public_key is not None:
        key = _public_key
    else:
        raise RuntimeError('No public key available for encryption')

    ciphertext = key.encrypt(
        plaintext.encode('utf-8'),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return base64.b64encode(ciphertext).decode('ascii')


def decrypt_password(ciphertext_b64: str) -> str:
    """Decrypt a base64-encoded ciphertext using the loaded private key."""
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives import hashes

    if _private_key is None:
        raise RuntimeError('No private key available for decryption')

    ciphertext = base64.b64decode(ciphertext_b64)
    plaintext = _private_key.decrypt(
        ciphertext,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return plaintext.decode('utf-8')


# ------------------------------------------------------------------
# At-rest encryption (AES-256-GCM)
# ------------------------------------------------------------------

def encrypt_for_storage(plaintext: str) -> bytes:
    """Encrypt plaintext for DB storage. Returns nonce + ciphertext blob."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if _storage_key is None:
        raise RuntimeError('Storage encryption not available')

    aesgcm = AESGCM(_storage_key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
    return nonce + ct


def decrypt_from_storage(blob: bytes) -> str:
    """Decrypt an at-rest blob back to plaintext."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if _storage_key is None:
        raise RuntimeError('Storage decryption not available')

    aesgcm = AESGCM(_storage_key)
    nonce = blob[:12]
    ct = blob[12:]
    return aesgcm.decrypt(nonce, ct, None).decode('utf-8')


# ------------------------------------------------------------------
# Status (for health endpoint)
# ------------------------------------------------------------------

def status() -> dict[str, Any]:
    return {
        'initialized': _initialized,
        'has_public_key': _public_key is not None,
        'can_decrypt': can_decrypt(),
        'can_store_encrypted': can_store_encrypted(),
    }
