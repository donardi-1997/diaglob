"""Shopify checkout reference guards using only synthetic payloads.

A buyer-provided note attribute is not proof of an order. Invalid markers
and order identifiers must be rejected before SQL or any external call.
"""
import pytest

from app.services.shopify_chat_draft_reconciliation import (
    _candidate_reference,
    verified_chat_draft_for_order,
)

VALID = {"name": "diaglob_checkout_ref", "value": "chat-checkout:987:123"}


@pytest.mark.parametrize("attributes,expected", [
    ([VALID], "chat-checkout:987:123"),
    ([{"name": "other", "value": "x"}, VALID], "chat-checkout:987:123"),
    ([{"name": "diaglob_checkout_ref", "value": "chat-checkout:0001:0002"}], "chat-checkout:0001:0002"),
    (None, None),
    ({}, None),
    ("chat-checkout:987:123", None),
    ([], None),
    ([None, 42, "text", {"name": "other", "value": "x"}], None),
    ([{"name": "diaglob_checkout_ref"}], None),
    ([{"name": "DIAGLOB_CHECKOUT_REF", "value": "chat-checkout:987:123"}], None),
    ([{"name": "diaglob_checkout_ref", "value": 987}], None),
    ([VALID, VALID], None),
    ([VALID, {"name": "diaglob_checkout_ref", "value": "invalid"}], None),
    ([{"name": "diaglob_checkout_ref", "value": "chat-checkout:987:123\n"}], None),
    ([{"name": "diaglob_checkout_ref", "value": " chat-checkout:987:123"}], None),
    ([{"name": "diaglob_checkout_ref", "value": "chat-checkout:+987:123"}], None),
    ([{"name": "diaglob_checkout_ref", "value": "chat-checkout:987:１２３"}], None),
    ([{"name": "diaglob_checkout_ref", "value": "chat-checkout:987:123:456"}], None),
    ([{"name": "diaglob_checkout_ref", "value": "shopify:987:123"}], None),
])
def test_only_one_exact_checkout_reference_is_accepted(attributes, expected):
    assert _candidate_reference(attributes) == expected


class NoDatabaseQueries:
    def query(self, *args, **kwargs):
        raise AssertionError("Untrusted Shopify identifiers must not reach SQL")


@pytest.mark.parametrize("order_id,attributes", [
    ("", [VALID]),
    ("gid://shopify/Order/456", [VALID]),
    ("-456", [VALID]),
    ("456\n", [VALID]),
    ("４５６", [VALID]),
    ("٤٥٦", [VALID]),
    ("456.0", [VALID]),
    (" 456", [VALID]),
    ("456", [VALID, VALID]),
    ("456", [{"name": "diaglob_checkout_ref", "value": "not-an-app-reference"}]),
    ("456", None),
])
def test_invalid_marker_or_order_id_cannot_trigger_database_lookup(order_id, attributes):
    assert verified_chat_draft_for_order(
        NoDatabaseQueries(),
        connection=object(),
        shopify_order_id=order_id,
        note_attributes=attributes,
    ) is None
