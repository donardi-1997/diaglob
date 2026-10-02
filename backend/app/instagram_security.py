import os

from cryptography.fernet import Fernet, InvalidToken


def _get_fernet() -> Fernet:
    key = os.getenv("INSTAGRAM_TOKEN_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("INSTAGRAM_TOKEN_ENCRYPTION_KEY is not configured")
    try:
        return Fernet(key.encode("utf-8"))
    except Exception as exc:
        raise RuntimeError("INSTAGRAM_TOKEN_ENCRYPTION_KEY is invalid") from exc


def encrypt_instagram_secret(value: str) -> str:
    if not value:
        raise ValueError("Cannot encrypt an empty Instagram secret")
    return _get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_instagram_secret(value: str) -> str:
    if not value:
        raise ValueError("Cannot decrypt an empty Instagram secret")
    try:
        return _get_fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Unable to decrypt Instagram secret") from exc
