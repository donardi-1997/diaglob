"""Human Conversation API must not spoof incoming customer or AI messages."""
import pytest
from pydantic import ValidationError

from app.api.conversations import MessageCreate


def test_conversation_operator_message_defaults_to_human():
    payload = MessageCreate.model_validate({"text": "Hello"})
    assert payload.sender == "human"
    assert payload.text == "Hello"


@pytest.mark.parametrize("sender", [
    "customer",
    "ai",
    "bot",
    "system",
    "human ",
    None,
])
def test_conversation_operator_rejects_spoofed_message_origin(sender):
    with pytest.raises(ValidationError):
        MessageCreate.model_validate({"text": "spoof", "sender": sender})


def test_conversation_operator_accepts_only_explicit_human_origin():
    assert MessageCreate.model_validate(
        {"text": "Hi there", "sender": "human"}
    ).sender == "human"
