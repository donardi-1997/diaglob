"""Provider-neutral outbound voice-call adapter for Flow Builder."""
from __future__ import annotations

import os
from dataclasses import dataclass

import httpx


class VoiceProviderError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class VoiceProviderConfig:
    url: str
    token: str | None
    callback_url: str


def get_voice_provider_config() -> VoiceProviderConfig | None:
    url = os.getenv("DIAGLOB_VOICE_PROVIDER_URL", "").strip()
    public_api = os.getenv("DIAGLOB_PUBLIC_API_URL", "").strip().rstrip("/")
    callback_url = os.getenv("DIAGLOB_VOICE_CALLBACK_URL", "").strip()
    if not callback_url and public_api:
        callback_url = f"{public_api}/api/voice/callback"
    if not url or not callback_url:
        return None
    return VoiceProviderConfig(
        url=url,
        token=os.getenv("DIAGLOB_VOICE_PROVIDER_TOKEN", "").strip() or None,
        callback_url=callback_url,
    )


def voice_provider_configured() -> bool:
    return (
        get_voice_provider_config() is not None
        and bool(os.getenv("DIAGLOB_VOICE_WEBHOOK_SECRET", "").strip())
    )


def verify_voice_callback_secret(value: str | None) -> bool:
    expected = os.getenv("DIAGLOB_VOICE_WEBHOOK_SECRET", "").strip()
    if not expected or not value:
        return False
    import hmac
    return hmac.compare_digest(expected, value)


def start_voice_call(
    *,
    to: str,
    prompt: str,
    language: str,
    idempotency_key: str,
    metadata: dict,
) -> dict:
    config = get_voice_provider_config()
    if not config:
        raise VoiceProviderError(
            "voice_provider_not_configured",
            "Voice provider URL and callback URL must be configured",
        )

    headers = {
        "Content-Type": "application/json",
        "Idempotency-Key": idempotency_key,
    }
    if config.token:
        headers["Authorization"] = f"Bearer {config.token}"

    try:
        response = httpx.post(
            config.url,
            headers=headers,
            json={
                "to": to,
                "prompt": prompt,
                "language": language,
                "callback_url": config.callback_url,
                "outcomes": ["confirmed", "rejected", "no_answer", "failed"],
                "metadata": metadata,
            },
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        raise VoiceProviderError(
            "voice_provider_unreachable",
            "Voice provider could not be reached",
        ) from exc

    if response.status_code < 200 or response.status_code >= 300:
        raise VoiceProviderError(
            "voice_provider_rejected",
            f"Voice provider returned HTTP {response.status_code}",
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise VoiceProviderError(
            "voice_provider_invalid_response",
            "Voice provider returned invalid JSON",
        ) from exc

    call_id = payload.get("call_id") or payload.get("id")
    if not call_id:
        raise VoiceProviderError(
            "voice_provider_missing_call_id",
            "Voice provider response did not include call_id",
        )

    return {
        "call_id": str(call_id),
        "status": str(payload.get("status") or "queued"),
    }
