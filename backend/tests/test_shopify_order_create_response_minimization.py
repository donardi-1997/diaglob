"""Ensure DIAGLOB only asks Shopify for fields consumed after orderCreate.

Input PII (phone/address/email) is managed independently by the authorized
checkout flow; this test constrains the returned GraphQL selection set.
"""
import re

from app.shopify_client import ORDER_CREATE_MUTATION


def test_order_create_response_requests_only_order_identifiers():
    selected = re.search(
        r"orderCreate\s*\(order:\s*\$order\)\s*\{\s*order\s*\{([^{}]*)\}",
        ORDER_CREATE_MUTATION,
        re.DOTALL,
    )
    assert selected is not None
    assert selected.group(1).split() == ["id", "name"]
    assert "userErrors" in ORDER_CREATE_MUTATION
