"""Encryption helpers for supplier credentials."""

import os

from cryptography.fernet import Fernet, InvalidToken


def _get_fernet() -> Fernet:
    key = os.getenv("SUPPLIER_TOKEN_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("SUPPLIER_TOKEN_ENCRYPTION_KEY is not configured")

    try:
        return Fernet(key.encode("utf-8"))
    except Exception as exc:
        raise RuntimeError("SUPPLIER_TOKEN_ENCRYPTION_KEY is invalid") from exc


def encrypt_supplier_secret(value: str) -> str:
    if not value:
        raise ValueError("Cannot encrypt an empty supplier secret")
    return _get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_supplier_secret(value: str) -> str:
    if not value:
        raise ValueError("Cannot decrypt an empty supplier secret")

    try:
        decrypted = _get_fernet().decrypt(value.encode("utf-8"))
    except InvalidToken as exc:
        raise RuntimeError("Unable to decrypt supplier secret") from exc

    return decrypted.decode("utf-8")
