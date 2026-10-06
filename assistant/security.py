"""Symmetric encryption for OAuth tokens at rest.

Refresh tokens grant standing access to a user's mailbox and calendar, so we
never store them in plaintext. They're encrypted with Fernet (AES-128-CBC +
HMAC) keyed from ``settings.FIELD_ENCRYPTION_KEY``.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


@lru_cache
def _cipher() -> Fernet:
    key = settings.FIELD_ENCRYPTION_KEY.encode()
    # Accept a proper 32-byte urlsafe-base64 Fernet key, or derive one from any
    # passphrase. A dedicated FIELD_ENCRYPTION_KEY is strongly advised in prod.
    try:
        return Fernet(key)
    except (ValueError, TypeError):
        return Fernet(base64.urlsafe_b64encode(hashlib.sha256(key).digest()))


def encrypt(plaintext: str) -> str:
    return _cipher().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _cipher().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:  # pragma: no cover - defensive
        raise ValueError("Failed to decrypt secret — FIELD_ENCRYPTION_KEY changed?") from exc
