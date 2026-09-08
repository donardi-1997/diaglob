"""Meta Ads credential encryption utilities.

Uses Fernet symmetric encryption.
Key is loaded from META_ADS_ENCRYPTION_KEY environment variable.
"""
import os

from cryptography.fernet import Fernet, InvalidToken


class MetaAdsEncryptionError(Exception):
    pass


def _get_fernet() -> Fernet:
    key = os.getenv("META_ADS_ENCRYPTION_KEY", "")
    if not key:
        raise MetaAdsEncryptionError(
            "META_ADS_ENCRYPTION_KEY environment variable is not set"
        )
    try:
        return Fernet(key.encode())
    except Exception as exc:
        raise MetaAdsEncryptionError(
            f"Invalid META_ADS_ENCRYPTION_KEY: {exc}"
        ) from exc


def encrypt_secret(value: str) -> str:
    """Encrypt a secret value."""
    f = _get_fernet()
    try:
        return f.encrypt(value.encode()).decode()
    except Exception as exc:
        raise MetaAdsEncryptionError(
            f"Failed to encrypt: {exc}"
        ) from exc


def decrypt_secret(encrypted: str) -> str:
    """Decrypt a secret value."""
    f = _get_fernet()
    try:
        return f.decrypt(encrypted.encode()).decode()
    except InvalidToken as exc:
        raise MetaAdsEncryptionError(
            "Failed to decrypt: invalid token"
        ) from exc
    except Exception as exc:
        raise MetaAdsEncryptionError(
            f"Failed to decrypt: {exc}"
        ) from exc
