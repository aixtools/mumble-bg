from __future__ import annotations

import datetime as dt
import secrets
import uuid

from django.db import transaction
from django.utils.timezone import now

from bg import crypto
from bg.state.models import ControlChannelKeyEntry


# Keyring policy:
# - rotate every ~4 hours
# - also rotate once per process "comms reboot" (first use after restart)
# - keep at most KEEP_MAX keys (UUID-keyed) to tolerate DB restores/out-of-sync
ROTATE_EVERY = dt.timedelta(hours=4)
KEEP_MAX = 80

_boot_rotated = False


def reset_rotation_state() -> None:
    global _boot_rotated  # noqa: PLW0603
    _boot_rotated = False


def _encrypt_secret_for_storage(secret: str) -> str:
    # Use BG public key (RSA-OAEP). Private key/passphrase is only needed to decrypt later.
    if not crypto.is_available():
        raise RuntimeError("BG crypto is not available (no public key loaded)")
    return crypto.encrypt_password(secret)


def _decrypt_secret_from_storage(ciphertext_b64: str) -> str:
    if not crypto.can_decrypt():
        raise RuntimeError("BG crypto cannot decrypt (private key unavailable)")
    return crypto.decrypt_password(ciphertext_b64)


def create_key() -> ControlChannelKeyEntry:
    # 32 bytes of entropy encoded as urlsafe text (still treated as opaque secret).
    secret = secrets.token_urlsafe(32)
    ciphertext = _encrypt_secret_for_storage(secret)
    return ControlChannelKeyEntry.objects.create(
        key_id=uuid.uuid4(),
        secret_ciphertext_b64=ciphertext,
    )


def ensure_fresh() -> ControlChannelKeyEntry | None:
    """Ensure there is a reasonably fresh key entry.

    Returns the newest entry if it exists; returns None if crypto is unavailable.
    """
    if not crypto.is_available():
        return None

    with transaction.atomic():
        global _boot_rotated  # noqa: PLW0603
        latest = ControlChannelKeyEntry.objects.select_for_update().order_by("-created_at", "-id").first()
        now_ts = now()

        # Rotate on first call after process start (comms reboot),
        # or when the newest key is stale.
        should_rotate = (not _boot_rotated) or latest is None or (now_ts - latest.created_at) >= ROTATE_EVERY
        if should_rotate:
            latest = create_key()
            _boot_rotated = True

        prune()
        return latest


def prune() -> None:
    """Retention: keep newest KEEP_MAX keys."""
    keep_ids: set[int] = set(
        ControlChannelKeyEntry.objects.order_by("-created_at", "-id")
        .values_list("id", flat=True)[:KEEP_MAX]
    )

    ControlChannelKeyEntry.objects.exclude(id__in=keep_ids).delete()


def decrypt_active_keypairs(*, limit: int = KEEP_MAX) -> list[tuple[uuid.UUID, str]]:
    """Return (key_id, secret) pairs BG should accept for inbound auth.

    Policy:
    - newest KEEP_MAX keys

    The order is stable (newest first) and duplicates by secret are removed.
    """
    prune()

    values: list[tuple[uuid.UUID, str]] = []
    seen: set[str] = set()

    rows = list(
        ControlChannelKeyEntry.objects.order_by("-created_at", "-id")
        .only("key_id", "secret_ciphertext_b64")[: int(limit)]
    )
    for row in rows:
        secret = _decrypt_secret_from_storage(row.secret_ciphertext_b64)
        if secret in seen:
            continue
        values.append((uuid.UUID(str(row.key_id)), secret))
        seen.add(secret)

    return values


def decrypt_active_secrets() -> list[str]:
    """Return secrets BG should accept for inbound auth.

    Policy:
    - newest KEEP_MAX keys
    """
    return [secret for _key_id, secret in decrypt_active_keypairs()]
