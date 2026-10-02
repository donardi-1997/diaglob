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
    Customer,
    CustomerStoreProfile,
    Order,
    OrderItem,
    Organization,
    OrganizationMembership,
    Product,
    ProductVariant,
    Store,
    User,
)
from app.shopify_client import (
    ShopifyAuthError,
    ShopifyTimeoutError,
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


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def cleanup_db():
    yield
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())


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
                "availableForSale": False,
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


class TestShopifyPocOrder:
    def _variant(self, db, org, store):
        product = Product(
            organization_id=org.id,
            store_id=store.id,
            shopify_product_id="901",
            title="POC product",
            handle="poc-product",
            description="",
            active=True,
        )
        db.add(product)
        db.flush()
        variant = ProductVariant(
            product_id=product.id,
            shopify_variant_id="902",
            title="Default",
            sku="POC-902",
            price=12.5,
            currency="USD",
            inventory_quantity=10,
            available=True,
        )
        db.add(variant)
        db.commit()
        return variant

    def _payload(self, variant_id, **changes):
        payload = {
            "variant_id": f"gid://shopify/ProductVariant/{variant_id}",
            "quantity": 2,
            "customer_email": "poc@example.com",
            "customer_phone": "+573001234567",
            "shipping_address": {
                "first_name": "POC",
                "last_name": "Diaglob",
                "address1": "Calle 1",
                "city": "Medellin",
                "province": "Antioquia",
                "country_code": "co",
                "zip": "050001",
            },
            "idempotency_key": "poc-key-001",
        }
        payload.update(changes)
        return payload

    def test_success_and_idempotency(
        self, client, db, org, store, shopify_connection
    ):
        variant = self._variant(db, org, store)
        shopify_response = {
            "orderCreate": {
                "order": {
                    "id": "gid://shopify/Order/700",
                    "name": "#1007",
                },
                "userErrors": [],
            }
        }
        with patch(
            "app.shopify_poc.decrypt_shopify_secret",
            return_value="secret",
        ), patch(
            "app.shopify_poc.ShopifyGraphQLClient.query",
            return_value=shopify_response,
        ) as query:
            first = client.post(
                f"/api/stores/{store.id}/shopify/poc/order",
                json=self._payload(variant.shopify_variant_id),
            )
            second = client.post(
                f"/api/stores/{store.id}/shopify/poc/order",
                json=self._payload(variant.shopify_variant_id),
            )
        assert first.status_code == 200
        assert second.json()["idempotent"] is True
        query.assert_called_once()
        variables = query.call_args.args[1]["order"]
        assert variables["email"] == "poc@example.com"
        assert variables["phone"] == "+573001234567"
        assert "DIAGLOB_POC" in variables["tags"]

    @pytest.mark.parametrize(
        "changes",
        [
            {"quantity": 0},
            {
                "shipping_address": {
                    "first_name": "",
                    "last_name": "X",
                    "address1": "A",
                    "city": "C",
                    "country_code": "CO",
                    "zip": "1",
                }
            },
        ],
    )
    def test_invalid_input_rejected(self, client, store, changes):
        response = client.post(
            f"/api/stores/{store.id}/shopify/poc/order",
            json=self._payload("902", **changes),
        )
        assert response.status_code == 422

    def test_invalid_variant_rejected(
        self, client, store, shopify_connection
    ):
        response = client.post(
            f"/api/stores/{store.id}/shopify/poc/order",
            json=self._payload("999"),
        )
        assert response.status_code == 400

    def test_user_error_is_normalized(
        self, client, db, org, store, shopify_connection
    ):
        variant = self._variant(db, org, store)
        with patch(
            "app.shopify_poc.decrypt_shopify_secret",
            return_value="secret",
        ), patch(
            "app.shopify_poc.ShopifyGraphQLClient.query",
            return_value={
                "orderCreate": {
                    "order": None,
                    "userErrors": [{"message": "invalid variant"}],
                }
            },
        ):
            response = client.post(
                f"/api/stores/{store.id}/shopify/poc/order",
                json=self._payload(variant.shopify_variant_id),
            )
        assert response.status_code == 422
        assert "invalid variant" in response.json()["detail"]["error"]

    @pytest.mark.parametrize(
        "error,status",
        [
            (ShopifyTimeoutError("timed out"), 504),
            (ShopifyAuthError("invalid token"), 401),
        ],
    )
    def test_shopify_errors_do_not_expose_secret(
        self,
        client,
        db,
        org,
        store,
        shopify_connection,
        error,
        status,
    ):
        variant = self._variant(db, org, store)
        with patch(
            "app.shopify_poc.decrypt_shopify_secret",
            return_value="secret",
        ), patch(
            "app.shopify_poc.ShopifyGraphQLClient.query",
            side_effect=error,
        ):
            response = client.post(
                f"/api/stores/{store.id}/shopify/poc/order",
                json=self._payload(
                    variant.shopify_variant_id,
                    idempotency_key="poc-error",
                ),
            )
        assert response.status_code == status
        assert "secret" not in response.text

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
        queries = []

        def mock_query(query, variables=None):
            queries.append(query)
            return PAGE1 if len(queries) == 1 else PAGE2

        with patch(
            "app.shopify_sync"
            ".decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync"
            ".ShopifyGraphQLClient.query",
            side_effect=mock_query,
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

        assert len(queries) == 2
        assert "availableForSale" in queries[0]
        assert "available\n" not in queries[0]

        products = (
            db.query(Product)
            .filter(
                Product.store_id
                == shopify_connection.store_id,
            )
            .all()
        )

        assert len(products) == 3

        variant = (
            db.query(ProductVariant)
            .filter(
                ProductVariant.shopify_variant_id
                == "101",
            )
            .first()
        )
        assert variant is not None
        assert variant.available is False

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

class TestShopifyOrderWebhooks:
    @staticmethod
    def _payload():
        return {
            "id": 98765,
            "order_number": 1057,
            "name": "#1057",
            "email": "buyer@example.com",
            "created_at": "2026-10-02T14:20:00Z",
            "updated_at": "2026-10-02T14:21:00Z",
            "currency": "USD",
            "current_total_price": "59.98",
            "financial_status": "pending",
            "fulfillment_status": None,
            "payment_gateway_names": ["bogus"],
            "note": "Webhook order",
            "customer": {
                "id": 2001,
                "first_name": "Ada",
                "last_name": "Buyer",
                "email": "buyer@example.com",
                "phone": "+15551234567",
            },
            "shipping_address": {
                "first_name": "Ada",
                "last_name": "Buyer",
                "address1": "123 Test St",
                "address2": "Apt 4",
                "city": "Miami",
                "province": "Florida",
                "province_code": "FL",
                "country": "United States",
                "country_code": "US",
                "zip": "33101",
                "phone": "+15551234567",
            },
            "line_items": [
                {
                    "id": 555,
                    "variant_id": 101,
                    "title": "Shirt",
                    "name": "Shirt - Default",
                    "sku": "SKU-001",
                    "quantity": 1,
                    "price": "59.98",
                }
            ],
        }

    @staticmethod
    def _headers(payload_bytes, *, topic="orders/create", shop="test-store.myshopify.com"):
        import base64
        import hashlib
        import hmac

        secret = "shopify-webhook-secret"
        signature = base64.b64encode(
            hmac.new(
                secret.encode("utf-8"),
                payload_bytes,
                hashlib.sha256,
            ).digest()
        ).decode("ascii")
        return secret, {
            "X-Shopify-Hmac-Sha256": signature,
            "X-Shopify-Topic": topic,
            "X-Shopify-Shop-Domain": shop,
            "X-Shopify-Webhook-Id": "webhook-test-1",
        }

    def _sync_catalog(self, client, store):
        with patch(
            "app.shopify_sync.decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_sync.ShopifyGraphQLClient.query",
            side_effect=[PAGE1, PAGE2],
        ):
            response = client.post(
                f"/api/stores/{store.id}/shopify/sync/products"
            )
            assert response.status_code == 200

    def test_create_webhook_persists_customer_order_items_and_address(
        self,
        client,
        shopify_connection,
        store,
        db,
    ):
        import json

        self._sync_catalog(client, store)
        payload = self._payload()
        body = json.dumps(payload).encode("utf-8")
        secret, headers = self._headers(body)

        with patch.dict(
            os.environ,
            {"SHOPIFY_CLIENT_SECRET": secret},
            clear=False,
        ):
            response = client.post(
                "/api/webhooks/shopify",
                content=body,
                headers=headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["action"] == "created"

        db.expire_all()
        order = (
            db.query(Order)
            .filter(Order.shopify_order_id == "98765")
            .one()
        )
        assert order.store_id == store.id
        assert order.order_number == "1057"
        assert order.source == "shopify"
        assert order.lifecycle_status == "open"
        assert order.fulfillment_status == "unfulfilled"
        assert order.shipping_address["city"] == "Miami"
        assert order.shipping_address["country_code"] == "US"

        customer = db.query(Customer).filter(Customer.id == order.customer_id).one()
        assert customer.name == "Ada Buyer"
        assert customer.phone == "+15551234567"
        assert customer.email == "buyer@example.com"

        profile = (
            db.query(CustomerStoreProfile)
            .filter(
                CustomerStoreProfile.customer_id == customer.id,
                CustomerStoreProfile.store_id == store.id,
            )
            .one()
        )
        assert profile.external_customer_id == "2001"
        assert profile.orders_count == 1
        assert float(profile.total_spent) == 59.98
        assert profile.last_order_ref == "1057"

        items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
        assert len(items) == 1
        assert items[0].shopify_line_item_id == "555"
        assert items[0].shopify_variant_id == "101"
        assert items[0].variant_id is not None

    def test_duplicate_create_is_idempotent(self, client, shopify_connection, store, db):
        import json

        payload = self._payload()
        body = json.dumps(payload).encode("utf-8")
        secret, headers = self._headers(body)

        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}, clear=False):
            first = client.post("/api/webhooks/shopify", content=body, headers=headers)
            second = client.post("/api/webhooks/shopify", content=body, headers=headers)

        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["action"] == "updated"
        assert db.query(Order).filter(Order.shopify_order_id == "98765").count() == 1
        order = db.query(Order).filter(Order.shopify_order_id == "98765").one()
        assert db.query(OrderItem).filter(OrderItem.order_id == order.id).count() == 1
        assert db.query(Customer).count() == 1

    def test_updated_webhook_updates_same_order_and_line_item(
        self,
        client,
        shopify_connection,
        store,
        db,
    ):
        import json

        payload = self._payload()
        create_body = json.dumps(payload).encode("utf-8")
        secret, create_headers = self._headers(create_body)

        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}, clear=False):
            assert client.post(
                "/api/webhooks/shopify",
                content=create_body,
                headers=create_headers,
            ).status_code == 200

            original = db.query(Order).filter(Order.shopify_order_id == "98765").one()
            original_item = db.query(OrderItem).filter(OrderItem.order_id == original.id).one()
            original_order_id = original.id
            original_item_id = original_item.id

            payload["financial_status"] = "paid"
            payload["current_total_price"] = "119.96"
            payload["line_items"][0]["quantity"] = 2
            payload["updated_at"] = "2026-10-02T15:00:00Z"
            update_body = json.dumps(payload).encode("utf-8")
            _, update_headers = self._headers(
                update_body,
                topic="orders/updated",
            )

            response = client.post(
                "/api/webhooks/shopify",
                content=update_body,
                headers=update_headers,
            )

        assert response.status_code == 200
        assert response.json()["action"] == "updated"

        db.expire_all()
        order = db.query(Order).filter(Order.shopify_order_id == "98765").one()
        item = db.query(OrderItem).filter(OrderItem.order_id == order.id).one()
        assert order.id == original_order_id
        assert order.financial_status == "paid"
        assert order.payment_status == "paid"
        assert order.lifecycle_status == "paid"
        assert float(order.total_amount) == 119.96
        assert item.id == original_item_id
        assert item.quantity == 2

    def test_stale_retry_does_not_regress_newer_order_state(
        self,
        client,
        shopify_connection,
        store,
        db,
    ):
        import json

        payload = self._payload()
        payload["financial_status"] = "paid"
        payload["updated_at"] = "2026-10-02T15:00:00Z"
        paid_body = json.dumps(payload).encode("utf-8")
        secret, paid_headers = self._headers(
            paid_body,
            topic="orders/updated",
        )

        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}, clear=False):
            first = client.post(
                "/api/webhooks/shopify",
                content=paid_body,
                headers=paid_headers,
            )
            assert first.status_code == 200

            stale = self._payload()
            stale["updated_at"] = "2026-10-02T14:21:00Z"
            stale_body = json.dumps(stale).encode("utf-8")
            _, stale_headers = self._headers(
                stale_body,
                topic="orders/create",
            )
            retry = client.post(
                "/api/webhooks/shopify",
                content=stale_body,
                headers=stale_headers,
            )

        assert retry.status_code == 200
        assert retry.json()["action"] == "ignored_stale"

        db.expire_all()
        order = db.query(Order).filter(
            Order.shopify_order_id == "98765"
        ).one()
        assert order.financial_status == "paid"
        assert order.payment_status == "paid"
        assert order.lifecycle_status == "paid"

    def test_cancelled_webhook_marks_order_cancelled(
        self,
        client,
        shopify_connection,
        store,
        db,
    ):
        import json

        payload = self._payload()
        body = json.dumps(payload).encode("utf-8")
        secret, headers = self._headers(body)

        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}, clear=False):
            assert client.post(
                "/api/webhooks/shopify",
                content=body,
                headers=headers,
            ).status_code == 200

            payload["cancelled_at"] = "2026-10-02T16:00:00Z"
            cancel_body = json.dumps(payload).encode("utf-8")
            _, cancel_headers = self._headers(
                cancel_body,
                topic="orders/cancelled",
            )
            response = client.post(
                "/api/webhooks/shopify",
                content=cancel_body,
                headers=cancel_headers,
            )

        assert response.status_code == 200
        db.expire_all()
        order = db.query(Order).filter(Order.shopify_order_id == "98765").one()
        assert order.lifecycle_status == "cancelled"

    def test_invalid_hmac_is_rejected(self, client, shopify_connection):
        import json

        body = json.dumps(self._payload()).encode("utf-8")
        response = client.post(
            "/api/webhooks/shopify",
            content=body,
            headers={
                "X-Shopify-Hmac-Sha256": "invalid",
                "X-Shopify-Topic": "orders/create",
                "X-Shopify-Shop-Domain": "test-store.myshopify.com",
            },
        )
        assert response.status_code == 401

    def test_unknown_shop_is_acknowledged_without_persisting(
        self,
        client,
        shopify_connection,
        db,
    ):
        import json

        body = json.dumps(self._payload()).encode("utf-8")
        secret, headers = self._headers(
            body,
            shop="unknown-store.myshopify.com",
        )

        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}, clear=False):
            response = client.post(
                "/api/webhooks/shopify",
                content=body,
                headers=headers,
            )

        assert response.status_code == 200
        assert response.json()["action"] == "ignored"
        assert db.query(Order).count() == 0

    def test_invalid_json_is_rejected(self, client, shopify_connection):
        body = b"{not-json"
        secret, headers = self._headers(body)

        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}, clear=False):
            response = client.post(
                "/api/webhooks/shopify",
                content=body,
                headers=headers,
            )

        assert response.status_code == 400

