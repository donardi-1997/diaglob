import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import (
    app,
    get_current_membership,
    get_current_user,
)
from app.models import (
    CommerceConnection,
    Order,
    OrderItem,
    Organization,
    OrganizationMembership,
    Product,
    ProductVariant,
    Store,
    User,
)

SQLALCHEMY_TEST_DATABASE_URL = (
    "sqlite:///./test_shopify.db"
)

engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={
        "check_same_thread": False,
    },
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def org(db):
    o = Organization(
        name="Test Org",
        slug="test-org",
        plan="starter",
        subscription_status="active",
    )
    db.add(o)
    db.flush()
    return o


@pytest.fixture()
def user(db, org):
    u = User(
        email="shopify@test.com",
        name="Shopify Tester",
        external_auth_id="test-cognito-sub",
    )
    db.add(u)
    db.flush()

    m = OrganizationMembership(
        user_id=u.id,
        organization_id=org.id,
        role="owner",
    )
    db.add(m)
    db.flush()

    return u


@pytest.fixture()
def membership(db, user, org):
    return (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id
            == user.id,
            OrganizationMembership.organization_id
            == org.id,
        )
        .first()
    )


@pytest.fixture()
def store(db, org):
    s = Store(
        organization_id=org.id,
        name="Shopify Store",
        slug="shopify-store",
        country_code="US",
        currency="USD",
        timezone="America/New_York",
        default_language="en",
    )
    db.add(s)
    db.flush()
    return s


@pytest.fixture()
def shopify_connection(db, org, store):
    conn = CommerceConnection(
        organization_id=org.id,
        store_id=store.id,
        provider="shopify",
        external_store_url=(
            "test-store.myshopify.com"
        ),
        access_token_encrypted=(
            "encrypted_token_placeholder"
        ),
        scopes="read_products,read_inventory",
        status="connected",
    )
    db.add(conn)
    db.flush()
    return conn


@pytest.fixture()
def client(db, membership):
    original_overrides = dict(
        app.dependency_overrides
    )

    def _override_get_db():
        try:
            yield db
        finally:
            pass

    def _override_user():
        return membership.user

    def _override_membership():
        return membership

    app.dependency_overrides[get_db] = (
        _override_get_db
    )
    app.dependency_overrides[
        get_current_user
    ] = _override_user
    app.dependency_overrides[
        get_current_membership
    ] = _override_membership

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    app.dependency_overrides.update(
        original_overrides
    )


MOCK_SHOPIFY_TEST_RESPONSE = {
    "shop": {
        "name": "Test Shop",
        "myshopifyDomain": (
            "test-store.myshopify.com"
        ),
        "currencyCode": "USD",
    }
}


def _mock_product_edge(
    pid="gid://shopify/Product/1",
    title="Test Product",
    handle="test-product",
    status="ACTIVE",
    description="<p>Hello</p>",
    image_url=(
        "https://cdn.example.com/img.jpg"
    ),
    variants=None,
):
    if variants is None:
        variants = [
            {
                "id": (
                    "gid://shopify/"
                    "ProductVariant/101"
                ),
                "title": "Default",
                "sku": "SKU-001",
                "price": "29.99",
                "compareAtPrice": None,
                "inventoryQuantity": 10,
                "available": True,
            }
        ]

    return {
        "node": {
            "id": pid,
            "title": title,
            "handle": handle,
            "status": status,
            "descriptionHtml": description,
            "images": {
                "edges": [
                    {
                        "node": {
                            "url": image_url,
                        }
                    }
                ]
                if image_url
                else []
            },
            "variants": {
                "edges": [
                    {"node": v}
                    for v in variants
                ]
            },
        }
    }


PAGE1 = {
    "products": {
        "pageInfo": {
            "hasNextPage": True,
            "endCursor": "cursor_page1",
        },
        "edges": [
            _mock_product_edge(
                pid=(
                    "gid://shopify/Product/1"
                ),
                title="Shirt",
                handle="shirt",
            ),
            _mock_product_edge(
                pid=(
                    "gid://shopify/Product/2"
                ),
                title="Pants",
                handle="pants",
            ),
        ],
    }
}

PAGE2 = {
    "products": {
        "pageInfo": {
            "hasNextPage": False,
            "endCursor": None,
        },
        "edges": [
            _mock_product_edge(
                pid=(
                    "gid://shopify/Product/3"
                ),
                title="Hat",
                handle="hat",
            ),
        ],
    }
}


class TestShopifyTestConnection:
    def test_connection_ok(
        self,
        client,
        shopify_connection,
        db,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="decrypted",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            return_value=(
                MOCK_SHOPIFY_TEST_RESPONSE
            ),
        ):
            resp = client.post(
                f"/api/stores/"
                f"{shopify_connection.store_id}"
                f"/shopify/test"
            )

            assert resp.status_code == 200

            data = resp.json()

            assert (
                data["connected"] is True
            )
            assert (
                data["shop_name"]
                == "Test Shop"
            )
            assert (
                data["currency"] == "USD"
            )

    def test_connection_not_connected(
        self,
        client,
        store,
        db,
    ):
        resp = client.post(
            f"/api/stores/"
            f"{store.id}/shopify/test"
        )

        assert resp.status_code == 404

    def test_token_never_in_response(
        self,
        client,
        shopify_connection,
        db,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="secret12345",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            return_value=(
                MOCK_SHOPIFY_TEST_RESPONSE
            ),
        ):
            resp = client.post(
                f"/api/stores/"
                f"{shopify_connection.store_id}"
                f"/shopify/test"
            )

            assert (
                "secret12345"
                not in resp.text
            )
            assert (
                "encrypted_token_placeholder"
                not in resp.text
            )

    def test_cross_tenant_blocked(
        self,
        client,
        shopify_connection,
        db,
        org,
    ):
        other_org = Organization(
            name="Other Org",
            slug="other-cross",
            plan="starter",
            subscription_status="active",
        )
        db.add(other_org)
        db.flush()

        other_user = User(
            email="other@test.com",
            name="Other",
            external_auth_id="other-cognito-sub",
        )
        db.add(other_user)
        db.flush()

        other_m = OrganizationMembership(
            user_id=other_user.id,
            organization_id=other_org.id,
            role="owner",
        )
        db.add(other_m)
        db.flush()

        app.dependency_overrides[
            get_current_user
        ] = lambda: other_user
        app.dependency_overrides[
            get_current_membership
        ] = lambda: other_m

        try:
            resp = client.post(
                f"/api/stores/"
                f"{shopify_connection.store_id}"
                f"/shopify/test"
            )

            assert (
                resp.status_code == 404
            )
        finally:
            app.dependency_overrides.pop(
                get_current_user, None
            )
            app.dependency_overrides.pop(
                get_current_membership, None
            )

    def test_expired_token_handled(
        self,
        client,
        shopify_connection,
        db,
    ):
        from app.shopify_client import (
            ShopifyAuthError,
        )

        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="expired",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=ShopifyAuthError(
                "Invalid access token"
            ),
        ):
            resp = client.post(
                f"/api/stores/"
                f"{shopify_connection.store_id}"
                f"/shopify/test"
            )

            assert (
                resp.status_code == 401
            )

            data = resp.json()

            assert (
                data["detail"]["connected"]
                is False
            )

    def test_graphql_errors_sanitized(
        self,
        client,
        shopify_connection,
        db,
    ):
        from app.shopify_client import (
            ShopifyGraphQLError,
        )

        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=ShopifyGraphQLError(
                "GraphQL error"
            ),
        ):
            resp = client.post(
                f"/api/stores/"
                f"{shopify_connection.store_id}"
                f"/shopify/test"
            )

            assert (
                resp.status_code == 502
            )

    def test_sync_not_connected(
        self,
        client,
        store,
        db,
    ):
        resp = client.post(
            f"/api/stores/"
            f"{store.id}"
            f"/shopify/sync/products"
        )

        assert resp.status_code == 404


