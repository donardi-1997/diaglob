import os

from cryptography.fernet import Fernet, InvalidToken


def _get_fernet() -> Fernet:
    key = os.getenv("TELEGRAM_TOKEN_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("TELEGRAM_TOKEN_ENCRYPTION_KEY is not configured")
    try:
        return Fernet(key.encode("utf-8"))
    except Exception as exc:
        raise RuntimeError("TELEGRAM_TOKEN_ENCRYPTION_KEY is invalid") from exc


def encrypt_telegram_secret(value: str) -> str:
    if not value:
        raise ValueError("Cannot encrypt an empty Telegram secret")
    return _get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_telegram_secret(value: str) -> str:
    if not value:
        raise ValueError("Cannot decrypt an empty Telegram secret")
    try:
        return _get_fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Unable to decrypt Telegram secret") from exc
