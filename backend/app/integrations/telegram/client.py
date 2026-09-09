"""Small Telegram Bot API client used by the Telegram V1 integration."""

from __future__ import annotations

from typing import Any

import requests


class TelegramClientError(RuntimeError):
    pass


def _call(
    bot_token: str,
    method: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    if not bot_token:
        raise TelegramClientError("Missing Telegram bot token")

    url = f"https://api.telegram.org/bot{bot_token}/{method}"
    try:
        response = requests.post(url, json=payload or {}, timeout=15)
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise TelegramClientError(f"Telegram {method} request failed") from exc

    if response.status_code >= 400 or not data.get("ok"):
        description = str(data.get("description") or "Telegram API error")
        raise TelegramClientError(description)

    return data.get("result")


def get_me(bot_token: str) -> dict[str, Any]:
    result = _call(bot_token, "getMe")
    if not isinstance(result, dict) or not result.get("is_bot"):
        raise TelegramClientError("Token does not belong to a Telegram bot")
    return result


def set_webhook(
    bot_token: str,
    *,
    webhook_url: str,
    secret_token: str,
) -> bool:
    result = _call(
        bot_token,
        "setWebhook",
        {
            "url": webhook_url,
            "secret_token": secret_token,
            "allowed_updates": ["message"],
            "drop_pending_updates": False,
        },
    )
    return result is True


def delete_webhook(bot_token: str) -> bool:
    result = _call(
        bot_token,
        "deleteWebhook",
        {"drop_pending_updates": False},
    )
    return result is True


def send_message(bot_token: str, *, chat_id: int, text: str) -> dict[str, Any]:
    result = _call(
        bot_token,
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
        },
    )
    if not isinstance(result, dict):
        raise TelegramClientError("Telegram sendMessage returned an invalid response")
    return result
