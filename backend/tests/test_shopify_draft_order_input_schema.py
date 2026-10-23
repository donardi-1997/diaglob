"""Regression tests for Shopify's GraphQL DraftOrderInput contract.

These tests are synthetic only and never call Shopify Admin mutations.
The schema intentionally does not contain a top-level "name" input field.
"""

from app.shopify_orders import build_draft_order_input


def test_draft_order_customer_name_is_a_custom_attribute_not_an_invalid_field():
    line_items = [{"variantId": "gid://shopify/ProductVariant/123", "quantity": 2}]
    result = build_draft_order_input(
        line_items=line_items,
        note="Synthetic checkout",
        customer_email="buyer@example.invalid",
        customer_name="  Ejemplo Comprador  ",
    )

    assert result == {
        "lineItems": line_items,
        "note": "Synthetic checkout",
        "email": "buyer@example.invalid",
        "customAttributes": [
            {"key": "diaglob_customer_name", "value": "Ejemplo Comprador"},
        ],
    }
    assert "name" not in result


def test_draft_order_omits_unprovided_pii_and_optional_fields():
    line_items = [{"variantId": "gid://shopify/ProductVariant/321", "quantity": 1}]
    result = build_draft_order_input(
        line_items=line_items,
        note=None,
        customer_email=None,
        customer_name="  ",
    )
    assert result == {"lineItems": line_items}
