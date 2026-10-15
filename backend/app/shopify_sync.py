from ..shopify_token_lifecycle import connection_access_token
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
from .shopify_oauth import normalize_shop_domain
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
    first: 5
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
          pageInfo {
            hasNextPage
            endCursor
          }
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



SHOPIFY_PRODUCT_VARIANTS_QUERY = """
query DiaglobProductVariants($productId: ID!, $cursor: String) {
  product(id: $productId) {
    variants(first: 100, after: $cursor) {
      pageInfo {
        hasNextPage
        endCursor
      }
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
"""


def _all_variant_edges(client: ShopifyGraphQLClient, node: dict) -> list[dict]:
    """Fetch every variant page before mutating this product.

    Do not silently treat a truncated response, repeated cursor, or missing
    product as a completed catalog. Existing mock responses without pageInfo
    represent one complete page for backward compatibility.
    """
    connection = node.get("variants") or {}
    edges = list(connection.get("edges") or [])
    info = connection.get("pageInfo") or {}
    seen_cursors: set[str] = set()
    pages = 0
    while info.get("hasNextPage") is True:
        cursor = info.get("endCursor")
        if not cursor or cursor in seen_cursors or pages >= 100:
            raise ValueError("SHOPIFY_VARIANT_PAGINATION_INCOMPLETE")
        seen_cursors.add(cursor)
        pages += 1
        result = client.query(
            SHOPIFY_PRODUCT_VARIANTS_QUERY,
            {"productId": node["id"], "cursor": cursor},
        )
        product = result.get("product")
        if not isinstance(product, dict):
            raise ValueError("SHOPIFY_VARIANT_PRODUCT_NOT_FOUND")
        connection = product.get("variants") or {}
        edges.extend(connection.get("edges") or [])
        info = connection.get("pageInfo") or {}
    return edges


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
    token = connection_access_token(connection)

    client = ShopifyGraphQLClient(
        shop_domain=connection.external_store_url,
        access_token=token,
    )

    data = client.query(SHOPIFY_TEST_QUERY)

    # A token response is not proof that the intended store is connected
    # unless Shopify returns a matching canonical myshopifyDomain.
    if not isinstance(data, dict) or not isinstance(data.get("shop"), dict):
        raise ShopifyAPIError("SHOPIFY_SHOP_IDENTITY_UNVERIFIED")
    shop = data["shop"]
    provider_domain = shop.get("myshopifyDomain")
    try:
        expected = normalize_shop_domain(connection.external_store_url)
        actual = normalize_shop_domain(provider_domain)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ShopifyAPIError("SHOPIFY_SHOP_IDENTITY_UNVERIFIED") from exc
    if actual != expected:
        raise ShopifyAuthError("SHOPIFY_SHOP_IDENTITY_MISMATCH")

    return {
        "connected": True,
        "shop_name": shop.get("name") or "",
        "shop_domain": actual,
        "currency": shop.get("currencyCode") or "",
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
        existing.currency = currency
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
    token = connection_access_token(connection)

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
    seen_page_cursors: set[str] = set()
    seen_product_ids: set[str] = set()

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
            seen_product_ids.add(shopify_pid)

            title = node.get("title", "")

            handle = node.get("handle")

            status = node.get("status", "")

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
                variants_data = _all_variant_edges(client, node)
            except (ShopifyAuthError, ShopifyGraphQLError, ShopifyAPIError):
                raise
            except (KeyError, TypeError, ValueError):
                failed += 1
                continue

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

            seen_variant_ids: set[str] = set()
            variant_failures = 0
            for vedge in variants_data:
                vnode = (
                    vedge.get("node") or {}
                )

                shopify_vid = _extract_gid_id(
                    vnode.get("id")
                )

                if not shopify_vid:
                    failed += 1
                    variant_failures += 1
                    continue
                if shopify_vid in seen_variant_ids:
                    continue
                seen_variant_ids.add(shopify_vid)

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
                        available=(
                            status == "ACTIVE"
                            and price > 0
                            and vnode.get("availableForSale") is True
                        ),
                        currency=currency,
                    )

                except Exception:
                    failed += 1
                    variant_failures += 1

            # Only retire variants if the complete Shopify variant connection
            # was fetched and each returned variant was successfully written.
            if not variant_failures:
                stale_variants = (
                    db.query(ProductVariant)
                    .filter(
                        ProductVariant.product_id == product.id,
                        ProductVariant.shopify_variant_id.isnot(None),
                    )
                    .all()
                )
                for old_variant in stale_variants:
                    if old_variant.shopify_variant_id not in seen_variant_ids:
                        old_variant.available = False

        has_next = page_info.get(
            "hasNextPage", False
        )

        cursor = page_info.get("endCursor")

        if not has_next:
            break
        if not cursor or cursor in seen_page_cursors:
            failed += 1
            break
        seen_page_cursors.add(cursor)

    # Never retire products on an incomplete scan; successful scans can
    # disable removed Shopify products without touching manual catalog entries.
    if not failed:
        for old_product in (
            db.query(Product)
            .filter(
                Product.store_id == connection.store_id,
                Product.organization_id == connection.organization_id,
                Product.shopify_product_id.isnot(None),
            )
            .all()
        ):
            if old_product.shopify_product_id not in seen_product_ids:
                old_product.active = False
                for old_variant in old_product.variants:
                    old_variant.available = False
        connection.last_sync_at = datetime.utcnow()
        connection.last_error = None
    else:
        connection.last_error = "SHOPIFY_PRODUCTS_PARTIAL_SYNC"

    db.commit()

    # Analytics: catalog synced
    from .services.product_analytics import track_catalog_synced
    if store and not failed:
        track_catalog_synced(
            user_id=0,  # No user context in sync
            organization_id=connection.organization_id,
            store_id=connection.store_id,
            products_synced=created + updated,
        )

    return {
        "ok": failed == 0,
        "fetched": fetched,
        "created": created,
        "updated": updated,
        "failed": failed,
    }
