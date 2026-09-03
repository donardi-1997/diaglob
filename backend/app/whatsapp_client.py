import os

import httpx


GRAPH_API_VERSION = os.getenv(
    "WHATSAPP_GRAPH_API_VERSION",
    "v21.0",
)

GRAPH_API_BASE = (
    "https://graph.facebook.com"
)


class WhatsAppDeliveryError(RuntimeError):
    """Sanitized provider failure with retry-safe classification metadata."""

    def __init__(self, code: str, category: str, message: str):
        super().__init__(message)
        self.code = code
        self.category = category


def send_whatsapp_text_message(
    phone_number_id: str,
    access_token: str,
    to: str,
    text: str,
) -> dict:
    url = (
        f"{GRAPH_API_BASE}"
        f"/{GRAPH_API_VERSION}"
        f"/{phone_number_id}/messages"
    )

    headers = {
        "Authorization":
            f"Bearer {access_token}",
        "Content-Type":
            "application/json",
    }

    payload = {
        "messaging_product":
            "whatsapp",
        "recipient_type":
            "individual",
        "to":
            to,
        "type":
            "text",
        "text":
            {
                "body": text,
            },
    }

    try:
        response = httpx.post(
            url,
            json=payload,
            headers=headers,
            timeout=20,
        )

    except httpx.ConnectError as exc:
        raise WhatsAppDeliveryError("connect_error", "transient", "WhatsApp connection failed") from exc
    except httpx.TimeoutException as exc:
        # A timeout can happen after Meta accepts the request. Never retry it automatically.
        raise WhatsAppDeliveryError("timeout", "ambiguous", "WhatsApp response timed out") from exc
    except httpx.HTTPError as exc:
        raise WhatsAppDeliveryError("transport_error", "ambiguous", "WhatsApp transport failed") from exc

    if response.status_code not in {
        200,
        201,
    }:
        category = "transient" if response.status_code == 429 or response.status_code >= 500 else "permanent"
        raise WhatsAppDeliveryError(f"http_{response.status_code}", category, f"WhatsApp rejected the request ({response.status_code})")

    data = response.json()

    messages = data.get("messages") or []

    message_id = (
        messages[0].get("id")
        if messages
        else None
    )

    return {
        "message_id": message_id,
        "response": data,
    }
