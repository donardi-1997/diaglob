"""Conservative purchase checks shared by AI and Shopify order entry points.

Shopify can allow backorders at zero inventory. That permission is not evidence
of supplier stock; no supplier availability is inferred from it.
"""

from decimal import Decimal


def variant_is_purchasable(variant, quantity: int = 1) -> bool:
    product = variant.product
    return bool(
        product is not None
        and product.active
        and Decimal(str(variant.price or 0)) > 0
        and variant.available
        and quantity > 0
        and int(variant.inventory_quantity or 0) >= quantity
    )


def availability_reason(variant) -> str:
    if not variant.product or not variant.product.active:
        return "inactive_product"
    if Decimal(str(variant.price or 0)) <= 0:
        return "invalid_price"
    if not variant.available:
        return "unavailable"
    if int(variant.inventory_quantity or 0) <= 0:
        return "stock_not_verified"
    return "in_stock"
