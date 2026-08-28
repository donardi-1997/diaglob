import re

from sqlalchemy.orm import Session

from .models import Product


def _normalize(
    value: str | None,
):
    return (
        value
        or ""
    ).strip().lower()


def search_products(
    *,
    db: Session,
    organization_id: int,
    store_id: int,
    query: str,
    limit: int = 5,
):
    normalized_query = _normalize(
        query
    )

    if not normalized_query:
        return []

    words = [
        word
        for word in re.findall(
            r"[a-záéíóúüñ0-9_-]+",
            normalized_query,
        )
        if len(word) >= 2
    ]

    numeric_terms = {
        word
        for word in words
        if word.isdigit()
    }

    products = (
        db.query(Product)
        .filter(
            Product.organization_id
            == organization_id,

            Product.store_id
            == store_id,

            Product.active.is_(True),
        )
        .order_by(
            Product.title
        )
        .all()
    )

    results = []

    for product in products:
        searchable_product = _normalize(
            " ".join(
                [
                    product.title or "",
                    product.description or "",
                    product.vendor or "",
                    product.product_type or "",
                ]
            )
        )

        product_score = sum(
            1
            for word in words
            if word in searchable_product
        )

        variants = []

        for variant in product.variants:
            searchable_variant = _normalize(
                " ".join(
                    [
                        variant.title or "",
                        variant.sku or "",
                        variant.barcode or "",
                    ]
                )
            )

            variant_score = sum(
                1
                for word in words
                if word in searchable_variant
            )

            exact_numeric_match = any(
                term in searchable_variant
                for term in numeric_terms
            )

            total_score = (
                product_score
                + variant_score
                + (
                    5
                    if exact_numeric_match
                    else 0
                )
            )

            if (
                product_score > 0
                or variant_score > 0
            ):
                variants.append(
                    {
                        "id":
                            variant.id,

                        "title":
                            variant.title,

                        "sku":
                            variant.sku,

                        "price":
                            float(
                                variant.price
                            ),

                        "currency":
                            variant.currency,

                        "inventory_quantity":
                            variant.inventory_quantity,

                        "available": (
                            variant.available
                            and
                            variant.inventory_quantity
                            > 0
                        ),

                        "score":
                            total_score,

                        "_exact_numeric_match":
                            exact_numeric_match,
                    }
                )

        if not variants:
            continue

        if numeric_terms:
            exact_variants = [
                variant
                for variant in variants
                if variant[
                    "_exact_numeric_match"
                ]
            ]

            if exact_variants:
                variants = exact_variants

        variants.sort(
            key=lambda item:
                item["score"],
            reverse=True,
        )

        clean_variants = []

        for variant in variants:
            variant = dict(
                variant
            )

            variant.pop(
                "_exact_numeric_match",
                None,
            )

            clean_variants.append(
                variant
            )

        results.append(
            {
                "product_id":
                    product.id,

                "title":
                    product.title,

                "description":
                    product.description,

                "vendor":
                    product.vendor,

                "product_type":
                    product.product_type,

                "image_url":
                    product.image_url,

                "variants":
                    clean_variants,

                "score":
                    max(
                        item["score"]
                        for item
                        in clean_variants
                    ),
            }
        )

    results.sort(
        key=lambda item:
            item["score"],
        reverse=True,
    )

    return results[:limit]
