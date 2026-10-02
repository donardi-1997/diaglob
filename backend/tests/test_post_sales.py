from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import pytest

from app.db import Base
from app.models import Customer, Order, Organization, Store, User
from app.services import post_sales_service


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def schema():
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
def data(db):
    org = Organization(
        name="Post Sales Org",
        slug="post-sales-org",
        plan="growth",
        subscription_status="active",
        active=True,
    )
    db.add(org)
    db.flush()
    user = User(
        external_auth_id="post-sales-user",
        email="post-sales@example.com",
        name="Post Sales User",
        active=True,
    )
    db.add(user)
    db.flush()
    store = Store(
        organization_id=org.id,
        name="Post Sales Store",
        slug="post-sales-store",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
        active=True,
        deleted=False,
    )
    db.add(store)
    db.flush()
    customer = Customer(
        organization_id=org.id,
        name="Cliente E2E",
        phone="+573001234567",
        email="cliente@example.com",
        country_code="CO",
    )
    db.add(customer)
    db.flush()
    order = Order(
        organization_id=org.id,
        store_id=store.id,
        customer_id=customer.id,
        order_number="PS-100",
        total_amount=120000,
        currency="COP",
    )
    db.add(order)
    db.commit()
    return org, user, store, customer, order


def test_create_case_links_real_order_and_customer(db, data, monkeypatch):
    org, user, store, customer, order = data
    monkeypatch.setattr(post_sales_service, "safe_emit_event", lambda *args, **kwargs: [])

    created = post_sales_service.create_case(
        db,
        org.id,
        store.id,
        user.id,
        {
            "case_type": "damaged",
            "priority": "high",
            "title": "Caja golpeada",
            "description": "El cliente adjuntó evidencia.",
            "order_id": order.id,
        },
    )

    assert created["order_id"] == order.id
    assert created["customer_id"] == customer.id
    assert created["status"] == "open"
    assert created["currency"] == "COP"
    assert created["events"][0]["event_type"] == "case_created"


def test_case_is_strictly_store_scoped(db, data, monkeypatch):
    org, user, store, _customer, order = data
    monkeypatch.setattr(post_sales_service, "safe_emit_event", lambda *args, **kwargs: [])
    other = Store(
        organization_id=org.id,
        name="Other",
        slug="other-post-sales",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
        active=True,
        deleted=False,
    )
    db.add(other)
    db.commit()

    with pytest.raises(post_sales_service.PostSalesValidationError):
        post_sales_service.create_case(
            db,
            org.id,
            other.id,
            user.id,
            {
                "case_type": "refund",
                "priority": "normal",
                "title": "No debe cruzar tiendas",
                "order_id": order.id,
            },
        )


def test_closed_case_cannot_be_reopened(db, data, monkeypatch):
    org, user, store, _customer, order = data
    monkeypatch.setattr(post_sales_service, "safe_emit_event", lambda *args, **kwargs: [])
    created = post_sales_service.create_case(
        db,
        org.id,
        store.id,
        user.id,
        {
            "case_type": "delivery_issue",
            "priority": "normal",
            "title": "Novedad",
            "order_id": order.id,
        },
    )
    post_sales_service.update_case(
        db,
        org.id,
        store.id,
        created["id"],
        user.id,
        {"status": "closed"},
    )

    with pytest.raises(post_sales_service.PostSalesValidationError):
        post_sales_service.update_case(
            db,
            org.id,
            store.id,
            created["id"],
            user.id,
            {"status": "open"},
        )
