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


def send_whatsapp_template_message(phone_number_id: str, access_token: str, to: str, template_name: str, language_code: str, components: list[dict] | None = None) -> dict:
    """Send an already-approved Cloud API template; this never creates templates."""
    url = f"{GRAPH_API_BASE}/{GRAPH_API_VERSION}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp", "recipient_type": "individual", "to": to,
        "type": "template",
        "template": {"name": template_name, "language": {"code": language_code}, "components": components or []},
    }
    return _post_whatsapp_message(url, access_token, payload)


def list_whatsapp_templates(business_account_id: str, access_token: str) -> list[dict]:
    """Read-only WABA template inventory used for local status synchronization."""
    url = f"{GRAPH_API_BASE}/{GRAPH_API_VERSION}/{business_account_id}/message_templates"
    headers = {"Authorization": f"Bearer {access_token}"}
    items, seen_urls = [], set()
    for _ in range(100):
        if url in seen_urls:
            raise WhatsAppDeliveryError("template_sync_paging", "permanent", "WhatsApp template sync returned a repeated page")
        seen_urls.add(url)
        try:
            response = httpx.get(url, params={"fields": "id,name,language,status,category,components"} if len(seen_urls) == 1 else None, headers=headers, timeout=20)
        except httpx.HTTPError as exc:
            raise WhatsAppDeliveryError("template_sync_transport", "transient", "WhatsApp template sync failed") from exc
        if response.status_code != 200:
            category = "transient" if response.status_code == 429 or response.status_code >= 500 else "permanent"
            raise WhatsAppDeliveryError(f"template_sync_http_{response.status_code}", category, "WhatsApp template sync was rejected")
        data = response.json(); items.extend(data.get("data") or [])
        url = (data.get("paging") or {}).get("next")
        if not url:
            return items
    raise WhatsAppDeliveryError("template_sync_paging", "permanent", "WhatsApp template sync exceeded page limit")


def _post_whatsapp_message(url: str, access_token: str, payload: dict) -> dict:
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=20)
    except httpx.ConnectError as exc:
        raise WhatsAppDeliveryError("connect_error", "transient", "WhatsApp connection failed") from exc
    except httpx.TimeoutException as exc:
        raise WhatsAppDeliveryError("timeout", "ambiguous", "WhatsApp response timed out") from exc
    except httpx.HTTPError as exc:
        raise WhatsAppDeliveryError("transport_error", "ambiguous", "WhatsApp transport failed") from exc
    if response.status_code not in {200, 201}:
        category = "transient" if response.status_code == 429 or response.status_code >= 500 else "permanent"
        raise WhatsAppDeliveryError(f"http_{response.status_code}", category, f"WhatsApp rejected the request ({response.status_code})")
    data = response.json()
    messages = data.get("messages") or []
    return {"message_id": messages[0].get("id") if messages else None, "response": data}
