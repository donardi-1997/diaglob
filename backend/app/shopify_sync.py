from datetime import datetime

from sqlalchemy.orm import Session

from .models import (
    CommerceConnection,
    Product,
    ProductVariant,
)
from .shopify_client import (
    ShopifyAuthError,
    ShopifyGraphQLClient,
    ShopifyGraphQLError,
    ShopifyAPIError,
)
from .shopify_security import (
    decrypt_shopify_secret,
)


SHOPIFY_TEST_QUERY = """
query {
  shop {
    name
    myshopifyDomain
    currencyCode
  }
}
"""


SHOPIFY_PRODUCTS_QUERY = """
query ($cursor: String) {
  products(
    first: 50
    after: $cursor
  ) {
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      node {
        id
        title
        handle
        status
        descriptionHtml
        images(first: 1) {
          edges {
            node {
              url
            }
          }
        }
        variants(first: 100) {
          edges {
            node {
              id
              title
              sku
              price
              compareAtPrice
              inventoryQuantity
              availableForSale
            }
          }
        }
      }
    }
  }
}
"""


def _extract_gid_id(
    gid: str | None,
) -> str | None:
    if not gid:
        return None

    parts = gid.rsplit("/", 1)

    if len(parts) == 2:
        return parts[1]

    return gid


def test_shopify_connection(
    connection: CommerceConnection,
) -> dict:
    token = decrypt_shopify_secret(
        connection.access_token_encrypted
    )

    client = ShopifyGraphQLClient(
        shop_domain=connection.external_store_url,
        access_token=token,
    )

    data = client.query(SHOPIFY_TEST_QUERY)

    shop = data.get("shop") or {}

    return {
        "connected": True,
        "shop_name": shop.get("name", ""),
        "shop_domain": (
            connection.external_store_url
        ),
        "currency": shop.get(
            "currencyCode", ""
        ),
    }


def _upsert_product(
    db: Session,
    *,
    organization_id: int,
    store_id: int,
    shopify_product_id: str,
    title: str,
    handle: str | None,
    description: str,
    image_url: str | None,
    status: str,
) -> tuple[Product, bool]:
    existing = (
        db.query(Product)
        .filter(
            Product.store_id == store_id,
            Product.shopify_product_id
            == shopify_product_id,
        )
        .first()
    )

    is_active = status == "ACTIVE"

    if existing:
        existing.title = title
        existing.handle = handle or ""
        existing.description = (
            description or ""
        )
        existing.image_url = image_url
        existing.active = is_active
        existing.updated_at = (
            datetime.utcnow()
        )

        return existing, False

    product = Product(
        organization_id=organization_id,
        store_id=store_id,
        shopify_product_id=(
            shopify_product_id
        ),
        title=title,
        handle=handle or "",
        description=description or "",
        image_url=image_url,
        active=is_active,
    )

    db.add(product)
    db.flush()

    return product, True


def _upsert_variant(
    db: Session,
    *,
    product_id: int,
    shopify_variant_id: str,
    title: str,
    sku: str | None,
    price: float,
    compare_at_price: float | None,
    inventory_quantity: int,
    available: bool,
    currency: str,
) -> ProductVariant:
    existing = (
        db.query(ProductVariant)
        .filter(
            ProductVariant.product_id
            == product_id,
            ProductVariant.shopify_variant_id
            == shopify_variant_id,
        )
        .first()
    )

    if existing:
        existing.title = title
        existing.sku = sku or ""
        existing.price = price
        existing.inventory_quantity = (
            inventory_quantity
        )
        existing.available = available
        existing.updated_at = (
            datetime.utcnow()
        )

        return existing

    variant = ProductVariant(
        product_id=product_id,
        shopify_variant_id=(
            shopify_variant_id
        ),
        title=title,
        sku=sku or "",
        price=price,
        currency=currency,
        inventory_quantity=(
            inventory_quantity
        ),
        available=available,
    )

    db.add(variant)
    db.flush()

    return variant