class TestShopifySyncProducts:
    def test_sync_creates_products(
        self,
        client,
        shopify_connection,
        db,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            resp = client.post(
                f"/api/stores/"
                f"{shopify_connection.store_id}"
                f"/shopify/sync/products"
            )

            assert resp.status_code == 200

            data = resp.json()

            assert data["ok"] is True
            assert data["fetched"] == 3
            assert data["created"] == 3
            assert data["updated"] == 0
            assert data["failed"] == 0

        products = (
            db.query(Product)
            .filter(
                Product.store_id
                == shopify_connection.store_id,
            )
            .all()
        )

        assert len(products) == 3

    def test_second_sync_updates(
        self,
        client,
        shopify_connection,
        db,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{shopify_connection.store_id}"
                f"/shopify/sync/products"
            )

        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            resp = client.post(
                f"/api/stores/"
                f"{shopify_connection.store_id}"
                f"/shopify/sync/products"
            )

            assert resp.status_code == 200

            data = resp.json()

            assert data["ok"] is True
            assert data["created"] == 0
            assert data["updated"] == 3

    def test_store_isolation(
        self,
        client,
        shopify_connection,
        db,
        org,
    ):
        other_org = Organization(
            name="Other",
            slug="other-iso",
        )
        db.add(other_org)
        db.flush()

        other_store = Store(
            organization_id=other_org.id,
            name="Other Store",
            slug="other-store-iso",
            country_code="US",
            currency="USD",
            timezone="UTC",
            default_language="en",
        )
        db.add(other_store)
        db.flush()

        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{shopify_connection.store_id}"
                f"/shopify/sync/products"
            )

        a = (
            db.query(Product)
            .filter(
                Product.store_id
                == shopify_connection.store_id,
            )
            .count()
        )

        b = (
            db.query(Product)
            .filter(
                Product.store_id
                == other_store.id,
            )
            .count()
        )

        assert a == 3
        assert b == 0

    def test_inactive_product(
        self,
        client,
        shopify_connection,
        db,
    ):
        draft = {
            "products": {
                "pageInfo": {
                    "hasNextPage": False,
                    "endCursor": None,
                },
                "edges": [
                    _mock_product_edge(
                        pid=(
                            "gid://shopify/"
                            "Product/10"
                        ),
                        title="Draft",
                        handle="draft",
                        status="DRAFT",
                    )
                ],
            }
        }

        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            return_value=draft,
        ):
            resp = client.post(
                f"/api/stores/"
                f"{shopify_connection.store_id}"
                f"/shopify/sync/products"
            )

            assert resp.status_code == 200

        product = (
            db.query(Product)
            .filter(
                Product.shopify_product_id
                == "10",
            )
            .first()
        )

        assert product is not None
        assert product.active is False

    def test_auth_error_handled(
        self,
        client,
        shopify_connection,
        db,
    ):
        from app.shopify_client import (
            ShopifyAuthError,
        )

        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="bad",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=ShopifyAuthError(
                "Invalid token"
            ),
        ):
            resp = client.post(
                f"/api/stores/"
                f"{shopify_connection.store_id}"
                f"/shopify/sync/products"
            )

            assert resp.status_code == 401

            data = resp.json()

            assert (
                data["detail"]["ok"] is False
            )

    def test_pagination(
        self,
        client,
        shopify_connection,
        db,
    ):
        big_page1 = {
            "products": {
                "pageInfo": {
                    "hasNextPage": True,
                    "endCursor": "c1",
                },
                "edges": [
                    _mock_product_edge(
                        pid=(
                            "gid://shopify/"
                            f"Product/{i}"
                        ),
                        title=f"P{i}",
                        handle=f"p-{i}",
                    )
                    for i in range(1, 51)
                ],
            }
        }

        big_page2 = {
            "products": {
                "pageInfo": {
                    "hasNextPage": False,
                    "endCursor": None,
                },
                "edges": [
                    _mock_product_edge(
                        pid=(
                            "gid://shopify/"
                            "Product/51"
                        ),
                        title="P51",
                        handle="p-51",
                    )
                ],
            }
        }

        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[
                big_page1,
                big_page2,
            ],
        ):
            resp = client.post(
                f"/api/stores/"
                f"{shopify_connection.store_id}"
                f"/shopify/sync/products"
            )

            assert resp.status_code == 200

            data = resp.json()

            assert data["ok"] is True
            assert data["fetched"] == 51
            assert data["created"] == 51

        count = (
            db.query(Product)
            .filter(
                Product.store_id
                == shopify_connection.store_id,
            )
            .count()
        )

        assert count == 51

    def test_commerce_search_sees_products(
        self,
        client,
        shopify_connection,
        db,
        org,
        store,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{shopify_connection.store_id}"
                f"/shopify/sync/products"
            )

        from app.commerce import (
            search_products,
        )

        results = search_products(
            db=db,
            organization_id=org.id,
            store_id=store.id,
            query="shirt",
            limit=5,
        )

        assert len(results) >= 1

        titles = {
            r["title"] for r in results
        }

        assert "Shirt" in titles

    def test_cross_store_search_isolated(
        self,
        client,
        shopify_connection,
        db,
        org,
        store,
    ):
        other_org = Organization(
            name="Other",
            slug="other-search",
        )
        db.add(other_org)
        db.flush()

        other_store = Store(
            organization_id=other_org.id,
            name="Other",
            slug="other-store-search",
            country_code="US",
            currency="USD",
            timezone="UTC",
            default_language="en",
        )
        db.add(other_store)
        db.flush()

        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{shopify_connection.store_id}"
                f"/shopify/sync/products"
            )

        from app.commerce import (
            search_products,
        )

        r_a = search_products(
            db=db,
            organization_id=org.id,
            store_id=store.id,
            query="shirt",
            limit=5,
        )

        r_b = search_products(
            db=db,
            organization_id=other_org.id,
            store_id=other_store.id,
            query="shirt",
            limit=5,
        )

        assert len(r_a) >= 1
        assert len(r_b) == 0


