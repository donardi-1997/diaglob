import os

from cryptography.fernet import (
    Fernet,
    InvalidToken,
)


def _get_fernet() -> Fernet:
    key = os.getenv(
        "GOOGLE_TOKEN_ENCRYPTION_KEY"
    )

    if not key:
        raise RuntimeError(
            "GOOGLE_TOKEN_ENCRYPTION_KEY "
            "is not configured"
        )

    try:
        return Fernet(
            key.encode("utf-8")
        )

    except Exception as exc:
        raise RuntimeError(
            "GOOGLE_TOKEN_ENCRYPTION_KEY "
            "is invalid"
        ) from exc


def encrypt_google_secret(
    value: str,
) -> str:
    if not value:
        raise ValueError(
            "Cannot encrypt an empty secret"
        )

    encrypted = (
        _get_fernet()
        .encrypt(
            value.encode("utf-8")
        )
    )

    return encrypted.decode("utf-8")


def decrypt_google_secret(
    value: str,
) -> str:
    if not value:
        raise ValueError(
            "Cannot decrypt an empty secret"
        )

    try:
        decrypted = (
            _get_fernet()
            .decrypt(
                value.encode("utf-8")
            )
        )

    except InvalidToken as exc:
        raise RuntimeError(
            "Unable to decrypt Google secret"
        ) from exc

    return decrypted.decode("utf-8")
