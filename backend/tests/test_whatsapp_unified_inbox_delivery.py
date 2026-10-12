"""Unified inbox must never fake delivery of a WhatsApp reply."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.conversation_service import (
    ConversationDeliveryError,
    create_message_with_ai,
)
from app.services.whatsapp_service import (
    WhatsAppNotConnectedError,
    WhatsAppSendError,
)


def _conversation():
    return SimpleNamespace(
        id=33, organization_id=71, store_id=41,
        channel="WhatsApp", mode="human",
    )


def test_human_reply_routes_to_real_whatsapp_adapter_without_local_fallback():
    db = MagicMock()
    with patch(
        "app.services.whatsapp_service.send_message",
        return_value={"ok": True, "message_id": 9},
    ) as sender:
        result = create_message_with_ai(
            db=db, conversation=_conversation(), sender="human", text="Hola",
        )
    sender.assert_called_once_with(
        db=db, organization_id=71, conversation_id=33, text="Hola",
    )
    assert result == {"ok": True, "message_id": 9}
    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize("failure,code", [
    (WhatsAppNotConnectedError("WHATSAPP_NOT_CONNECTED"), "WHATSAPP_NOT_CONNECTED"),
    (WhatsAppSendError("WHATSAPP_SERVICE_WINDOW_CLOSED"), "WHATSAPP_SERVICE_WINDOW_CLOSED"),
    (WhatsAppSendError("WHATSAPP_SEND_FAILED"), "WHATSAPP_SEND_FAILED"),
])
def test_unified_inbox_failures_never_save_undelivered_message(failure, code):
    db = MagicMock()
    with patch("app.services.whatsapp_service.send_message", side_effect=failure):
        with pytest.raises(ConversationDeliveryError, match=code):
            create_message_with_ai(
                db=db, conversation=_conversation(), sender="human", text="Hola",
            )
    db.add.assert_not_called()
    db.commit.assert_not_called()


