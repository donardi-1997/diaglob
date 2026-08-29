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

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(
        get_current_user, None
    )
    app.dependency_overrides.pop(
        get_current_membership, None
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
