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
    """Sanitized provider failure with retry-safe classification metadata.

    Categories:
      - ``transient``: nothing was sent; retry later with backoff.
      - ``permanent``: nothing was sent; retrying the same request won't help.
      - ``ambiguous``: Meta may have accepted it; never retry automatically.
      - ``channel``: the whole WhatsApp channel is unusable (expired/revoked
        token, missing permission, locked or unpaid account). Every send on
        this connection will fail until the merchant fixes it, so callers
        pause the connection instead of burning each recipient's attempts.
    """

    def __init__(self, code: str, category: str, message: str):
        super().__init__(message)
        self.code = code
        self.category = category


# Meta Cloud API error codes (error.code in the JSON body). Meta returns many
# retryable conditions with HTTP 400, so the HTTP status alone misclassifies
# throughput limits as permanent and token expiry as a per-recipient failure.
# https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes
_META_TRANSIENT_CODES = frozenset({
    1,       # API unknown
    2,       # API service temporarily unavailable
    4,       # API too many calls (app rate limit)
    17,      # API user too many calls
    80007,   # WABA rate limit reached
    130429,  # Cloud API throughput reached
    131000,  # Something went wrong
    131016,  # Service unavailable
    131048,  # Spam rate limit hit
    131056,  # Business/consumer pair rate limit hit
    133004,  # Server temporarily unavailable
})
_META_CHANNEL_CODES = frozenset({
    0,       # AuthException
    3,       # API method / capability not available
    10,      # Permission denied
    190,     # Access token expired or invalid
    368,     # Temporarily blocked for policy violations
    131031,  # Business account locked
    131042,  # Business eligibility / payment issue
    133010,  # Phone number not registered on Cloud API
})


def _meta_error_code(response: httpx.Response) -> int | None:
    try:
        error = (response.json() or {}).get("error") or {}
        code = error.get("code")
        return int(code) if code is not None else None
    except (ValueError, TypeError, AttributeError):
        return None


def classify_whatsapp_error_response(response: httpx.Response) -> WhatsAppDeliveryError:
    """Turn a non-2xx Graph API response into a sanitized, classified error.

    Never includes the provider body in the message: it can echo phone
    numbers and template content.
    """
    status = response.status_code
    meta_code = _meta_error_code(response)
    if meta_code is not None:
        if meta_code in _META_CHANNEL_CODES or 200 <= meta_code <= 299:
            category = "channel"
        elif meta_code in _META_TRANSIENT_CODES:
            category = "transient"
        else:
            category = "permanent"
        return WhatsAppDeliveryError(
            f"meta_{meta_code}", category,
            f"WhatsApp rejected the request (Meta error {meta_code})",
        )
    if status in (401, 403):
        category = "channel"
    elif status == 429 or status >= 500:
        category = "transient"
    else:
        category = "permanent"
    return WhatsAppDeliveryError(
        f"http_{status}", category, f"WhatsApp rejected the request ({status})",
    )


def send_whatsapp_text_message(
    phone_number_id: str,
    access_token: str,
    to: str,
    text: str,
) -> dict:
    url = f"{GRAPH_API_BASE}/{GRAPH_API_VERSION}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    return _post_whatsapp_message(url, access_token, payload)


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
        # A timeout can happen after Meta accepts the request. Never retry it automatically.
        raise WhatsAppDeliveryError("timeout", "ambiguous", "WhatsApp response timed out") from exc
    except httpx.HTTPError as exc:
        raise WhatsAppDeliveryError("transport_error", "ambiguous", "WhatsApp transport failed") from exc
    if response.status_code not in {200, 201}:
        raise classify_whatsapp_error_response(response)
    try:
        data = response.json()
    except ValueError as exc:
        raise WhatsAppDeliveryError("invalid_response", "ambiguous", "WhatsApp returned an unreadable response") from exc
    messages = data.get("messages") if isinstance(data, dict) else None
    message_id = messages[0].get("id") if messages and isinstance(messages[0], dict) else None
    if not message_id:
        # 2xx without a message id: Meta may or may not have queued it, and
        # without the id we can never match delivery status. Don't record it
        # as sent and don't retry it automatically.
        raise WhatsAppDeliveryError("missing_message_id", "ambiguous", "WhatsApp did not confirm the message")
    return {"message_id": message_id, "response": data}