MOCK_DRAFT_ORDER_RESPONSE = {
    "draftOrderCreate": {
        "draftOrder": {
            "id": (
                "gid://shopify/"
                "DraftOrder/9999"
            ),
            "name": "#D1",
            "totalPriceSet": {
                "shopMoney": {
                    "amount": "59.98",
                    "currencyCode": "USD",
                }
            },
            "invoiceUrl": (
                "https://checkout.shopify.com/"
                "draft-invoice/9999"
            ),
            "lineItems": {
                "edges": [
                    {
                        "node": {
                            "id": (
                                "gid://shopify/"
                                "DraftOrderLineItem/1"
                            )
                        }
                    }
                ]
            },
        },
        "userErrors": [],
    }
}


MOCK_DRAFT_ORDER_USER_ERROR = {
    "draftOrderCreate": {
        "draftOrder": None,
        "userErrors": [
            {
                "field": ["lineItems"],
                "message": (
                    "Variant is required"
                ),
            }
        ],
    }
}


class TestShopifyOrders:
    def test_valid_order_creates_draft(
        self,
        client,
        shopify_connection,
        db,
        org,
        store,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        assert variant is not None

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            return_value=(
                MOCK_DRAFT_ORDER_RESPONSE
            ),
        ):
            resp = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 2,
                        }
                    ],
                    "note": "Test order",
                },
            )

            assert resp.status_code == 200

            data = resp.json()

            assert data["ok"] is True
            assert data["status"] == "pending"
            assert (
                data["shopify_draft_order_id"]
                == "gid://shopify/DraftOrder/9999"
            )
            assert (
                data["invoice_url"]
                == (
                    "https://checkout.shopify.com/"
                    "draft-invoice/9999"
                )
            )
            assert data["total_amount"] == 59.98
            assert data["currency"] == "USD"

        order = (
            db.query(Order)
            .filter(
                Order.id == data["order_id"]
            )
            .first()
        )

        assert order is not None
        assert order.source == "shopify"
        assert (
            order.shopify_draft_order_id
            == "gid://shopify/DraftOrder/9999"
        )
        assert order.shopify_order_id is None
        assert order.invoice_url is not None
        assert order.note == "Test order"
        assert order.idempotency_key is None

        items = (
            db.query(OrderItem)
            .filter(
                OrderItem.order_id == order.id
            )
            .all()
        )

        assert len(items) == 1
        assert items[0].quantity == 2
        assert items[0].title == variant.title
        assert items[0].sku == variant.sku

    def test_variant_from_another_store_rejected(
        self,
        client,
        shopify_connection,
        db,
        org,
        store,
    ):
        other_org = Organization(
            name="Other",
            slug="other-order-iso",
        )
        db.add(other_org)
        db.flush()

        other_store = Store(
            organization_id=other_org.id,
            name="Other Store",
            slug="other-store-order-iso",
            country_code="US",
            currency="USD",
            timezone="UTC",
            default_language="en",
        )
        db.add(other_store)
        db.flush()

        other_product = Product(
            organization_id=other_org.id,
            store_id=other_store.id,
            title="Other Product",
            handle="other-product",
        )
        db.add(other_product)
        db.flush()

        other_variant = ProductVariant(
            product_id=other_product.id,
            title="Other Variant",
            price=10.00,
            currency="USD",
        )
        db.add(other_variant)
        db.flush()

        resp = client.post(
            f"/api/stores/"
            f"{store.id}"
            f"/shopify/orders",
            json={
                "items": [
                    {
                        "variant_local_id": (
                            other_variant.id
                        ),
                        "quantity": 1,
                    }
                ],
            },
        )

        assert resp.status_code == 400

    def test_cross_tenant_order_rejected(
        self,
        client,
        shopify_connection,
        db,
        org,
        store,
    ):
        other_org = Organization(
            name="Other",
            slug="other-order-x-tenant",
            plan="starter",
            subscription_status="active",
        )
        db.add(other_org)
        db.flush()

        other_user = User(
            email="other-ot@test.com",
            name="Other",
            external_auth_id="other-ot-cognito",
        )
        db.add(other_user)
        db.flush()

        other_m = OrganizationMembership(
            user_id=other_user.id,
            organization_id=other_org.id,
            role="owner",
        )
        db.add(other_m)
        db.flush()

        app.dependency_overrides[
            get_current_user
        ] = lambda: other_user
        app.dependency_overrides[
            get_current_membership
        ] = lambda: other_m

        try:
            resp = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": 1,
                            "quantity": 1,
                        }
                    ],
                },
            )

            assert resp.status_code == 404
        finally:
            app.dependency_overrides.pop(
                get_current_user, None
            )
            app.dependency_overrides.pop(
                get_current_membership, None
            )

    def test_quantity_zero_rejected(
        self,
        client,
        shopify_connection,
        db,
        store,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        resp = client.post(
            f"/api/stores/"
            f"{store.id}"
            f"/shopify/orders",
            json={
                "items": [
                    {
                        "variant_local_id": (
                            variant.id
                        ),
                        "quantity": 0,
                    }
                ],
            },
        )

        assert resp.status_code == 400

    def test_quantity_negative_rejected(
        self,
        client,
        shopify_connection,
        db,
        store,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        resp = client.post(
            f"/api/stores/"
            f"{store.id}"
            f"/shopify/orders",
            json={
                "items": [
                    {
                        "variant_local_id": (
                            variant.id
                        ),
                        "quantity": -1,
                    }
                ],
            },
        )

        assert resp.status_code == 400

    def test_no_shopify_connection_rejected(
        self,
        client,
        store,
        db,
    ):
        resp = client.post(
            f"/api/stores/"
            f"{store.id}"
            f"/shopify/orders",
            json={
                "items": [
                    {
                        "variant_local_id": 1,
                        "quantity": 1,
                    }
                ],
            },
        )

        assert resp.status_code == 404

    def test_shopify_user_errors_sanitized(
        self,
        client,
        shopify_connection,
        db,
        store,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            return_value=(
                MOCK_DRAFT_ORDER_USER_ERROR
            ),
        ):
            resp = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                },
            )

            assert resp.status_code == 422

    def test_shopify_auth_error_on_order(
        self,
        client,
        shopify_connection,
        db,
        store,
    ):
        from app.shopify_client import (
            ShopifyAuthError,
        )

        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            side_effect=ShopifyAuthError(
                "Invalid token"
            ),
        ):
            resp = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                },
            )

            assert resp.status_code == 401

    def test_token_never_in_order_response(
        self,
        client,
        shopify_connection,
        db,
        store,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="secret_token_abc",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            return_value=(
                MOCK_DRAFT_ORDER_RESPONSE
            ),
        ):
            resp = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                },
            )

            assert (
                "secret_token_abc"
                not in resp.text
            )

    def test_frontend_price_tampering_ignored(
        self,
        client,
        shopify_connection,
        db,
        store,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        original_price = float(
            variant.price
        )

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            return_value=(
                MOCK_DRAFT_ORDER_RESPONSE
            ),
        ):
            resp = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                },
            )

            assert resp.status_code == 200

        order_item = (
            db.query(OrderItem)
            .order_by(
                OrderItem.id.desc()
            )
            .first()
        )

        assert float(
            order_item.unit_price
        ) == original_price

    def test_idempotency_key_returns_same_order(
        self,
        client,
        shopify_connection,
        db,
        store,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        idem_key = "test-idempotency-key-001"

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            return_value=(
                MOCK_DRAFT_ORDER_RESPONSE
            ),
        ):
            resp1 = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                    "idempotency_key": idem_key,
                },
            )

            assert resp1.status_code == 200

            data1 = resp1.json()
            assert (
                data1["idempotent"] is False
            )

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
        ) as mock_query:
            resp2 = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                    "idempotency_key": idem_key,
                },
            )

            mock_query.assert_not_called()

            assert resp2.status_code == 200

            data2 = resp2.json()
            assert (
                data2["idempotent"] is True
            )
            assert (
                data2["order_id"]
                == data1["order_id"]
            )

    def test_source_is_shopify_for_new_orders(
        self,
        client,
        shopify_connection,
        db,
        store,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            return_value=(
                MOCK_DRAFT_ORDER_RESPONSE
            ),
        ):
            resp = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                },
            )

            assert resp.status_code == 200

        order = (
            db.query(Order)
            .filter(
                Order.id
                == resp.json()["order_id"]
            )
            .first()
        )

        assert order.source == "shopify"

    def test_shopify_draft_order_id_separated(
        self,
        client,
        shopify_connection,
        db,
        store,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            return_value=(
                MOCK_DRAFT_ORDER_RESPONSE
            ),
        ):
            resp = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                },
            )

            assert resp.status_code == 200

        order = (
            db.query(Order)
            .filter(
                Order.id
                == resp.json()["order_id"]
            )
            .first()
        )

        assert (
            order.shopify_draft_order_id
            is not None
        )
        assert (
            order.shopify_order_id is None
        )
        assert (
            order.shopify_draft_order_id
            != order.shopify_order_id
        )

    def test_invoice_url_saved_correctly(
        self,
        client,
        shopify_connection,
        db,
        store,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            return_value=(
                MOCK_DRAFT_ORDER_RESPONSE
            ),
        ):
            resp = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                },
            )

            assert resp.status_code == 200
            assert (
                resp.json()["invoice_url"]
                is not None
            )

        order = (
            db.query(Order)
            .filter(
                Order.id
                == resp.json()["order_id"]
            )
            .first()
        )

        assert (
            order.invoice_url
            == (
                "https://checkout.shopify.com/"
                "draft-invoice/9999"
            )
        )

    def test_historical_orders_not_shopify_source(
        self,
        db,
        org,
        store,
    ):
        old_order = Order(
            organization_id=org.id,
            store_id=store.id,
            order_number="HIST-001",
            total_amount=100.00,
            currency="USD",
        )

        db.add(old_order)
        db.commit()

        assert old_order.source is None

    def test_list_orders(
        self,
        client,
        shopify_connection,
        db,
        store,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            return_value=(
                MOCK_DRAFT_ORDER_RESPONSE
            ),
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                },
            )

        resp = client.get(
            f"/api/stores/"
            f"{store.id}"
            f"/shopify/orders"
        )

        assert resp.status_code == 200

        data = resp.json()
        assert data["total"] == 1
        assert (
            data["items"][0]["source"]
            == "shopify"
        )

    def test_get_order_detail(
        self,
        client,
        shopify_connection,
        db,
        store,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            return_value=(
                MOCK_DRAFT_ORDER_RESPONSE
            ),
        ):
            create_resp = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                },
            )

            order_id = (
                create_resp.json()["order_id"]
            )

        resp = client.get(
            f"/api/stores/"
            f"{store.id}"
            f"/shopify/orders/{order_id}"
        )

        assert resp.status_code == 200

        data = resp.json()
        assert data["id"] == order_id
        assert len(data["items"]) == 1

    def test_empty_items_rejected(
        self,
        client,
        shopify_connection,
        db,
        store,
    ):
        resp = client.post(
            f"/api/stores/"
            f"{store.id}"
            f"/shopify/orders",
            json={"items": []},
        )

        assert resp.status_code == 400