class TestShopifyWebhookSubscriptions:
    def test_ensure_webhooks_is_idempotent_and_creates_only_missing(
        self,
        client,
        shopify_connection,
        store,
    ):
        existing = {
            "webhookSubscriptions": {
                "edges": [
                    {
                        "node": {
                            "id": "gid://shopify/WebhookSubscription/1",
                            "topic": "ORDERS_CREATE",
                            "uri": "https://api.diaglob.tech/api/webhooks/shopify",
                        }
                    }
                ]
            }
        }
        create_updated = {
            "webhookSubscriptionCreate": {
                "webhookSubscription": {
                    "id": "gid://shopify/WebhookSubscription/2",
                    "topic": "ORDERS_UPDATED",
                    "uri": "https://api.diaglob.tech/api/webhooks/shopify",
                },
                "userErrors": [],
            }
        }
        create_cancelled = {
            "webhookSubscriptionCreate": {
                "webhookSubscription": {
                    "id": "gid://shopify/WebhookSubscription/3",
                    "topic": "ORDERS_CANCELLED",
                    "uri": "https://api.diaglob.tech/api/webhooks/shopify",
                },
                "userErrors": [],
            }
        }

        with patch(
            "app.shopify_webhook_subscriptions.decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_webhook_subscriptions.ShopifyGraphQLClient.query",
            side_effect=[
                existing,
                create_updated,
                create_cancelled,
            ],
        ) as query:
            response = client.post(
                f"/api/stores/{store.id}/shopify/webhooks/ensure"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["retained"] == ["ORDERS_CREATE"]
        assert [item["topic"] for item in data["created"]] == [
            "ORDERS_UPDATED",
            "ORDERS_CANCELLED",
        ]
        assert query.call_count == 3

    def test_ensure_webhooks_provider_error_is_visible_and_recorded(
        self,
        client,
        shopify_connection,
        store,
        db,
    ):
        from app.shopify_client import ShopifyAPIError

        with patch(
            "app.shopify_webhook_subscriptions.decrypt_shopify_secret",
            return_value="token",
        ), patch(
            "app.shopify_webhook_subscriptions.ShopifyGraphQLClient.query",
            side_effect=ShopifyAPIError("provider unavailable"),
        ):
            response = client.post(
                f"/api/stores/{store.id}/shopify/webhooks/ensure"
            )

        assert response.status_code == 502
        db.expire_all()
        refreshed = db.query(CommerceConnection).filter(
            CommerceConnection.id == shopify_connection.id
        ).one()
        assert "WEBHOOK_SUBSCRIPTION_FAILED" in (refreshed.last_error or "")

