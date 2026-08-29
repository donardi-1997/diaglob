import os

import httpx


GRAPH_API_VERSION = os.getenv(
    "WHATSAPP_GRAPH_API_VERSION",
    "v21.0",
)

GRAPH_API_BASE = (
    "https://graph.facebook.com"
)


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

    except httpx.HTTPError as exc:
        raise RuntimeError(
            "Unable to reach WhatsApp "
            "Graph API"
        ) from exc

    if response.status_code not in {
        200,
        201,
    }:
        raise RuntimeError(
            (
                "WhatsApp Graph API "
                "rejected the request "
                f"(HTTP {response.status_code})"
            )
        )

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