MOCK_FAILED_SHOPIFY_RESPONSE = {
    "draftOrderCreate": {
        "draftOrder": None,
        "userErrors": [
            {
                "field": ["lineItems"],
                "message": (
                    "Variant is required"
                ),
            }
        ],
    }
}


class TestShopifyOrdersMultiStore:
    """Tests for store-scoped uniqueness and
    cross-store isolation of orders."""

    def test_same_idempotency_key_across_stores(
        self,
        client,
        shopify_connection,
        db,
        org,
        store,
    ):
        other_org = Organization(
            name="Other",
            slug="other-idem-multi",
            plan="starter",
            subscription_status="active",
        )
        db.add(other_org)
        db.flush()

        other_store = Store(
            organization_id=other_org.id,
            name="Other Store",
            slug="other-store-idem-multi",
            country_code="US",
            currency="USD",
            timezone="UTC",
            default_language="en",
        )
        db.add(other_store)
        db.flush()

        other_user = User(
            email="other-idem@test.com",
            name="Other",
            external_auth_id="other-idem-cognito",
        )
        db.add(other_user)
        db.flush()

        other_m = OrganizationMembership(
            user_id=other_user.id,
            organization_id=other_org.id,
            role="owner",
        )
        db.add(other_m)
        db.flush()

        other_cc = CommerceConnection(
            organization_id=other_org.id,
            store_id=other_store.id,
            provider="shopify",
            external_store_url=(
                "other-store.myshopify.com"
            ),
            access_token_encrypted="enc-tok",
            scopes="read_products",
            status="connected",
        )
        db.add(other_cc)
        db.flush()

        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        idem_key = "shared-key-001"

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            return_value=(
                MOCK_DRAFT_ORDER_RESPONSE
            ),
        ):
            resp1 = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                    "idempotency_key": idem_key,
                },
            )

            assert resp1.status_code == 200

        app.dependency_overrides[
            get_current_user
        ] = lambda: other_user
        app.dependency_overrides[
            get_current_membership
        ] = lambda: other_m

        try:
            with patch(
                "app.shopify_sync"
                ".decrypt_shopify_secret",
                return_value="token",
            ), patch(
                "app.shopify_sync"
                ".ShopifyGraphQLClient.query",
                side_effect=[PAGE1, PAGE2],
            ):
                client.post(
                    f"/api/stores/"
                    f"{other_store.id}"
                    f"/shopify/sync/products"
                )

            other_product = Product(
                organization_id=other_org.id,
                store_id=other_store.id,
                title="Other",
                handle="other",
            )
            db.add(other_product)
            db.flush()

            other_variant = ProductVariant(
                product_id=other_product.id,
                title="Other Variant",
                price=15.00,
                currency="USD",
            )
            db.add(other_variant)
            db.flush()

            with patch(
                "app.shopify_orders"
                ".decrypt_shopify_secret",
                return_value="token",
            ), patch(
                "app.shopify_orders"
                ".ShopifyGraphQLClient.query",
                return_value={
                    "draftOrderCreate": {
                        "draftOrder": {
                            "id": (
                                "gid://shopify/"
                                "DraftOrder/8888"
                            ),
                            "name": "#D2",
                            "totalPriceSet": {
                                "shopMoney": {
                                    "amount": (
                                        "15.00"
                                    ),
                                    "currencyCode": (
                                        "USD"
                                    ),
                                }
                            },
                            "invoiceUrl": (
                                "https://checkout"
                                ".shopify.com/"
                                "draft-invoice/8888"
                            ),
                            "lineItems": {
                                "edges": []
                            },
                        },
                        "userErrors": [],
                    }
                },
            ):
                resp2 = client.post(
                    f"/api/stores/"
                    f"{other_store.id}"
                    f"/shopify/orders",
                    json={
                        "items": [
                            {
                                "variant_local_id": (
                                    other_variant.id
                                ),
                                "quantity": 1,
                            }
                        ],
                        "idempotency_key": (
                            idem_key
                        ),
                    },
                )

                assert resp2.status_code == 200

                data2 = resp2.json()
                assert data2["idempotent"] is False
                assert (
                    data2["order_id"]
                    != resp1.json()["order_id"]
                )
        finally:
            app.dependency_overrides.pop(
                get_current_user, None
            )
            app.dependency_overrides.pop(
                get_current_membership, None
            )

    def test_same_idempotency_key_within_store_deduped(
        self,
        client,
        shopify_connection,
        db,
        store,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        idem_key = "dedup-key-001"

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            return_value=(
                MOCK_DRAFT_ORDER_RESPONSE
            ),
        ):
            resp1 = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                    "idempotency_key": idem_key,
                },
            )

            assert resp1.status_code == 200
            assert (
                resp1.json()["idempotent"] is False
            )

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
        ) as mock_q:
            resp2 = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                    "idempotency_key": idem_key,
                },
            )

            mock_q.assert_not_called()

            assert resp2.status_code == 200

            data2 = resp2.json()
            assert (
                data2["idempotent"] is True
            )
            assert (
                data2["order_id"]
                == resp1.json()["order_id"]
            )

    def test_shopify_failure_preserves_local_order(
        self,
        client,
        shopify_connection,
        db,
        store,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        idem_key = "fail-key-001"

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            return_value=(
                MOCK_FAILED_SHOPIFY_RESPONSE
            ),
        ):
            resp1 = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                    "idempotency_key": idem_key,
                },
            )

            assert resp1.status_code == 422

        order = (
            db.query(Order)
            .filter(
                Order.idempotency_key == idem_key,
                Order.store_id == store.id,
            )
            .first()
        )

        assert order is not None
        assert (
            order.shopify_draft_order_id is None
        )
        assert (
            order.invoice_url is None
        )
        assert (
            order.financial_status == "pending"
        )
        assert order.source == "shopify"

        items = (
            db.query(OrderItem)
            .filter(
                OrderItem.order_id == order.id
            )
            .all()
        )

        assert len(items) == 1

    def test_shopify_retry_after_failure(
        self,
        client,
        shopify_connection,
        db,
        store,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        idem_key = "retry-key-001"

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            return_value=(
                MOCK_FAILED_SHOPIFY_RESPONSE
            ),
        ):
            resp1 = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                    "idempotency_key": idem_key,
                },
            )

            assert resp1.status_code == 422

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            return_value=(
                MOCK_DRAFT_ORDER_RESPONSE
            ),
        ):
            resp2 = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                    "idempotency_key": idem_key,
                },
            )

            assert resp2.status_code == 200

            data2 = resp2.json()
            assert data2["idempotent"] is False
            assert (
                data2["shopify_draft_order_id"]
                == (
                    "gid://shopify/"
                    "DraftOrder/9999"
                )
            )
            assert data2["invoice_url"] is not None

    def test_shopify_only_called_once_on_duplicate(
        self,
        client,
        shopify_connection,
        db,
        store,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        idem_key = "once-key-001"

        call_count = [0]

        def mock_shopify_query(*args, **kwargs):
            call_count[0] += 1
            return MOCK_DRAFT_ORDER_RESPONSE

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            side_effect=mock_shopify_query,
        ):
            resp1 = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                    "idempotency_key": idem_key,
                },
            )

            assert resp1.status_code == 200

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            side_effect=mock_shopify_query,
        ):
            resp2 = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                    "idempotency_key": idem_key,
                },
            )

            assert resp2.status_code == 200
            assert resp2.json()["idempotent"] is True
            assert call_count[0] == 1

    def test_cross_store_draft_order_isolation(
        self,
        client,
        shopify_connection,
        db,
        org,
        store,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            return_value=(
                MOCK_DRAFT_ORDER_RESPONSE
            ),
        ):
            resp = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                },
            )

            assert resp.status_code == 200

        order = (
            db.query(Order)
            .filter(
                Order.id
                == resp.json()["order_id"]
            )
            .first()
        )

        other_org = Organization(
            name="Other",
            slug="other-draft-iso",
        )
        db.add(other_org)
        db.flush()

        other_store = Store(
            organization_id=other_org.id,
            name="Other",
            slug="other-store-draft-iso",
            country_code="US",
            currency="USD",
            timezone="UTC",
            default_language="en",
        )
        db.add(other_store)
        db.flush()

        other_order = Order(
            organization_id=other_org.id,
            store_id=other_store.id,
            order_number="OTHER-001",
            total_amount=100.00,
            currency="USD",
            source="shopify",
            shopify_draft_order_id=(
                order.shopify_draft_order_id
            ),
        )
        db.add(other_order)

        try:
            db.flush()
            db.commit()
        except Exception:
            db.rollback()

            count = (
                db.query(Order)
                .filter(
                    Order.shopify_draft_order_id
                    == (
                        order
                        .shopify_draft_order_id
                    )
                )
                .count()
            )

            assert count == 1


