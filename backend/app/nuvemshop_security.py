"""Nuvemshop credential encryption utilities.

Uses Fernet symmetric encryption.
Key is loaded from NUVEMSHOP_ENCRYPTION_KEY environment variable.
"""
import os

from cryptography.fernet import Fernet, InvalidToken


class NuvemshopEncryptionError(Exception):
    pass


def _get_fernet() -> Fernet:
    key = os.getenv("NUVEMSHOP_ENCRYPTION_KEY", "")
    if not key:
        raise NuvemshopEncryptionError(
            "NUVEMSHOP_ENCRYPTION_KEY environment variable is not set"
        )
    try:
        return Fernet(key.encode())
    except Exception as exc:
        raise NuvemshopEncryptionError(
            f"Invalid NUVEMSHOP_ENCRYPTION_KEY: {exc}"
        ) from exc


def encrypt_secret(value: str) -> str:
    """Encrypt a secret value."""
    f = _get_fernet()
    try:
        return f.encrypt(value.encode()).decode()
    except Exception as exc:
        raise NuvemshopEncryptionError(
            f"Failed to encrypt: {exc}"
        ) from exc


def decrypt_secret(encrypted: str) -> str:
    """Decrypt a secret value."""
    f = _get_fernet()
    try:
        return f.decrypt(encrypted.encode()).decode()
    except InvalidToken as exc:
        raise NuvemshopEncryptionError(
            "Failed to decrypt: invalid token"
        ) from exc
    except Exception as exc:
        raise NuvemshopEncryptionError(
            f"Failed to decrypt: {exc}"
        ) from exc
