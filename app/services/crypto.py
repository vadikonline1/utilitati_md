"""Symmetric encryption (AES-GCM via Fernet) for sensitive data at rest.

The encryption key is derived deterministically from the UTILITATI_SECRET_KEY
environment variable (via PBKDF2-HMAC-SHA256), so no separate key file needs to
be shipped. Deployments that keep the default secret remain technically
decryptable by anyone who knows the default, so a real secret MUST be set in
production.
"""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from ..config import SECRET_KEY

_LOGGER = logging.getLogger(__name__)

_DEFAULT_SECRET = "change-me-in-production"
_SALT = b"utilitati_md_salt_v1"
_ITERATIONS = 390_000

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        if SECRET_KEY == _DEFAULT_SECRET:
            _LOGGER.warning(
                "CRYPTO: UTILITATI_SECRET_KEY is the insecure default. "
                "Set a strong secret in production so at-rest data is protected."
            )
        key = base64.urlsafe_b64encode(
            hashlib.pbkdf2_hmac(
                "sha256",
                SECRET_KEY.encode("utf-8"),
                _SALT,
                _ITERATIONS,
                dklen=32,
            )
        )
        _fernet = Fernet(key)
    return _fernet


def encrypt(plaintext: str | None) -> str | None:
    """Return a URL-safe Fernet token, or None if plaintext is empty/None."""
    if not plaintext:
        return None
    try:
        return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Encryption failed")
        return None


def decrypt(token: str | None) -> str | None:
    """Return the original plaintext, or None if the token is absent/invalid."""
    if not token:
        return None
    try:
        return _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception):  # noqa: BLE001
        # Unreadable / legacy data: return None so storage stays readable-only.
        _LOGGER.warning("Could not decrypt a stored value (invalid token)")
        return None


def is_encrypted(token: str | None) -> bool:
    """True when the value looks like a Fernet token we can decrypt."""
    return token is not None and token.startswith("gAAAAA")


def safe_encrypt(plaintext: str | None) -> str:
    """Encrypt, always returning a non-None string for storage ('' when empty)."""
    return encrypt(plaintext) or ""