MOCK_TIMEOUT_EXCEPTION = (
    "Request timed out"
)

MOCK_CONNECTION_RESET = (
    "Connection reset by peer"
)

MOCK_HTTP_500 = (
    "Shopify HTTP error 500"
)


class TestShopifyOrdersExternalStatus:
    """Tests for external_creation_status lifecycle
    tracking of Shopify Draft Orders."""

    def test_success_pending_to_created(
        self,
        client,
        shopify_connection,
        db,
        store,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            return_value=(
                MOCK_DRAFT_ORDER_RESPONSE
            ),
        ):
            resp = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                },
            )

            assert resp.status_code == 200

            data = resp.json()
            assert (
                data["external_creation_status"]
                == "created"
            )

        order = (
            db.query(Order)
            .filter(
                Order.id
                == data["order_id"]
            )
            .first()
        )

        assert (
            order.external_creation_status
            == "created"
        )
        assert (
            order.external_last_error is None
        )
        assert (
            order.shopify_draft_order_id
            is not None
        )

    def test_graphql_user_error_pending_to_failed(
        self,
        client,
        shopify_connection,
        db,
        store,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            return_value=(
                MOCK_FAILED_SHOPIFY_RESPONSE
            ),
        ):
            resp = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                    "idempotency_key": (
                        "failed-key-001"
                    ),
                },
            )

            assert resp.status_code == 422

        order = (
            db.query(Order)
            .filter(
                Order.idempotency_key
                == "failed-key-001",
                Order.store_id == store.id,
            )
            .first()
        )

        assert order is not None
        assert (
            order.external_creation_status
            == "failed"
        )
        assert (
            order.external_last_error
            is not None
        )
        assert (
            order.shopify_draft_order_id
            is None
        )
        assert (
            order.invoice_url is None
        )

    def test_timeout_pending_to_unknown(
        self,
        client,
        shopify_connection,
        db,
        store,
    ):
        from app.shopify_client import (
            ShopifyAPIError,
        )

        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            side_effect=ShopifyAPIError(
                MOCK_TIMEOUT_EXCEPTION
            ),
        ):
            resp = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                    "idempotency_key": (
                        "timeout-key-001"
                    ),
                },
            )

            assert resp.status_code == 502

        order = (
            db.query(Order)
            .filter(
                Order.idempotency_key
                == "timeout-key-001",
                Order.store_id == store.id,
            )
            .first()
        )

        assert order is not None
        assert (
            order.external_creation_status
            == "unknown"
        )
        assert (
            order.external_last_error
            is not None
        )
        assert (
            "timed out"
            in order.external_last_error.lower()
        )
        assert (
            order.shopify_draft_order_id
            is None
        )

    def test_connection_reset_pending_to_unknown(
        self,
        client,
        shopify_connection,
        db,
        store,
    ):
        from app.shopify_client import (
            ShopifyAPIError,
        )

        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            side_effect=ShopifyAPIError(
                MOCK_CONNECTION_RESET
            ),
        ):
            resp = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                    "idempotency_key": (
                        "reset-key-001"
                    ),
                },
            )

            assert resp.status_code == 502

        order = (
            db.query(Order)
            .filter(
                Order.idempotency_key
                == "reset-key-001",
                Order.store_id == store.id,
            )
            .first()
        )

        assert order is not None
        assert (
            order.external_creation_status
            == "unknown"
        )
        assert (
            order.shopify_draft_order_id
            is None
        )

    def test_http_5xx_ambiguous_pending_to_unknown(
        self,
        client,
        shopify_connection,
        db,
        store,
    ):
        from app.shopify_client import (
            ShopifyAPIError,
        )

        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            side_effect=ShopifyAPIError(
                MOCK_HTTP_500
            ),
        ):
            resp = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                    "idempotency_key": (
                        "5xx-key-001"
                    ),
                },
            )

            assert resp.status_code == 502

        order = (
            db.query(Order)
            .filter(
                Order.idempotency_key
                == "5xx-key-001",
                Order.store_id == store.id,
            )
            .first()
        )

        assert order is not None
        assert (
            order.external_creation_status
            == "unknown"
        )
        assert (
            order.shopify_draft_order_id
            is None
        )

    def test_retry_same_key_when_created_no_shopify(
        self,
        client,
        shopify_connection,
        db,
        store,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        idem_key = "created-retry-001"

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            return_value=(
                MOCK_DRAFT_ORDER_RESPONSE
            ),
        ):
            resp1 = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                    "idempotency_key": idem_key,
                },
            )

            assert resp1.status_code == 200
            assert (
                resp1.json()[
                    "external_creation_status"
                ]
                == "created"
            )

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
        ) as mock_q:
            resp2 = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                    "idempotency_key": idem_key,
                },
            )

            mock_q.assert_not_called()

            assert resp2.status_code == 200
            assert (
                resp2.json()["idempotent"] is True
            )
            assert (
                resp2.json()["order_id"]
                == resp1.json()["order_id"]
            )

    def test_retry_same_key_when_unknown_no_shopify(
        self,
        client,
        shopify_connection,
        db,
        store,
    ):
        from app.shopify_client import (
            ShopifyAPIError,
        )

        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        idem_key = "unknown-retry-001"

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            side_effect=ShopifyAPIError(
                MOCK_TIMEOUT_EXCEPTION
            ),
        ):
            resp1 = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                    "idempotency_key": idem_key,
                },
            )

            assert resp1.status_code == 502

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
        ) as mock_q:
            resp2 = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                    "idempotency_key": idem_key,
                },
            )

            mock_q.assert_not_called()

            assert resp2.status_code == 200

            data2 = resp2.json()
            assert (
                data2["idempotent"] is True
            )
            assert (
                data2["external_creation_status"]
                == "unknown"
            )
            assert (
                data2["shopify_draft_order_id"]
                is None
            )

    def test_pending_status_no_retry_no_shopify(
        self,
        client,
        shopify_connection,
        db,
        store,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        order = Order(
            organization_id=(
                store.organization_id
            ),
            store_id=store.id,
            order_number="PENDING-001",
            total_amount=0,
            currency="USD",
            financial_status="pending",
            source="shopify",
            shopify_draft_order_id=None,
            invoice_url=None,
            idempotency_key="pending-key-001",
            external_creation_status="pending",
        )
        db.add(order)
        db.commit()

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
        ) as mock_q:
            resp = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                    "idempotency_key": (
                        "pending-key-001"
                    ),
                },
            )

            mock_q.assert_not_called()

            assert resp.status_code == 200

            data = resp.json()
            assert (
                data["idempotent"] is True
            )
            assert (
                data["external_creation_status"]
                == "pending"
            )
            assert (
                data["shopify_draft_order_id"]
                is None
            )

    def test_explicit_retry_after_failed_reuses_order(
        self,
        client,
        shopify_connection,
        db,
        store,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        idem_key = "retry-failed-001"

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            return_value=(
                MOCK_FAILED_SHOPIFY_RESPONSE
            ),
        ):
            resp1 = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                    "idempotency_key": idem_key,
                },
            )

            assert resp1.status_code == 422

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            return_value=(
                MOCK_DRAFT_ORDER_RESPONSE
            ),
        ):
            resp2 = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                    "idempotency_key": idem_key,
                },
            )

            assert resp2.status_code == 200

            data2 = resp2.json()
            assert (
                data2["idempotent"] is False
            )
            assert (
                data2["external_creation_status"]
                == "created"
            )
            assert (
                data2["shopify_draft_order_id"]
                is not None
            )

        order = (
            db.query(Order)
            .filter(
                Order.idempotency_key
                == idem_key,
                Order.store_id == store.id,
            )
            .first()
        )

        assert order is not None
        assert (
            order.external_creation_status
            == "created"
        )

    def test_ambiguous_failure_preserves_order(
        self,
        client,
        shopify_connection,
        db,
        store,
    ):
        from app.shopify_client import (
            ShopifyAPIError,
        )

        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        idem_key = "ambiguous-preserve-001"

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            side_effect=ShopifyAPIError(
                MOCK_TIMEOUT_EXCEPTION
            ),
        ):
            resp = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                    "idempotency_key": idem_key,
                },
            )

            assert resp.status_code == 502

        order = (
            db.query(Order)
            .filter(
                Order.idempotency_key
                == idem_key,
                Order.store_id == store.id,
            )
            .first()
        )

        assert order is not None
        assert (
            order.external_creation_status
            == "unknown"
        )
        assert (
            order.shopify_draft_order_id
            is None
        )
        assert (
            order.invoice_url is None
        )
        assert (
            order.financial_status == "pending"
        )
        assert order.source == "shopify"

    def test_external_last_error_no_token(
        self,
        client,
        shopify_connection,
        db,
        store,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            return_value=(
                MOCK_FAILED_SHOPIFY_RESPONSE
            ),
        ):
            resp = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                    "idempotency_key": (
                        "error-no-token-001"
                    ),
                },
            )

            assert resp.status_code == 422

        order = (
            db.query(Order)
            .filter(
                Order.idempotency_key
                == "error-no-token-001",
                Order.store_id == store.id,
            )
            .first()
        )

        assert order is not None
        assert (
            order.external_last_error
            is not None
        )
        assert (
            "token"
            not in order.external_last_error.lower()
        )
        assert (
            "secret"
            not in order.external_last_error.lower()
        )
        assert (
            "Bearer"
            not in order.external_last_error
        )

    def test_historical_orders_external_status_null(
        self,
        db,
        org,
        store,
    ):
        old_order = Order(
            organization_id=org.id,
            store_id=store.id,
            order_number="HIST-EXT-001",
            total_amount=100.00,
            currency="USD",
        )

        db.add(old_order)
        db.commit()

        assert old_order.source is None
        assert (
            old_order.external_creation_status
            is None
        )
        assert (
            old_order.external_last_error is None
        )

    def test_same_idempotency_key_across_stores(
        self,
        client,
        shopify_connection,
        db,
        org,
        store,
    ):
        other_org = Organization(
            name="Other",
            slug="other-ext-multi",
            plan="starter",
            subscription_status="active",
        )
        db.add(other_org)
        db.flush()

        other_store = Store(
            organization_id=other_org.id,
            name="Other Store",
            slug="other-store-ext-multi",
            country_code="US",
            currency="USD",
            timezone="UTC",
            default_language="en",
        )
        db.add(other_store)
        db.flush()

        other_user = User(
            email="other-ext@test.com",
            name="Other",
            external_auth_id=(
                "other-ext-cognito"
            ),
        )
        db.add(other_user)
        db.flush()

        other_m = OrganizationMembership(
            user_id=other_user.id,
            organization_id=other_org.id,
            role="owner",
        )
        db.add(other_m)
        db.flush()

        other_cc = CommerceConnection(
            organization_id=other_org.id,
            store_id=other_store.id,
            provider="shopify",
            external_store_url=(
                "other-ext.myshopify.com"
            ),
            access_token_encrypted=(
                "enc-tok-ext"
            ),
            scopes="read_products",
            status="connected",
        )
        db.add(other_cc)
        db.flush()

        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        idem_key = "ext-shared-key-001"

        with patch(
            "app.shopify_orders"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_orders"
            ".ShopifyGraphQLClient.query",
            return_value=(
                MOCK_DRAFT_ORDER_RESPONSE
            ),
        ):
            resp1 = client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/orders",
                json={
                    "items": [
                        {
                            "variant_local_id": (
                                variant.id
                            ),
                            "quantity": 1,
                        }
                    ],
                    "idempotency_key": idem_key,
                },
            )

            assert resp1.status_code == 200

        app.dependency_overrides[
            get_current_user
        ] = lambda: other_user
        app.dependency_overrides[
            get_current_membership
        ] = lambda: other_m

        try:
            with patch(
                "app.shopify_sync"
                ".decrypt_shopify_secret",
                return_value="token",
            ), patch(
                "app.shopify_sync"
                ".ShopifyGraphQLClient.query",
                side_effect=[PAGE1, PAGE2],
            ):
                client.post(
                    f"/api/stores/"
                    f"{other_store.id}"
                    f"/shopify/sync/products"
                )

            other_product = Product(
                organization_id=(
                    other_org.id
                ),
                store_id=other_store.id,
                title="Other",
                handle="other-ext",
            )
            db.add(other_product)
            db.flush()

            other_variant = ProductVariant(
                product_id=other_product.id,
                title="Other Variant",
                price=15.00,
                currency="USD",
            )
            db.add(other_variant)
            db.flush()

            with patch(
                "app.shopify_orders"
                ".decrypt_shopify_secret",
                return_value="token",
            ), patch(
                "app.shopify_orders"
                ".ShopifyGraphQLClient.query",
                return_value={
                    "draftOrderCreate": {
                        "draftOrder": {
                            "id": (
                                "gid://shopify/"
                                "DraftOrder/7777"
                            ),
                            "name": "#D3",
                            "totalPriceSet": {
                                "shopMoney": {
                                    "amount": (
                                        "15.00"
                                    ),
                                    "currencyCode": (
                                        "USD"
                                    ),
                                }
                            },
                            "invoiceUrl": (
                                "https://checkout"
                                ".shopify.com/"
                                "draft-invoice/7777"
                            ),
                            "lineItems": {
                                "edges": []
                            },
                        },
                        "userErrors": [],
                    }
                },
            ):
                resp2 = client.post(
                    f"/api/stores/"
                    f"{other_store.id}"
                    f"/shopify/orders",
                    json={
                        "items": [
                            {
                                "variant_local_id": (
                                    other_variant.id
                                ),
                                "quantity": 1,
                            }
                        ],
                        "idempotency_key": (
                            idem_key
                        ),
                    },
                )

                assert (
                    resp2.status_code == 200
                )

                data2 = resp2.json()
                assert (
                    data2["idempotent"] is False
                )
                assert (
                    data2["order_id"]
                    != resp1.json()["order_id"]
                )
                assert (
                    data2[
                        "external_creation_status"
                    ]
                    == "created"
                )
        finally:
            app.dependency_overrides.pop(
                get_current_user, None
            )
            app.dependency_overrides.pop(
                get_current_membership, None
            )

    def test_full_tenant_store_isolation(
        self,
        client,
        shopify_connection,
        db,
        org,
        store,
    ):
        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            client.post(
                f"/api/stores/"
                f"{store.id}"
                f"/shopify/sync/products"
            )

        variant = (
            db.query(ProductVariant)
            .first()
        )

        other_org = Organization(
            name="Other",
            slug="other-tenant-iso",
            plan="starter",
            subscription_status="active",
        )
        db.add(other_org)
        db.flush()

        other_store = Store(
            organization_id=other_org.id,
            name="Other Store",
            slug="other-store-tenant-iso",
            country_code="US",
            currency="USD",
            timezone="UTC",
            default_language="en",
        )
        db.add(other_store)
        db.flush()

        other_user = User(
            email="other-tenant@test.com",
            name="Other",
            external_auth_id=(
                "other-tenant-cognito"
            ),
        )
        db.add(other_user)
        db.flush()

        other_m = OrganizationMembership(
            user_id=other_user.id,
            organization_id=other_org.id,
            role="owner",
        )
        db.add(other_m)
        db.flush()

        other_cc = CommerceConnection(
            organization_id=other_org.id,
            store_id=other_store.id,
            provider="shopify",
            external_store_url=(
                "other-tenant.myshopify.com"
            ),
            access_token_encrypted=(
                "enc-tok-tenant"
            ),
            scopes="read_products",
            status="connected",
        )
        db.add(other_cc)
        db.flush()

        app.dependency_overrides[
            get_current_user
        ] = lambda: other_user
        app.dependency_overrides[
            get_current_membership
        ] = lambda: other_m

        try:
            with patch(
                "app.shopify_orders"
                ".decrypt_shopify_secret",
                return_value="token",
            ), patch(
                "app.shopify_orders"
                ".ShopifyGraphQLClient.query",
            ) as mock_q:
                resp = client.post(
                    f"/api/stores/"
                    f"{other_store.id}"
                    f"/shopify/orders",
                    json={
                        "items": [
                            {
                                "variant_local_id": (
                                    variant.id
                                ),
                                "quantity": 1,
                            }
                        ],
                    },
                )

                assert (
                    resp.status_code == 400
                )
                mock_q.assert_not_called()
        finally:
            app.dependency_overrides.pop(
                get_current_user, None
            )
            app.dependency_overrides.pop(
                get_current_membership, None
            )
