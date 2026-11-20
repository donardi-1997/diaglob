"""Pause automated WhatsApp sends while a connection's channel is unusable.

When Meta rejects a send because of the channel itself (expired or revoked
token, missing permission, locked or unpaid account), every other send on
that connection will fail the same way. Instead of burning each recipient's
attempts one by one, the automation engines:

1. mark the connection paused (``last_error`` + ``updated_at``),
2. defer every recipient of that connection without calling Meta and without
   consuming attempts, probing again once the pause window ends,
3. give up a recipient only after ``CHANNEL_GIVE_UP`` so stale messages are
   not sent days later.

The connection keeps ``status == "connected"`` on purpose: inbound webhooks
only accept connected connections, and customer messages must keep arriving
while the merchant fixes the token. Reconnecting creates a new connection
row, which starts with ``last_error = None``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from ..models import WhatsAppConnection

logger = logging.getLogger(__name__)

CHANNEL_PAUSE_PREFIX = "WHATSAPP_CHANNEL_PAUSED:"
CHANNEL_PAUSE = timedelta(minutes=30)
CHANNEL_GIVE_UP = timedelta(hours=24)
CHANNEL_UNAVAILABLE_CODE = "whatsapp_channel_unavailable"


def channel_pause_code(connection: WhatsAppConnection) -> str | None:
    """Return the Meta error code that paused this connection, if any."""
    last_error = connection.last_error or ""
    if not last_error.startswith(CHANNEL_PAUSE_PREFIX):
        return None
    return last_error[len(CHANNEL_PAUSE_PREFIX):] or "unknown"


def channel_resume_at(connection: WhatsAppConnection, now: datetime) -> datetime | None:
    """When sends may probe Meta again, or None if the channel is not paused."""
    if channel_pause_code(connection) is None:
        return None
    resume_at = (connection.updated_at or now) + CHANNEL_PAUSE
    return resume_at if resume_at > now else None


def mark_channel_paused(connection: WhatsAppConnection, code: str, now: datetime) -> None:
    """Pause automated sends on this connection. The caller commits."""
    if channel_pause_code(connection) is None:
        logger.warning(
            "whatsapp_channel_paused connection_id=%s store_id=%s code=%s",
            connection.id, connection.store_id, code,
        )
    connection.last_error = f"{CHANNEL_PAUSE_PREFIX}{code}"[:255]
    connection.updated_at = now


def clear_channel_pause(connection: WhatsAppConnection, now: datetime) -> None:
    """A send succeeded: the channel works again. The caller commits."""
    if channel_pause_code(connection) is None:
        return
    logger.info(
        "whatsapp_channel_resumed connection_id=%s store_id=%s",
        connection.id, connection.store_id,
    )
    connection.last_error = None
    connection.updated_at = now


def should_give_up(started_at: datetime | None, now: datetime) -> bool:
    return started_at is not None and now - started_at >= CHANNEL_GIVE_UP
