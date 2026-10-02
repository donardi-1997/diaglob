"""Minimal Meta Graph client for Instagram Messaging."""

from __future__ import annotations

import os
from typing import Any

import requests


class InstagramClientError(RuntimeError):
    pass


def _version() -> str:
    return os.getenv("META_GRAPH_API_VERSION", "v21.0").strip() or "v21.0"


def _url(path: str) -> str:
    return f"https://graph.facebook.com/{_version()}/{path.lstrip('/')}"


def get_account(access_token: str, instagram_account_id: str) -> dict[str, Any]:
    try:
        response = requests.get(
            _url(instagram_account_id),
            params={
                "fields": "id,username,name",
                "access_token": access_token,
            },
            timeout=15,
        )
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise InstagramClientError("Instagram account validation failed") from exc

    if response.status_code >= 400 or data.get("error"):
        raise InstagramClientError("Instagram rejected the account or token")
    if str(data.get("id") or "") != str(instagram_account_id):
        raise InstagramClientError("Instagram account id mismatch")
    return data


def send_message(
    access_token: str,
    *,
    instagram_account_id: str,
    recipient_id: str,
    text: str,
) -> dict[str, Any]:
    try:
        response = requests.post(
            _url(f"{instagram_account_id}/messages"),
            params={"access_token": access_token},
            json={
                "recipient": {"id": recipient_id},
                "message": {"text": text},
            },
            timeout=15,
        )
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise InstagramClientError("Instagram send request failed") from exc

    if response.status_code >= 400 or data.get("error"):
        raise InstagramClientError("Instagram message delivery failed")
    return data
