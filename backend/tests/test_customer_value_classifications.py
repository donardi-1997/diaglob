"""Regression coverage for commercial customer classifications."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.automation_campaigns import audience_metrics
from app.db import Base
from app.models import Conversation, Customer, CustomerStoreProfile, Order, Organization, Store
from app.services.customer_classification_service import (
    get_customer_classification_analytics,
    get_customer_classification_map,
    get_customer_classifications,
)

engine = create_engine(
    "sqlite:///./test_customer_value_classifications.db",
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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
def org_stores(db):
    org = Organization(name="Classification Org", slug="classification-org", plan="growth", subscription_status="active")
    db.add(org)
    db.flush()
    store = Store(organization_id=org.id, name="Classification Store", slug="classification-store", country_code="CO", currency="COP", timezone="America/Bogota", default_language="es")
    other = Store(organization_id=org.id, name="Other Store", slug="classification-other-store", country_code="MX", currency="MXN", timezone="America/Mexico_City", default_language="es")
    db.add_all([store, other])
    db.flush()
    return org, store, other


def make_customer(db, org, store, name):
    customer = Customer(organization_id=org.id, name=name, phone=f"+5700{name[:3]}", email=None, country_code="CO")
    db.add(customer)
    db.flush()
    db.add(CustomerStoreProfile(organization_id=org.id, customer_id=customer.id, store_id=store.id, orders_count=0, total_spent=0, currency=store.currency))
    db.flush()
    return customer


def delivered(db, org, store, customer, number, amount, created_at):
    order = Order(
        organization_id=org.id,
        store_id=store.id,
        customer_id=customer.id,
        order_number=number,
        total_amount=amount,
        currency=store.currency,
        source="shopify",
        lifecycle_status="delivered",
        external_creation_status="created",
        created_at=created_at,
    )
    db.add(order)
    db.flush()
    return order


def test_classifications_use_explainable_delivered_rfm(db, org_stores):
    org, store, _ = org_stores
    now = datetime(2026, 9, 10, 12)
    champion = make_customer(db, org, store, "Champion")
    loyal = make_customer(db, org, store, "Loyal")
    recent = make_customer(db, org, store, "Recent")
    dormant = make_customer(db, org, store, "Dormant")
    prospect = make_customer(db, org, store, "Prospect")
    for i in range(5):
        delivered(db, org, store, champion, f"C-{i}", 200, now - timedelta(days=i + 1))
    for i in range(3):
        delivered(db, org, store, loyal, f"L-{i}", 50, now - timedelta(days=20 + i))
    delivered(db, org, store, recent, "R-1", 100, now - timedelta(days=10))
    delivered(db, org, store, dormant, "D-1", 70, now - timedelta(days=200))
    db.add(Conversation(organization_id=org.id, store_id=store.id, customer_id=prospect.id, channel="whatsapp", preview="Interested", mode="ai", created_at=now - timedelta(days=2), updated_at=now - timedelta(days=2)))
    db.commit()

    result = get_customer_classification_map(db, org.id, store.id, now=now)
    assert result[champion.id]["commercial_classification"] == "champion"
    assert result[champion.id]["value_tier"] == "high"
    assert result[champion.id]["rfm_frequency"] == 5
    assert result[champion.id]["rfm_monetary_value"] == 1000.0
    assert result[loyal.id]["commercial_classification"] == "loyal"
    assert result[recent.id]["commercial_classification"] == "recent_buyer"
    assert result[dormant.id]["commercial_classification"] == "dormant"
    assert result[prospect.id]["commercial_classification"] == "prospect"


def test_classification_is_strictly_store_scoped(db, org_stores):
    org, store, other = org_stores
    now = datetime(2026, 9, 10, 12)
    customer = make_customer(db, org, store, "Scoped")
    db.add(CustomerStoreProfile(organization_id=org.id, customer_id=customer.id, store_id=other.id, orders_count=1, total_spent=99999, currency=other.currency))
    delivered(db, org, other, customer, "OTHER-1", 99999, now - timedelta(days=1))
    db.commit()

    result = get_customer_classification_map(db, org.id, store.id, now=now)[customer.id]
    assert result["rfm_frequency"] == 0
    assert result["rfm_monetary_value"] == 0.0
    assert result["commercial_classification"] == "lead"


def test_classification_listing_filters_and_summarizes(db, org_stores):
    org, store, _ = org_stores
    now = datetime.utcnow()
    high = make_customer(db, org, store, "High Buyer")
    low = make_customer(db, org, store, "Low Buyer")
    make_customer(db, org, store, "No Buyer")
    for i in range(5):
        delivered(db, org, store, high, f"H-{i}", 500, now - timedelta(days=i + 1))
    delivered(db, org, store, low, "LOW-1", 20, now - timedelta(days=5))
    db.commit()

    result = get_customer_classifications(db, org.id, store.id, classification="champion")
    assert result["total"] == 1
    assert result["items"][0]["customer_id"] == high.id
    assert result["summary"]["total_customers"] == 3
    assert result["summary"]["buyers"] == 2
    assert result["summary"]["repeat_buyer_rate"] == 50.0
    assert result["summary"]["classification_counts"]["lead"] == 1


def test_analytics_period_keeps_current_lifetime_classification(db, org_stores):
    org, store, _ = org_stores
    now = datetime.utcnow().replace(microsecond=0)
    customer = make_customer(db, org, store, "Period Champion")
    for i in range(4):
        delivered(db, org, store, customer, f"OLD-{i}", 100, now - timedelta(days=20 + i))
    delivered(db, org, store, customer, "PERIOD", 600, now - timedelta(days=1))
    db.commit()

    result = get_customer_classification_analytics(db, org.id, store.id, now - timedelta(days=2), now)
    assert result["period_delivered_orders"] == 1
    assert result["period_delivered_revenue"] == 600.0
    assert result["top_customers"][0]["commercial_classification"] == "champion"
    assert result["top_customers"][0]["rfm_frequency"] == 5
    assert result["top_customers"][0]["rfm_monetary_value"] == 1000.0
    assert result["top_customers"][0]["period_delivered_revenue"] == 600.0


def test_automation_audience_filters_classification(db, org_stores):
    org, store, _ = org_stores
    now = datetime.utcnow().replace(microsecond=0)
    champion = make_customer(db, org, store, "Campaign Champion")
    make_customer(db, org, store, "Campaign Lead")
    for i in range(5):
        delivered(db, org, store, champion, f"AUTO-{i}", 200, now - timedelta(days=i + 1))
    db.commit()

    matches = audience_metrics(db, org.id, store.id, "dynamic", {"classification": ["champion"]})
    assert [item["id"] for item in matches] == [champion.id]
    assert matches[0]["value_tier"] == "high"