def sync_shopify_products(
    db: Session,
    connection: CommerceConnection,
) -> dict:
    token = decrypt_shopify_secret(
        connection.access_token_encrypted
    )

    client = ShopifyGraphQLClient(
        shop_domain=connection.external_store_url,
        access_token=token,
    )

    store = connection.store

    currency = (
        (store.currency or "USD").upper()
        if store
        else "USD"
    )

    created = 0
    updated = 0
    failed = 0
    fetched = 0
    cursor = None

    while True:
        variables = {}

        if cursor:
            variables["cursor"] = cursor

        try:
            data = client.query(
                SHOPIFY_PRODUCTS_QUERY,
                variables,
            )
        except (
            ShopifyAuthError,
            ShopifyGraphQLError,
            ShopifyAPIError,
        ):
            raise

        products_data = (
            data.get("products") or {}
        )

        page_info = (
            products_data.get("pageInfo") or {}
        )

        edges = (
            products_data.get("edges") or []
        )

        for edge in edges:
            node = edge.get("node") or {}

            shopify_pid = _extract_gid_id(
                node.get("id")
            )

            if not shopify_pid:
                failed += 1
                continue

            fetched += 1

            title = node.get("title", "")

            handle = node.get("handle")

            status = node.get(
                "status", "ACTIVE"
            )

            description_html = node.get(
                "descriptionHtml", ""
            )

            images = (
                node.get("images") or {}
            ).get("edges") or []

            image_url = None

            if images:
                image_url = (
                    images[0]
                    .get("node", {})
                    .get("url")
                )

            try:
                product, product_created = _upsert_product(
                    db,
                    organization_id=(
                        connection.organization_id
                    ),
                    store_id=(
                        connection.store_id
                    ),
                    shopify_product_id=(
                        shopify_pid
                    ),
                    title=title,
                    handle=handle,
                    description=(
                        description_html
                    ),
                    image_url=image_url,
                    status=status,
                )

                if product_created:
                    created += 1
                else:
                    updated += 1

            except Exception:
                failed += 1
                continue

            variants_data = (
                node.get("variants") or {}
            ).get("edges") or []

            for vedge in variants_data:
                vnode = (
                    vedge.get("node") or {}
                )

                shopify_vid = _extract_gid_id(
                    vnode.get("id")
                )

                if not shopify_vid:
                    continue

                try:
                    price_str = (
                        vnode.get(
                            "price", "0"
                        )
                        or "0"
                    )

                    price = float(price_str)

                    cap_str = vnode.get(
                        "compareAtPrice"
                    )

                    compare_at_price = (
                        float(cap_str)
                        if cap_str
                        else None
                    )

                    inv_qty = int(
                        vnode.get(
                            "inventoryQuantity",
                            0,
                        )
                        or 0
                    )

                    _upsert_variant(
                        db,
                        product_id=product.id,
                        shopify_variant_id=(
                            shopify_vid
                        ),
                        title=vnode.get(
                            "title", ""
                        ),
                        sku=vnode.get("sku"),
                        price=price,
                        compare_at_price=(
                            compare_at_price
                        ),
                        inventory_quantity=(
                            inv_qty
                        ),
                        available=vnode.get(
                            "availableForSale",
                            True,
                        ),
                        currency=currency,
                    )

                except Exception:
                    failed += 1

        has_next = page_info.get(
            "hasNextPage", False
        )

        cursor = page_info.get("endCursor")

        if not has_next or not cursor:
            break

    connection.last_sync_at = (
        datetime.utcnow()
    )
    connection.last_error = None

    db.commit()

    # Analytics: catalog synced
    from .services.product_analytics import track_catalog_synced
    if store:
        track_catalog_synced(
            user_id=0,  # No user context in sync
            organization_id=connection.organization_id,
            store_id=connection.store_id,
            products_synced=created + updated,
        )

    return {
        "ok": True,
        "fetched": fetched,
        "created": created,
        "updated": updated,
        "failed": failed,
    }
