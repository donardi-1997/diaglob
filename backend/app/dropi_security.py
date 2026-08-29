import os

from cryptography.fernet import (
    Fernet,
    InvalidToken,
)


def _get_fernet() -> Fernet:
    key = os.getenv(
        "DROPPI_TOKEN_ENCRYPTION_KEY"
    )

    if not key:
        raise RuntimeError(
            "DROPPI_TOKEN_ENCRYPTION_KEY "
            "is not configured"
        )

    try:
        return Fernet(
            key.encode("utf-8")
        )

    except Exception as exc:
        raise RuntimeError(
            "DROPPI_TOKEN_ENCRYPTION_KEY "
            "is invalid"
        ) from exc


def encrypt_dropi_secret(
    value: str,
) -> str:
    if not value:
        raise ValueError(
            "Cannot encrypt an empty Dropi secret"
        )

    encrypted = (
        _get_fernet()
        .encrypt(
            value.encode("utf-8")
        )
    )

    return encrypted.decode("utf-8")


def decrypt_dropi_secret(
    value: str,
) -> str:
    if not value:
        raise ValueError(
            "Cannot decrypt an empty Dropi secret"
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
            "Unable to decrypt Dropi secret"
        ) from exc

    return decrypted.decode("utf-8")
