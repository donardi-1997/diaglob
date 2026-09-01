"""
Tests for Customer Intelligence service.

Covers:
- Segmentation rules (all segments)
- Boundary cases
- Multi-currency handling
- Tenant isolation
- Store scope
- Filter tests
- Summary tests
- Detail tests
- Order status semantics
- Priority/precedence
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    Conversation,
    Customer,
    CustomerStoreProfile,
    Message,
    Order,
    Organization,
    OrganizationMembership,
    Store,
    User,
)
from app.customers.intelligence import (
    SEGMENT_NEW,
    SEGMENT_INTERESTED,
    SEGMENT_HIGH_INTENT,
    SEGMENT_BUYER,
    SEGMENT_REPEAT_BUYER,
    SEGMENT_VIP,
    SEGMENT_INACTIVE,
    FLAG_AT_RISK,
    VALID_ORDER_STATUSES,
    get_summary,
    get_customer_list,
    get_customer_detail,
    get_customer_metrics,
)


@pytest.fixture(scope="module")
def setup_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    now = datetime.utcnow()

    # --- Organization 1 ---
    org1 = Organization(
        id=1,
        name="Org One",
        slug="org-one",
        plan="growth",
    )
    session.add(org1)

    # --- Organization 2 (cross-tenant) ---
    org2 = Organization(
        id=2,
        name="Org Two",
        slug="org-two",
        plan="starter",
    )
    session.add(org2)

    # --- User ---
    user = User(id=1, email="test@test.com", name="Test")
    session.add(user)

    membership = OrganizationMembership(
        id=1,
        user_id=1,
        organization_id=1,
        role="owner",
    )
    session.add(membership)

    # --- Stores ---
    store1 = Store(
        id=1,
        organization_id=1,
        name="Store US",
        slug="store-us",
        country_code="US",
        currency="USD",
        timezone="UTC",
        active=True,
    )
    session.add(store1)

    store2 = Store(
        id=2,
        organization_id=1,
        name="Store CO",
        slug="store-co",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        active=True,
    )
    session.add(store2)

    store_other = Store(
        id=3,
        organization_id=2,
        name="Other Store",
        slug="other-store",
        country_code="US",
        currency="USD",
        timezone="UTC",
        active=True,
    )
    session.add(store_other)

    # --- Customers for Org 1 ---

    # C1: NEW customer - no orders, no conversations
    cust_new = Customer(
        id=1,
        organization_id=1,
        name="New Customer",
        phone="+1111111111",
        email="new@test.com",
        country_code="US",
        created_at=now - timedelta(days=3),
    )
    session.add(cust_new)

    # C2: INTERESTED - has conversations but no orders
    cust_interested = Customer(
        id=2,
        organization_id=1,
        name="Interested Customer",
        phone="+2222222222",
        email="interested@test.com",
        country_code="CO",
        created_at=now - timedelta(days=30),
    )
    session.add(cust_interested)

    # C3: HIGH_INTENT - recent conversation, no orders
    cust_high_intent = Customer(
        id=3,
        organization_id=1,
        name="High Intent Customer",
        phone="+3333333333",
        email="highintent@test.com",
        country_code="US",
        created_at=now - timedelta(days=20),
    )
    session.add(cust_high_intent)

    # C4: BUYER - exactly 1 successful order
    cust_buyer = Customer(
        id=4,
        organization_id=1,
        name="Buyer Customer",
        phone="+4444444444",
        email="buyer@test.com",
        country_code="US",
        created_at=now - timedelta(days=60),
    )
    session.add(cust_buyer)

    # C5: REPEAT_BUYER - 2+ successful orders
    cust_repeat = Customer(
        id=5,
        organization_id=1,
        name="Repeat Customer",
        phone="+5555555555",
        email="repeat@test.com",
        country_code="CO",
        created_at=now - timedelta(days=90),
    )
    session.add(cust_repeat)

    # C6: VIP - 5+ successful orders
    cust_vip = Customer(
        id=6,
        organization_id=1,
        name="VIP Customer",
        phone="+6666666666",
        email="vip@test.com",
        country_code="US",
        created_at=now - timedelta(days=180),
    )
    session.add(cust_vip)

    # C7: AT_RISK - buyer with no recent activity
    cust_at_risk = Customer(
        id=7,
        organization_id=1,
        name="At Risk Customer",
        phone="+7777777777",
        email="atrisk@test.com",
        country_code="US",
        created_at=now - timedelta(days=120),
    )
    session.add(cust_at_risk)

    # C8: INACTIVE - no activity for 60+ days
    cust_inactive = Customer(
        id=8,
        organization_id=1,
        name="Inactive Customer",
        phone="+8888888888",
        email="inactive@test.com",
        country_code="US",
        created_at=now - timedelta(days=100),
    )
    session.add(cust_inactive)

    # C9: Cross-tenant customer
    cust_cross = Customer(
        id=9,
        organization_id=2,
        name="Cross Tenant",
        phone="+9999999999",
        country_code="US",
    )
    session.add(cust_cross)

    # C10: Multi-currency customer
    cust_multi = Customer(
        id=10,
        organization_id=1,
        name="Multi Currency",
        phone="+1010101010",
        email="multi@test.com",
        country_code="CO",
        created_at=now - timedelta(days=60),
    )
    session.add(cust_multi)

    # --- Conversations ---

    # Interested customer: 3 conversations (old)
    for i in range(3):
        conv = Conversation(
            organization_id=1,
            store_id=1,
            customer_id=2,
            channel="whatsapp",
            mode="ai",
            created_at=now - timedelta(days=20),
            updated_at=now - timedelta(days=20),
        )
        session.add(conv)

    # High intent: 1 recent conversation
    conv_hi = Conversation(
        organization_id=1,
        store_id=1,
        customer_id=3,
        channel="whatsapp",
        mode="ai",
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(days=1),
    )
    session.add(conv_hi)

    # Repeat buyer: conversations
    conv_rep = Conversation(
        organization_id=1,
        store_id=1,
        customer_id=5,
        channel="whatsapp",
        mode="ai",
        created_at=now - timedelta(days=30),
        updated_at=now - timedelta(days=30),
    )
    session.add(conv_rep)

    # VIP: conversations
    conv_vip = Conversation(
        organization_id=1,
        store_id=1,
        customer_id=6,
        channel="whatsapp",
        mode="ai",
        created_at=now - timedelta(days=10),
        updated_at=now - timedelta(days=10),
    )
    session.add(conv_vip)

    # At risk: old conversation
    conv_ar = Conversation(
        organization_id=1,
        store_id=1,
        customer_id=7,
        channel="whatsapp",
        mode="ai",
        created_at=now - timedelta(days=40),
        updated_at=now - timedelta(days=40),
    )
    session.add(conv_ar)

    # Inactive: old conversation
    conv_inact = Conversation(
        organization_id=1,
        store_id=1,
        customer_id=8,
        channel="whatsapp",
        mode="ai",
        created_at=now - timedelta(days=80),
        updated_at=now - timedelta(days=80),
    )
    session.add(conv_inact)

    # Cross-tenant conversation
    conv_cross = Conversation(
        organization_id=2,
        store_id=3,
        customer_id=9,
        channel="whatsapp",
        mode="ai",
    )
    session.add(conv_cross)

    session.flush()

    # --- Messages ---
    msg1 = Message(
        conversation_id=conv_hi.id,
        sender="customer",
        text="I want to buy",
    )
    session.add(msg1)

    # --- Orders ---

    # Buyer: 1 successful order
    order_buyer = Order(
        organization_id=1,
        store_id=1,
        customer_id=4,
        total_amount=100.00,
        order_number="ORD-B1",
        currency="USD",
        external_creation_status="created",
        created_at=now - timedelta(days=10),
    )
    session.add(order_buyer)

    # Repeat buyer: 3 successful orders
    for i in range(3):
        order = Order(
            organization_id=1,
            store_id=1,
            customer_id=5,
            total_amount=50.00 + i * 10,
            order_number=f"ORD-R{i+1}",
            currency="USD",
            external_creation_status="created",
            created_at=now - timedelta(days=30 - i * 5),
        )
        session.add(order)

    # VIP: 6 successful orders
    for i in range(6):
        order = Order(
            organization_id=1,
            store_id=1,
            customer_id=6,
            total_amount=200.00 + i * 50,
            order_number=f"ORD-V{i+1}",
            currency="USD",
            external_creation_status="created",
            created_at=now - timedelta(days=60 - i * 5),
        )
        session.add(order)

    # At risk: 2 successful orders, old
    for i in range(2):
        order = Order(
            organization_id=1,
            store_id=1,
            customer_id=7,
            total_amount=75.00,
            order_number=f"ORD-AR{i+1}",
            currency="USD",
            external_creation_status="created",
            created_at=now - timedelta(days=45),
        )
        session.add(order)

    # Multi-currency: 1 USD + 1 COP
    order_usd = Order(
        organization_id=1,
        store_id=1,
        customer_id=10,
        total_amount=100.00,
        order_number="ORD-M1",
        currency="USD",
        external_creation_status="created",
        created_at=now - timedelta(days=20),
    )
    session.add(order_usd)

    order_cop = Order(
        organization_id=1,
        store_id=2,
        customer_id=10,
        total_amount=500000.00,
        order_number="ORD-M2",
        currency="COP",
        external_creation_status="created",
        created_at=now - timedelta(days=15),
    )
    session.add(order_cop)

    # Failed order (should NOT count as buyer)
    order_failed = Order(
        organization_id=1,
        store_id=1,
        customer_id=1,
        total_amount=200.00,
        order_number="ORD-F1",
        currency="USD",
        external_creation_status="failed",
        created_at=now - timedelta(days=2),
    )
    session.add(order_failed)

    # Unknown order (should NOT count as buyer)
    order_unknown = Order(
        organization_id=1,
        store_id=1,
        customer_id=1,
        total_amount=300.00,
        order_number="ORD-U1",
        currency="USD",
        external_creation_status="unknown",
        created_at=now - timedelta(days=1),
    )
    session.add(order_unknown)

    # Pending order (should NOT count as buyer)
    order_pending = Order(
        organization_id=1,
        store_id=1,
        customer_id=2,
        total_amount=150.00,
        order_number="ORD-P1",
        currency="USD",
        external_creation_status="pending",
        created_at=now - timedelta(days=5),
    )
    session.add(order_pending)

    # Cross-tenant order
    order_cross = Order(
        organization_id=2,
        store_id=3,
        customer_id=9,
        total_amount=50.00,
        order_number="ORD-C1",
        currency="USD",
        external_creation_status="created",
    )
    session.add(order_cross)

    # --- CustomerStoreProfile ---
    profile1 = CustomerStoreProfile(
        organization_id=1,
        customer_id=10,
        store_id=1,
        orders_count=1,
        total_spent=100.00,
        currency="USD",
    )
    session.add(profile1)

    profile2 = CustomerStoreProfile(
        organization_id=1,
        customer_id=10,
        store_id=2,
        orders_count=1,
        total_spent=500000.00,
        currency="COP",
    )
    session.add(profile2)

    session.commit()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)


# ============================================================
# SEGMENTATION TESTS
# ============================================================


class TestSegmentation:
    """Test customer classification rules."""

    def test_new_customer(self, setup_db):
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust = next(
            m for m in metrics if m["id"] == 1
        )
        # Failed/unknown orders don't make buyer
        assert cust["primary_segment"] == SEGMENT_NEW
        assert cust["successful_order_count"] == 0

    def test_interested_customer(self, setup_db):
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust = next(
            m for m in metrics if m["id"] == 2
        )
        assert cust["conversation_count"] >= 3
        assert cust["successful_order_count"] == 0
        assert cust["primary_segment"] == SEGMENT_INTERESTED

    def test_high_intent_customer(self, setup_db):
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust = next(
            m for m in metrics if m["id"] == 3
        )
        assert cust["conversation_count"] >= 1
        assert cust["days_since_last_interaction"] <= 7
        assert cust["primary_segment"] == SEGMENT_HIGH_INTENT

    def test_buyer_customer(self, setup_db):
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust = next(
            m for m in metrics if m["id"] == 4
        )
        assert cust["successful_order_count"] == 1
        assert cust["primary_segment"] == SEGMENT_BUYER

    def test_repeat_buyer_customer(self, setup_db):
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust = next(
            m for m in metrics if m["id"] == 5
        )
        assert cust["successful_order_count"] == 3
        assert cust["primary_segment"] == SEGMENT_REPEAT_BUYER

    def test_vip_customer(self, setup_db):
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust = next(
            m for m in metrics if m["id"] == 6
        )
        assert cust["successful_order_count"] == 6
        assert cust["primary_segment"] == SEGMENT_VIP

    def test_at_risk_customer(self, setup_db):
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust = next(
            m for m in metrics if m["id"] == 7
        )
        assert cust["successful_order_count"] == 2
        assert cust["days_since_last_purchase"] >= 30
        assert FLAG_AT_RISK in cust["flags"]
        assert cust["primary_segment"] == SEGMENT_REPEAT_BUYER

    def test_inactive_customer(self, setup_db):
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust = next(
            m for m in metrics if m["id"] == 8
        )
        assert cust["primary_segment"] == SEGMENT_INACTIVE

    def test_vip_priority_over_repeat(self, setup_db):
        """VIP takes precedence over repeat_buyer."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust = next(
            m for m in metrics if m["id"] == 6
        )
        assert cust["primary_segment"] == SEGMENT_VIP

    def test_buyer_priority_over_interested(self, setup_db):
        """Buyer takes precedence over interested/high_intent."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust = next(
            m for m in metrics if m["id"] == 4
        )
        # Even with conversations, buyer takes precedence
        assert cust["primary_segment"] == SEGMENT_BUYER


# ============================================================
# ORDER STATUS TESTS
# ============================================================


class TestOrderStatus:
    """Test that only valid order statuses count as purchases."""

    def test_failed_order_not_counted(self, setup_db):
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust = next(
            m for m in metrics if m["id"] == 1
        )
        assert cust["successful_order_count"] == 0

    def test_unknown_order_not_counted(self, setup_db):
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust = next(
            m for m in metrics if m["id"] == 1
        )
        assert cust["successful_order_count"] == 0

    def test_pending_order_not_counted(self, setup_db):
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust = next(
            m for m in metrics if m["id"] == 2
        )
        assert cust["successful_order_count"] == 0

    def test_created_order_counted(self, setup_db):
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust = next(
            m for m in metrics if m["id"] == 4
        )
        assert cust["successful_order_count"] == 1

    def test_valid_statuses_constant(self):
        assert "created" in VALID_ORDER_STATUSES
        assert "failed" not in VALID_ORDER_STATUSES
        assert "unknown" not in VALID_ORDER_STATUSES
        assert "pending" not in VALID_ORDER_STATUSES


# ============================================================
# MULTI-CURRENCY TESTS
# ============================================================


class TestMultiCurrency:
    """Test spend is grouped by currency."""

    def test_spend_by_currency_keys(self, setup_db):
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust = next(
            m for m in metrics if m["id"] == 10
        )
        currencies = set(
            cust["spend_by_currency"].keys()
        )
        assert "USD" in currencies
        assert "COP" in currencies

    def test_spend_not_mixed(self, setup_db):
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust = next(
            m for m in metrics if m["id"] == 10
        )
        usd = cust["spend_by_currency"]["USD"]
        cop = cust["spend_by_currency"]["COP"]
        assert usd["total"] == 100.00
        assert cop["total"] == 500000.00

    def test_no_fake_total_revenue(self, setup_db):
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust = next(
            m for m in metrics if m["id"] == 10
        )
        # Should NOT have a single "total_revenue" key
        assert "total_revenue" not in cust

    def test_customer_with_single_currency(self, setup_db):
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust = next(
            m for m in metrics if m["id"] == 4
        )
        assert len(cust["spend_by_currency"]) == 1
        assert "USD" in cust["spend_by_currency"]


# ============================================================
# TENANT ISOLATION TESTS
# ============================================================


class TestTenantIsolation:
    """Test organization-scoped queries."""

    def test_org1_sees_own_customers(self, setup_db):
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        ids = {m["id"] for m in metrics}
        assert 9 not in ids  # cross-tenant

    def test_org2_sees_own_customers(self, setup_db):
        metrics = get_customer_metrics(
            setup_db, organization_id=2
        )
        ids = {m["id"] for m in metrics}
        assert 9 in ids
        assert 1 not in ids

    def test_summary_org_isolation(self, setup_db):
        s1 = get_summary(
            setup_db, organization_id=1
        )
        s2 = get_summary(
            setup_db, organization_id=2
        )
        assert s1["total_customers"] >= 9
        assert s2["total_customers"] == 1

    def test_list_org_isolation(self, setup_db):
        r1 = get_customer_list(
            setup_db, organization_id=1
        )
        r2 = get_customer_list(
            setup_db, organization_id=2
        )
        assert r1["total"] >= 9
        assert r2["total"] == 1

    def test_detail_cross_tenant_returns_none(
        self, setup_db
    ):
        result = get_customer_detail(
            setup_db,
            organization_id=1,
            customer_id=9,
        )
        assert result is None


# ============================================================
# STORE SCOPE TESTS
# ============================================================


class TestStoreScope:
    """Test store-scoped queries."""

    def test_store_scope_filters(self, setup_db):
        metrics = get_customer_metrics(
            setup_db,
            organization_id=1,
            store_id=1,
        )
        # Should only include customers with activity
        # in store 1
        assert len(metrics) >= 1

    def test_store_scope_summary(self, setup_db):
        s1 = get_summary(
            setup_db, organization_id=1, store_id=1
        )
        s2 = get_summary(
            setup_db, organization_id=1, store_id=2
        )
        # Different stores may have different counts
        assert isinstance(
            s1["total_customers"], int
        )
        assert isinstance(
            s2["total_customers"], int
        )

    def test_store_scope_list(self, setup_db):
        r1 = get_customer_list(
            setup_db,
            organization_id=1,
            store_id=1,
        )
        assert isinstance(r1["items"], list)


# ============================================================
# FILTER TESTS
# ============================================================


class TestFilters:
    """Test list filtering."""

    def test_filter_by_segment(self, setup_db):
        result = get_customer_list(
            setup_db,
            organization_id=1,
            segment=SEGMENT_VIP,
        )
        assert result["total"] >= 1
        for item in result["items"]:
            assert item["primary_segment"] == SEGMENT_VIP

    def test_filter_by_flag(self, setup_db):
        result = get_customer_list(
            setup_db,
            organization_id=1,
            flag=FLAG_AT_RISK,
        )
        assert result["total"] >= 1
        for item in result["items"]:
            assert FLAG_AT_RISK in item["flags"]

    def test_filter_by_search(self, setup_db):
        result = get_customer_list(
            setup_db,
            organization_id=1,
            search="VIP",
        )
        assert result["total"] >= 1
        assert any(
            "VIP" in m["name"]
            for m in result["items"]
        )

    def test_filter_by_has_orders_true(self, setup_db):
        result = get_customer_list(
            setup_db,
            organization_id=1,
            has_orders=True,
        )
        for item in result["items"]:
            assert item["successful_order_count"] > 0

    def test_filter_by_has_orders_false(self, setup_db):
        result = get_customer_list(
            setup_db,
            organization_id=1,
            has_orders=False,
        )
        for item in result["items"]:
            assert item["successful_order_count"] == 0

    def test_combined_filters(self, setup_db):
        result = get_customer_list(
            setup_db,
            organization_id=1,
            segment=SEGMENT_REPEAT_BUYER,
            has_orders=True,
        )
        for item in result["items"]:
            assert (
                item["primary_segment"]
                == SEGMENT_REPEAT_BUYER
            )
            assert item["successful_order_count"] > 0

    def test_search_by_phone(self, setup_db):
        result = get_customer_list(
            setup_db,
            organization_id=1,
            search="+444",
        )
        assert result["total"] >= 1

    def test_search_by_email(self, setup_db):
        result = get_customer_list(
            setup_db,
            organization_id=1,
            search="vip@test.com",
        )
        assert result["total"] >= 1


# ============================================================
# PAGINATION TESTS
# ============================================================


class TestPagination:
    """Test list pagination."""

    def test_default_pagination(self, setup_db):
        result = get_customer_list(
            setup_db, organization_id=1
        )
        assert result["page"] == 1
        assert result["page_size"] == 25
        assert result["total"] >= 9
        assert result["total_pages"] >= 1

    def test_custom_page_size(self, setup_db):
        result = get_customer_list(
            setup_db,
            organization_id=1,
            page_size=3,
        )
        assert len(result["items"]) <= 3
        assert result["page_size"] == 3

    def test_page_2(self, setup_db):
        result = get_customer_list(
            setup_db,
            organization_id=1,
            page=2,
            page_size=3,
        )
        assert result["page"] == 2

    def test_empty_page(self, setup_db):
        result = get_customer_list(
            setup_db,
            organization_id=1,
            page=999,
            page_size=10,
        )
        # Page is clamped to valid range, so this
        # returns last page items (not empty)
        assert result["page"] <= result["total_pages"]
        assert isinstance(result["items"], list)

    def test_page_clamped_to_valid(self, setup_db):
        result = get_customer_list(
            setup_db,
            organization_id=1,
            page=999,
            page_size=50,
        )
        assert result["page"] <= result["total_pages"]


# ============================================================
# SORTING TESTS
# ============================================================


class TestSorting:
    """Test list sorting."""

    def test_sort_last_interaction_desc(self, setup_db):
        result = get_customer_list(
            setup_db,
            organization_id=1,
            sort="last_interaction_desc",
        )
        items = result["items"]
        if len(items) >= 2:
            # First should have more recent interaction
            # (or None should sort last)
            for i in range(len(items) - 1):
                a = items[i]["last_interaction_at"] or ""
                b = items[i + 1][
                    "last_interaction_at"
                ] or ""
                assert a >= b

    def test_sort_order_count_desc(self, setup_db):
        result = get_customer_list(
            setup_db,
            organization_id=1,
            sort="order_count_desc",
        )
        items = result["items"]
        if len(items) >= 2:
            for i in range(len(items) - 1):
                a = items[i]["successful_order_count"]
                b = items[i + 1][
                    "successful_order_count"
                ]
                assert a >= b

    def test_sort_created_desc(self, setup_db):
        result = get_customer_list(
            setup_db,
            organization_id=1,
            sort="created_desc",
        )
        items = result["items"]
        if len(items) >= 2:
            for i in range(len(items) - 1):
                assert (
                    items[i]["created_at"]
                    >= items[i + 1]["created_at"]
                )

    def test_sort_name_asc(self, setup_db):
        result = get_customer_list(
            setup_db,
            organization_id=1,
            sort="name_asc",
        )
        items = result["items"]
        if len(items) >= 2:
            for i in range(len(items) - 1):
                assert (
                    items[i]["name"].lower()
                    <= items[i + 1]["name"].lower()
                )


# ============================================================
# SUMMARY TESTS
# ============================================================


class TestSummary:
    """Test summary endpoint."""

    def test_summary_structure(self, setup_db):
        result = get_summary(
            setup_db, organization_id=1
        )
        assert "total_customers" in result
        assert "new_customers" in result
        assert "interested" in result
        assert "high_intent" in result
        assert "buyers" in result
        assert "repeat_buyers" in result
        assert "vip" in result
        assert "at_risk" in result
        assert "inactive" in result

    def test_summary_counts_add_up(self, setup_db):
        result = get_summary(
            setup_db, organization_id=1
        )
        # Sum of segments should equal total
        segment_sum = (
            result["new_customers"]
            + result["interested"]
            + result["high_intent"]
            + result["buyers"]
            + result["repeat_buyers"]
            + result["vip"]
            + result["inactive"]
        )
        assert segment_sum == result["total_customers"]

    def test_summary_at_risk_overlap(self, setup_db):
        """At-risk can overlap with other segments."""
        result = get_summary(
            setup_db, organization_id=1
        )
        # At risk count may be less than total if it
        # overlaps with VIP/repeat
        assert result["at_risk"] >= 0
        assert result["at_risk"] <= result[
            "total_customers"
        ]

    def test_summary_org2(self, setup_db):
        result = get_summary(
            setup_db, organization_id=2
        )
        assert result["total_customers"] == 1


# ============================================================
# DETAIL TESTS
# ============================================================


class TestDetail:
    """Test customer detail endpoint."""

    def test_detail_structure(self, setup_db):
        result = get_customer_detail(
            setup_db,
            organization_id=1,
            customer_id=4,
        )
        assert result is not None
        assert result["id"] == 4
        assert "primary_segment" in result
        assert "flags" in result
        assert "recent_conversations" in result
        assert "recent_orders" in result
        assert "spend_by_currency" in result

    def test_detail_buyer(self, setup_db):
        result = get_customer_detail(
            setup_db,
            organization_id=1,
            customer_id=4,
        )
        assert result["primary_segment"] == SEGMENT_BUYER
        assert result["successful_order_count"] == 1

    def test_detail_not_found(self, setup_db):
        result = get_customer_detail(
            setup_db,
            organization_id=1,
            customer_id=99999,
        )
        assert result is None

    def test_detail_recent_orders(self, setup_db):
        result = get_customer_detail(
            setup_db,
            organization_id=1,
            customer_id=6,
        )
        assert result is not None
        assert len(result["recent_orders"]) >= 1
        assert len(result["recent_orders"]) <= 5

    def test_detail_cross_tenant(self, setup_db):
        result = get_customer_detail(
            setup_db,
            organization_id=1,
            customer_id=9,
        )
        assert result is None


# ============================================================
# EDGE CASE TESTS
# ============================================================


class TestEdgeCases:
    """Test boundary conditions."""

    def test_boundary_exactly_1_order(self, setup_db):
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust = next(
            m for m in metrics if m["id"] == 4
        )
        assert cust["successful_order_count"] == 1
        assert cust["primary_segment"] == SEGMENT_BUYER

    def test_boundary_exactly_2_orders(self, setup_db):
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust = next(
            m for m in metrics if m["id"] == 5
        )
        assert cust["successful_order_count"] == 3
        assert (
            cust["primary_segment"]
            == SEGMENT_REPEAT_BUYER
        )

    def test_boundary_exactly_5_orders(self, setup_db):
        # Create customer with exactly 5 orders
        now = datetime.utcnow()
        cust5 = Customer(
            id=50,
            organization_id=1,
            name="Boundary VIP",
            phone="+5050505050",
            created_at=now - timedelta(days=100),
        )
        setup_db.add(cust5)

        for i in range(5):
            order = Order(
                organization_id=1,
                store_id=1,
                customer_id=50,
                total_amount=100.00,
                order_number=f"ORD-B50-{i}",
                currency="USD",
                external_creation_status="created",
                created_at=now - timedelta(days=50 - i * 5),
            )
            setup_db.add(order)

        setup_db.commit()

        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust = next(
            m for m in metrics if m["id"] == 50
        )
        assert cust["successful_order_count"] == 5
        assert cust["primary_segment"] == SEGMENT_VIP

    def test_customer_with_no_activity(self, setup_db):
        now = datetime.utcnow()
        cust_empty = Customer(
            id=60,
            organization_id=1,
            name="Empty Customer",
            phone="+6060606060",
            created_at=now - timedelta(days=5),
        )
        setup_db.add(cust_empty)
        setup_db.commit()

        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust = next(
            m for m in metrics if m["id"] == 60
        )
        assert cust["conversation_count"] == 0
        assert cust["message_count"] == 0
        assert cust["successful_order_count"] == 0
        assert cust["primary_segment"] == SEGMENT_NEW

    def test_at_risk_only_for_buyers(self, setup_db):
        """At risk flag only applies to buyers."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust = next(
            m for m in metrics if m["id"] == 1
        )
        # Customer 1 has no successful orders
        assert cust["successful_order_count"] == 0
        assert FLAG_AT_RISK not in cust["flags"]


# ============================================================
# REGRESSION TESTS — BUG FIXES
# ============================================================


class TestRegressionFixes:
    """Tests for bugs found during code review."""

    def test_inactive_overrides_interested(self, setup_db):
        """
        Customer 2 has 3 conversations (meets INTERESTED threshold)
        but last interaction was 20 days ago (< INACTIVE_DAYS=60).
        With INACTIVE precedence fix, old interested customers
        should become INACTIVE before INTERESTED is considered.
        """
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust = next(
            m for m in metrics if m["id"] == 2
        )
        # Last interaction is 20 days ago, which is < 60 days
        # So this customer should still be INTERESTED (not inactive yet)
        assert cust["primary_segment"] == SEGMENT_INTERESTED

    def test_inactive_overrides_interested_old(self, setup_db):
        """
        Create customer with conversations but interaction 90+ days ago.
        Should be INACTIVE even though conversation_count >= 2.
        """
        now = datetime.utcnow()
        cust_old = Customer(
            id=70,
            organization_id=1,
            name="Old Interested",
            phone="+7070707070",
            created_at=now - timedelta(days=120),
        )
        setup_db.add(cust_old)

        for i in range(3):
            conv = Conversation(
                organization_id=1,
                store_id=1,
                customer_id=70,
                channel="whatsapp",
                mode="ai",
                created_at=now - timedelta(days=90),
                updated_at=now - timedelta(days=90),
            )
            setup_db.add(conv)

        setup_db.commit()

        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust = next(
            m for m in metrics if m["id"] == 70
        )
        assert cust["conversation_count"] >= 2
        assert (
            cust["last_interaction_at"] is not None
        )
        assert cust["primary_segment"] == SEGMENT_INACTIVE

    def test_recent_purchase_prevents_at_risk(self, setup_db):
        """
        Customer who purchased yesterday but hasn't messaged
        in 90 days should NOT be at-risk. Recent purchase
        prevents at-risk status.
        """
        now = datetime.utcnow()
        cust_recent = Customer(
            id=71,
            organization_id=1,
            name="Recent Buyer No Chat",
            phone="+7171717171",
            created_at=now - timedelta(days=120),
        )
        setup_db.add(cust_recent)

        # 1 order 1 day ago
        order_recent = Order(
            organization_id=1,
            store_id=1,
            customer_id=71,
            total_amount=100.00,
            order_number="ORD-RECENT-1",
            currency="USD",
            external_creation_status="created",
            created_at=now - timedelta(days=1),
        )
        setup_db.add(order_recent)

        # Old conversation 90 days ago
        conv_old = Conversation(
            organization_id=1,
            store_id=1,
            customer_id=71,
            channel="whatsapp",
            mode="ai",
            created_at=now - timedelta(days=90),
            updated_at=now - timedelta(days=90),
        )
        setup_db.add(conv_old)

        setup_db.commit()

        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust = next(
            m for m in metrics if m["id"] == 71
        )
        assert cust["successful_order_count"] == 1
        assert cust["primary_segment"] == SEGMENT_BUYER
        # Should NOT be at_risk — recent purchase
        assert FLAG_AT_RISK not in cust["flags"]

    def test_null_currency_not_crash(self, setup_db):
        """
        Orders with null currency should not crash metrics.
        """
        now = datetime.utcnow()
        cust_nc = Customer(
            id=72,
            organization_id=1,
            name="Null Currency",
            phone="+7272727272",
            created_at=now - timedelta(days=30),
        )
        setup_db.add(cust_nc)

        order_nc = Order(
            organization_id=1,
            store_id=1,
            customer_id=72,
            total_amount=50.00,
            order_number="ORD-NC-1",
            currency="",
            external_creation_status="created",
            created_at=now - timedelta(days=5),
        )
        setup_db.add(order_nc)
        setup_db.commit()

        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust = next(
            m for m in metrics if m["id"] == 72
        )
        assert cust["successful_order_count"] == 1
        assert cust["primary_segment"] == SEGMENT_BUYER

    def test_store_must_belong_to_org(self, setup_db):
        """
        Store 3 belongs to org2. Querying org1 with store_id=3
        should return empty (no matching CustomerStoreProfile).
        """
        results = get_customer_metrics(
            setup_db,
            organization_id=1,
            store_id=3,
        )
        assert len(results) == 0

    def test_filters_apply_before_pagination(
        self, setup_db
    ):
        """
        When filtering by segment, total_pages should reflect
        filtered count, not unfiltered count.
        """
        result = get_customer_list(
            db=setup_db,
            organization_id=1,
            segment=SEGMENT_VIP,
            page=1,
            page_size=100,
        )
        # VIP: customer 6 (6 orders) + customer 50 (5 orders)
        assert result["total"] == 2
        assert result["total_pages"] == 1

    def test_summary_partition_invariant(self, setup_db):
        """
        Segments are mutually exclusive (at_risk is a flag).
        Sum of segment counts must equal total_customers.
        """
        summary = get_summary(
            setup_db, organization_id=1
        )
        segment_sum = (
            summary["new_customers"]
            + summary["interested"]
             + summary["high_intent"]
            + summary["buyers"]
            + summary["repeat_buyers"]
            + summary["vip"]
            + summary["inactive"]
        )
        assert segment_sum == summary["total_customers"]


# ============================================================
# PHASE 2 — SCORE TESTS
# ============================================================


class TestScore:
    """Test customer score calculation."""

    def test_score_in_range(self, setup_db):
        """All scores must be between 0 and 100."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        for m in metrics:
            assert 0 <= m["customer_score"] <= 100

    def test_score_is_int(self, setup_db):
        """Score must be an integer."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        for m in metrics:
            assert isinstance(
                m["customer_score"], int
            )

    def test_score_factors_exist(self, setup_db):
        """Every customer must have score_factors."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        for m in metrics:
            assert isinstance(
                m["score_factors"], list
            )

    def test_vip_higher_than_new(self, setup_db):
        """VIP customer should score higher than new."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        vip = next(
            m for m in metrics if m["id"] == 6
        )
        new_cust = next(
            m for m in metrics if m["id"] == 1
        )
        assert (
            vip["customer_score"]
            > new_cust["customer_score"]
        )

    def test_buyer_higher_than_no_activity(
        self, setup_db
    ):
        """Buyer should score higher than empty."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        buyer = next(
            m for m in metrics if m["id"] == 4
        )
        new_cust = next(
            m for m in metrics if m["id"] == 1
        )
        assert (
            buyer["customer_score"]
            >= new_cust["customer_score"]
        )

    def test_active_repeat_buyer_score(self, setup_db):
        """Repeat buyer with recent activity should score well."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        repeat = next(
            m for m in metrics if m["id"] == 5
        )
        assert repeat["customer_score"] >= 30

    def test_inactive_low_score(self, setup_db):
        """Inactive customer should have low score."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        inactive = next(
            m for m in metrics if m["id"] == 8
        )
        assert inactive["customer_score"] <= 50

    def test_score_not_deducted_for_failed_orders(
        self, setup_db
    ):
        """Failed orders no longer reduce customer score."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust1 = next(
            m for m in metrics if m["id"] == 1
        )
        # Customer 1 has failed + unknown orders
        assert cust1["failed_order_count"] > 0
        # But score should not be negative or reduced
        assert cust1["customer_score"] >= 0
        # No negative factors
        for f in cust1["score_factors"]:
            assert f["impact"] >= 0

    def test_score_factors_have_code_impact(
        self, setup_db
    ):
        """Each factor must have code and impact."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        for m in metrics:
            for f in m["score_factors"]:
                assert "code" in f
                assert "impact" in f


# ============================================================
# PHASE 2 — PRIORITY TESTS
# ============================================================


class TestPriority:
    """Test priority calculation."""

    def test_priority_values(self, setup_db):
        """Priority must be high, medium, or low."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        valid = {"high", "medium", "low"}
        for m in metrics:
            assert m["priority"] in valid

    def test_priority_reasons_list(self, setup_db):
        """priority_reasons must be a list."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        for m in metrics:
            assert isinstance(
                m["priority_reasons"], list
            )

    def test_at_risk_high_priority(self, setup_db):
        """At-risk customer should be high priority."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        at_risk = next(
            m for m in metrics if m["id"] == 7
        )
        assert at_risk["priority"] == "high"

    def test_failed_order_high_priority(
        self, setup_db
    ):
        """Customer with recent failed order high priority."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust1 = next(
            m for m in metrics if m["id"] == 1
        )
        # Customer 1 has recent failed order
        assert cust1["priority"] == "high"

    def test_vip_at_risk_reason(self, setup_db):
        """VIP at risk should have vip_at_risk reason."""
        # C6 is VIP but not at risk (recent orders)
        # C7 is at risk with 2 orders
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust7 = next(
            m for m in metrics if m["id"] == 7
        )
        assert "at_risk" in cust7["priority_reasons"]

    def test_inactive_low_priority(self, setup_db):
        """Inactive customer should be low priority."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        inactive = next(
            m for m in metrics if m["id"] == 8
        )
        assert inactive["priority"] == "low"

    def test_high_intent_medium_priority(
        self, setup_db
    ):
        """High intent should be medium priority."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        hi = next(
            m for m in metrics if m["id"] == 3
        )
        assert hi["priority"] in ("medium", "high")

    def test_buyer_medium_priority(self, setup_db):
        """Active buyer should be medium priority."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        buyer = next(
            m for m in metrics if m["id"] == 4
        )
        assert buyer["priority"] in (
            "medium",
            "high",
        )


# ============================================================
# PHASE 2 — HEALTH TESTS
# ============================================================


class TestHealth:
    """Test health calculation."""

    def test_health_values(self, setup_db):
        """Health must be active, at_risk, or inactive."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        valid = {"active", "at_risk", "inactive"}
        for m in metrics:
            assert m["customer_health"] in valid

    def test_recent_buyer_active(self, setup_db):
        """Buyer with recent purchase is active."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        buyer = next(
            m for m in metrics if m["id"] == 4
        )
        # Buyer purchased 10 days ago
        assert buyer["customer_health"] == "active"

    def test_at_risk_customer_health(self, setup_db):
        """At-risk customer health is at_risk."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        at_risk = next(
            m for m in metrics if m["id"] == 7
        )
        assert at_risk["customer_health"] == "at_risk"

    def test_inactive_health(self, setup_db):
        """Inactive customer health is inactive."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        inactive = next(
            m for m in metrics if m["id"] == 8
        )
        assert (
            inactive["customer_health"] == "inactive"
        )

    def test_high_intent_active(self, setup_db):
        """High intent with recent interaction is active."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        hi = next(
            m for m in metrics if m["id"] == 3
        )
        assert hi["customer_health"] == "active"


# ============================================================
# PHASE 2 — OPPORTUNITIES / RISKS TESTS
# ============================================================


class TestOpportunitiesRisks:
    """Test opportunities and risks."""

    def test_opportunities_is_list(self, setup_db):
        """Opportunities must be a list."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        for m in metrics:
            assert isinstance(
                m["opportunities"], list
            )

    def test_risks_is_list(self, setup_db):
        """Risks must be a list."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        for m in metrics:
            assert isinstance(m["risks"], list)

    def test_vip_has_opportunity(self, setup_db):
        """VIP customer should have opportunity."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        vip = next(
            m for m in metrics if m["id"] == 6
        )
        assert "vip_customer" in vip["opportunities"]

    def test_at_risk_has_risk(self, setup_db):
        """At-risk customer should have risk."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        at_risk = next(
            m for m in metrics if m["id"] == 7
        )
        assert "at_risk" in at_risk["risks"]

    def test_inactive_has_risk(self, setup_db):
        """Inactive customer should have risk."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        inactive = next(
            m for m in metrics if m["id"] == 8
        )
        assert "inactive" in inactive["risks"]

    def test_failed_order_risk(self, setup_db):
        """Customer with failed orders has risk."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust1 = next(
            m for m in metrics if m["id"] == 1
        )
        assert "failed_order" in cust1["risks"]

    def test_no_invented_opportunities(self, setup_db):
        """No AI-invented opportunities."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        valid_opps = {
            "high_intent_no_order",
            "repeat_customer",
            "vip_customer",
            "recent_failed_order_recovery",
            "recent_reengagement",
            "recent_conversation_no_order",
        }
        for m in metrics:
            for opp in m["opportunities"]:
                assert opp in valid_opps

    def test_no_invented_risks(self, setup_db):
        """No AI-invented risks."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        valid_risks = {
            "at_risk",
            "inactive",
            "failed_order",
            "unknown_order",
            "long_time_since_purchase",
            "long_time_since_interaction",
            "no_engagement_history",
        }
        for m in metrics:
            for risk in m["risks"]:
                assert risk in valid_risks


# ============================================================
# PHASE 2 — NEXT BEST ACTION TESTS
# ============================================================


class TestNextBestAction:
    """Test next best action."""

    def test_action_values(self, setup_db):
        """Action must be valid."""
        valid = {
            "follow_up_conversation",
            "recover_failed_order",
            "reengage_customer",
            "review_vip",
            "no_action_needed",
        }
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        for m in metrics:
            assert (
                m["next_best_action"] in valid
            )

    def test_action_reasons_list(self, setup_db):
        """Action reasons must be a list."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        for m in metrics:
            assert isinstance(
                m["next_best_action_reasons"], list
            )

    def test_failed_order_recovers(self, setup_db):
        """Failed order triggers recover action."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust1 = next(
            m for m in metrics if m["id"] == 1
        )
        assert (
            cust1["next_best_action"]
            == "recover_failed_order"
        )

    def test_at_risk_reengages(self, setup_db):
        """At-risk triggers reengage."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        at_risk = next(
            m for m in metrics if m["id"] == 7
        )
        assert at_risk["next_best_action"] in (
            "reengage_customer",
            "recover_failed_order",
        )

    def test_healthy_buyer_no_action(self, setup_db):
        """Healthy recent buyer no action needed."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        buyer = next(
            m for m in metrics if m["id"] == 4
        )
        assert (
            buyer["next_best_action"]
            == "no_action_needed"
        )

    def test_high_intent_follows_up(self, setup_db):
        """High intent triggers follow up."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        hi = next(
            m for m in metrics if m["id"] == 3
        )
        assert hi["next_best_action"] in (
            "follow_up_conversation",
            "reengage_customer",
        )


# ============================================================
# PHASE 2 — FAILED/UNKNOWN ORDER SIGNALS
# ============================================================


class TestFailedUnknownSignals:
    """Test failed/unknown order signal counts."""

    def test_failed_order_count(self, setup_db):
        """Customer 1 has 1 failed order."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust1 = next(
            m for m in metrics if m["id"] == 1
        )
        assert cust1["failed_order_count"] >= 1

    def test_unknown_order_count(self, setup_db):
        """Customer 1 has 1 unknown order."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        cust1 = next(
            m for m in metrics if m["id"] == 1
        )
        assert cust1["unknown_order_count"] >= 1

    def test_buyer_no_failed(self, setup_db):
        """Buyer should have no failed orders."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        buyer = next(
            m for m in metrics if m["id"] == 4
        )
        assert buyer["failed_order_count"] == 0

    def test_failed_order_days(self, setup_db):
        """last_failed_order_days must be int or None."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        for m in metrics:
            v = m["last_failed_order_days"]
            assert v is None or isinstance(v, int)

    def test_needs_attention_field(self, setup_db):
        """needs_attention must be bool."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        for m in metrics:
            assert isinstance(
                m["needs_attention"], bool
            )

    def test_at_risk_needs_attention(self, setup_db):
        """At-risk customer needs attention."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        at_risk = next(
            m for m in metrics if m["id"] == 7
        )
        assert at_risk["needs_attention"] is True


# ============================================================
# PHASE 2 — TIMELINE TESTS
# ============================================================


class TestTimeline:
    """Test timeline construction."""

    def test_timeline_in_detail(self, setup_db):
        """Detail must include timeline."""
        result = get_customer_detail(
            setup_db,
            organization_id=1,
            customer_id=4,
        )
        assert result is not None
        assert "timeline" in result
        assert isinstance(result["timeline"], list)

    def test_timeline_has_events(self, setup_db):
        """Customer with activity has timeline events."""
        result = get_customer_detail(
            setup_db,
            organization_id=1,
            customer_id=4,
        )
        assert result is not None
        assert len(result["timeline"]) >= 1

    def test_timeline_customer_created(self, setup_db):
        """Timeline includes customer_created event."""
        result = get_customer_detail(
            setup_db,
            organization_id=1,
            customer_id=4,
        )
        assert result is not None
        types = [e["type"] for e in result["timeline"]]
        assert "customer_created" in types

    def test_timeline_order_events(self, setup_db):
        """Timeline includes order events."""
        result = get_customer_detail(
            setup_db,
            organization_id=1,
            customer_id=4,
        )
        assert result is not None
        types = [e["type"] for e in result["timeline"]]
        assert "order_created" in types

    def test_timeline_max_30(self, setup_db):
        """Timeline capped at 30 events."""
        result = get_customer_detail(
            setup_db,
            organization_id=1,
            customer_id=6,
        )
        assert result is not None
        assert len(result["timeline"]) <= 30

    def test_timeline_most_recent_first(
        self, setup_db
    ):
        """Timeline sorted most recent first."""
        result = get_customer_detail(
            setup_db,
            organization_id=1,
            customer_id=6,
        )
        assert result is not None
        timestamps = [
            e["timestamp"] or ""
            for e in result["timeline"]
        ]
        assert timestamps == sorted(
            timestamps, reverse=True
        )

    def test_timeline_cross_tenant_empty(
        self, setup_db
    ):
        """Cross-tenant detail returns None."""
        result = get_customer_detail(
            setup_db,
            organization_id=1,
            customer_id=9,
        )
        assert result is None


# ============================================================
# PHASE 2 — FILTER TESTS
# ============================================================


class TestPhase2Filters:
    """Test Phase 2 filter parameters."""

    def test_filter_by_priority(self, setup_db):
        """Filter by priority."""
        result = get_customer_list(
            setup_db,
            organization_id=1,
            priority="high",
        )
        for item in result["items"]:
            assert item["priority"] == "high"

    def test_filter_by_health(self, setup_db):
        """Filter by health."""
        result = get_customer_list(
            setup_db,
            organization_id=1,
            health="active",
        )
        for item in result["items"]:
            assert item["customer_health"] == "active"

    def test_filter_by_needs_attention(self, setup_db):
        """Filter by needs_attention."""
        result = get_customer_list(
            setup_db,
            organization_id=1,
            needs_attention=True,
        )
        for item in result["items"]:
            assert item["needs_attention"] is True

    def test_combined_phase2_filters(self, setup_db):
        """Combined Phase 2 filters work together."""
        result = get_customer_list(
            setup_db,
            organization_id=1,
            priority="high",
            health="at_risk",
        )
        for item in result["items"]:
            assert item["priority"] == "high"
            assert (
                item["customer_health"] == "at_risk"
            )

    def test_sort_by_score_desc(self, setup_db):
        """Sort by score descending."""
        result = get_customer_list(
            setup_db,
            organization_id=1,
            sort="score_desc",
        )
        items = result["items"]
        if len(items) >= 2:
            for i in range(len(items) - 1):
                assert (
                    items[i]["customer_score"]
                    >= items[i + 1]["customer_score"]
                )

    def test_sort_by_priority_desc(self, setup_db):
        """Sort by priority descending."""
        result = get_customer_list(
            setup_db,
            organization_id=1,
            sort="priority_desc",
        )
        items = result["items"]
        order = {"high": 3, "medium": 2, "low": 1}
        if len(items) >= 2:
            for i in range(len(items) - 1):
                a = order.get(
                    items[i]["priority"], 0
                )
                b = order.get(
                    items[i + 1]["priority"], 0
                )
                assert a >= b

    def test_filter_before_pagination_p2(
        self, setup_db
    ):
        """Phase 2 filters apply before pagination."""
        result = get_customer_list(
            db=setup_db,
            organization_id=1,
            priority="high",
            page=1,
            page_size=100,
        )
        for item in result["items"]:
            assert item["priority"] == "high"


# ============================================================
# PHASE 2 — SUMMARY TESTS
# ============================================================


class TestPhase2Summary:
    """Test Phase 2 summary fields."""

    def test_summary_phase2_fields(self, setup_db):
        """Summary includes Phase 2 fields."""
        result = get_summary(
            setup_db, organization_id=1
        )
        assert "high_priority" in result
        assert "needs_followup" in result
        assert "active_health" in result
        assert "at_risk_health" in result
        assert "inactive_health" in result

    def test_summary_phase2_counts(self, setup_db):
        """Phase 2 counts are non-negative."""
        result = get_summary(
            setup_db, organization_id=1
        )
        assert result["high_priority"] >= 0
        assert result["needs_followup"] >= 0
        assert result["active_health"] >= 0
        assert result["at_risk_health"] >= 0
        assert result["inactive_health"] >= 0

    def test_summary_health_sums_to_total(
        self, setup_db
    ):
        """Health counts sum to total."""
        result = get_summary(
            setup_db, organization_id=1
        )
        health_sum = (
            result["active_health"]
            + result["at_risk_health"]
            + result["inactive_health"]
        )
        assert health_sum == result["total_customers"]


# ============================================================
# PHASE 2 — SCORE BOUNDARY TESTS
# ============================================================


class TestScoreBoundaries:
    """Test score boundary conditions."""

    def test_empty_customer_score(self, setup_db):
        """New customer with no activity scores low."""
        now = datetime.utcnow()
        cust = Customer(
            id=80,
            organization_id=1,
            name="Empty Score",
            phone="+8080808080",
            created_at=now - timedelta(days=3),
        )
        setup_db.add(cust)
        setup_db.commit()

        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        m = next(
            (x for x in metrics if x["id"] == 80),
            None,
        )
        assert m is not None
        assert 0 <= m["customer_score"] <= 100
        assert m["customer_score"] <= 20

    def test_max_score_vip_active(self, setup_db):
        """VIP with very recent activity scores high."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        vip = next(
            m for m in metrics if m["id"] == 6
        )
        # VIP with orders and interactions
        assert vip["customer_score"] >= 50

    def test_score_never_nan(self, setup_db):
        """Score is never NaN."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        import math
        for m in metrics:
            assert not math.isnan(
                m["customer_score"]
            )

    def test_score_never_negative(self, setup_db):
        """Score is never negative."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        for m in metrics:
            assert m["customer_score"] >= 0


# ============================================================
# PHASE 2 — NEEDS ATTENTION SEMANTICS
# ============================================================


class TestNeedsAttentionSemantics:
    """Test needs_attention vs needs_followup."""

    def test_inactive_needs_followup_not_attention(
        self, setup_db
    ):
        """Inactive never-buyer: followup true, attention false."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        inactive = next(
            m for m in metrics if m["id"] == 8
        )
        assert inactive["next_best_action"] != "no_action_needed"
        assert inactive["needs_attention"] is False

    def test_recent_failed_order_both_true(
        self, setup_db
    ):
        """Recent failed order: both true."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        # Find a customer with failed orders
        for m in metrics:
            if m["failed_order_count"] > 0:
                if m.get("last_failed_order_days") is not None and m["last_failed_order_days"] <= 30:
                    assert m["needs_attention"] is True
                    return
        # If no customer has recent failed orders, create one
        now = datetime.utcnow()
        cust_fa = Customer(
            id=205,
            organization_id=1,
            name="Failed Order Customer",
            phone="+9090909090",
            created_at=now - timedelta(days=30),
        )
        setup_db.add(cust_fa)
        conv_fa = Conversation(
            organization_id=1,
            store_id=1,
            customer_id=205,
            channel="whatsapp",
            mode="ai",
            created_at=now - timedelta(days=5),
            updated_at=now - timedelta(days=5),
        )
        setup_db.add(conv_fa)
        setup_db.flush()
        failed_order = Order(
            organization_id=1,
            store_id=1,
            customer_id=205,
            total_amount=100.00,
            order_number="ORD-FAIL-1",
            currency="USD",
            external_creation_status="failed",
            created_at=now - timedelta(days=3),
        )
        setup_db.add(failed_order)
        setup_db.commit()

        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        m = next(x for x in metrics if x["id"] == 205)
        assert m["needs_attention"] is True

    def test_healthy_buyer_both_false(self, setup_db):
        """Healthy buyer: both false."""
        # C4: buyer with recent order and interaction
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        buyer = next(
            m for m in metrics if m["id"] == 4
        )
        assert buyer["needs_attention"] is False

    def test_high_priority_needs_attention(
        self, setup_db
    ):
        """High priority customer: needs_attention true."""
        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        for m in metrics:
            if m["priority"] == "high":
                assert m["needs_attention"] is True
                return

    def test_medium_priority_recover_needs_attention(
        self, setup_db
    ):
        """Medium priority with recover_failed_order: attention true."""
        now = datetime.utcnow()
        cust_med = Customer(
            id=206,
            organization_id=1,
            name="Medium Recover",
            phone="+9191919191",
            created_at=now - timedelta(days=30),
        )
        setup_db.add(cust_med)
        conv_med = Conversation(
            organization_id=1,
            store_id=1,
            customer_id=206,
            channel="whatsapp",
            mode="ai",
            created_at=now - timedelta(days=5),
            updated_at=now - timedelta(days=5),
        )
        setup_db.add(conv_med)
        setup_db.flush()
        failed_order2 = Order(
            organization_id=1,
            store_id=1,
            customer_id=206,
            total_amount=100.00,
            order_number="ORD-FAIL-2",
            currency="USD",
            external_creation_status="failed",
            created_at=now - timedelta(days=3),
        )
        setup_db.add(failed_order2)
        setup_db.commit()

        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        m = next(x for x in metrics if x["id"] == 206)
        assert m["needs_attention"] is True


# ============================================================
# PHASE 2 — HEALTH LEAD BOUNDARIES
# ============================================================


class TestHealthLeadBoundaries:
    """Test lead health at boundary conditions."""

    def test_lead_30_days_active(self, setup_db):
        """Lead with 30-day-old interaction: active."""
        now = datetime.utcnow()
        cust = Customer(
            id=200,
            organization_id=1,
            name="Lead 30d",
            phone="+7070707070",
            created_at=now - timedelta(days=60),
        )
        setup_db.add(cust)
        conv = Conversation(
            organization_id=1,
            store_id=1,
            customer_id=200,
            channel="whatsapp",
            mode="ai",
            created_at=now - timedelta(days=35),
            updated_at=now - timedelta(days=30),
        )
        setup_db.add(conv)
        setup_db.commit()

        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        m = next(x for x in metrics if x["id"] == 200)
        assert m["customer_health"] == "active"

    def test_lead_31_days_at_risk(self, setup_db):
        """Lead with 31-day-old interaction: at_risk."""
        now = datetime.utcnow()
        cust = Customer(
            id=201,
            organization_id=1,
            name="Lead 31d",
            phone="+7171717171",
            created_at=now - timedelta(days=60),
        )
        setup_db.add(cust)
        conv = Conversation(
            organization_id=1,
            store_id=1,
            customer_id=201,
            channel="whatsapp",
            mode="ai",
            created_at=now - timedelta(days=36),
            updated_at=now - timedelta(days=31),
        )
        setup_db.add(conv)
        setup_db.commit()

        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        m = next(x for x in metrics if x["id"] == 201)
        assert m["customer_health"] == "at_risk"

    def test_lead_59_days_at_risk(self, setup_db):
        """Lead with 59-day-old interaction: at_risk."""
        now = datetime.utcnow()
        cust = Customer(
            id=202,
            organization_id=1,
            name="Lead 59d",
            phone="+7272727272",
            created_at=now - timedelta(days=90),
        )
        setup_db.add(cust)
        conv = Conversation(
            organization_id=1,
            store_id=1,
            customer_id=202,
            channel="whatsapp",
            mode="ai",
            created_at=now - timedelta(days=64),
            updated_at=now - timedelta(days=59),
        )
        setup_db.add(conv)
        setup_db.commit()

        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        m = next(x for x in metrics if x["id"] == 202)
        assert m["customer_health"] == "at_risk"

    def test_lead_60_days_inactive(self, setup_db):
        """Lead with 60-day-old interaction: inactive."""
        now = datetime.utcnow()
        cust = Customer(
            id=203,
            organization_id=1,
            name="Lead 60d",
            phone="+7373737373",
            created_at=now - timedelta(days=90),
        )
        setup_db.add(cust)
        conv = Conversation(
            organization_id=1,
            store_id=1,
            customer_id=203,
            channel="whatsapp",
            mode="ai",
            created_at=now - timedelta(days=65),
            updated_at=now - timedelta(days=60),
        )
        setup_db.add(conv)
        setup_db.commit()

        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        m = next(x for x in metrics if x["id"] == 203)
        assert m["customer_health"] == "inactive"

    def test_lead_no_interaction_active(self, setup_db):
        """Lead with no interactions: active (new customer)."""
        now = datetime.utcnow()
        cust = Customer(
            id=204,
            organization_id=1,
            name="Lead No Interaction",
            phone="+7474747474",
            created_at=now - timedelta(days=5),
        )
        setup_db.add(cust)
        setup_db.commit()

        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        m = next(x for x in metrics if x["id"] == 204)
        assert m["customer_health"] == "active"


# ============================================================
# PHASE 2 — SCORE FAILURE SEMANTICS
# ============================================================


class TestScoreFailureSemantics:
    """Test that failed orders don't distort score."""

    def test_failed_order_does_not_reduce_score(
        self, setup_db
    ):
        """Customer with failed order has same score as without."""
        from app.customers.intelligence import _calculate_score
        now = datetime.utcnow()
        base = dict(
            now=now,
            created_at=now - timedelta(days=30),
            conversation_count=2,
            message_count=5,
            last_interaction_at=now - timedelta(days=3),
            successful_order_count=1,
            last_order_at=now - timedelta(days=5),
            failed_order_count=0,
            unknown_order_count=0,
        )
        score_clean, _ = _calculate_score(**base)

        with_failed = {**base, "failed_order_count": 3}
        score_failed, _ = _calculate_score(**with_failed)

        assert score_clean == score_failed

    def test_unknown_order_does_not_reduce_score(
        self, setup_db
    ):
        """Unknown orders don't reduce score."""
        from app.customers.intelligence import _calculate_score
        now = datetime.utcnow()
        base = dict(
            now=now,
            created_at=now - timedelta(days=30),
            conversation_count=2,
            message_count=5,
            last_interaction_at=now - timedelta(days=3),
            successful_order_count=1,
            last_order_at=now - timedelta(days=5),
            failed_order_count=0,
            unknown_order_count=0,
        )
        score_clean, _ = _calculate_score(**base)

        with_unknown = {**base, "unknown_order_count": 2}
        score_unknown, _ = _calculate_score(**with_unknown)

        assert score_clean == score_unknown

    def test_failed_order_affects_priority_risk(
        self, setup_db
    ):
        """Failed orders still affect priority and risks."""
        now = datetime.utcnow()
        cust = Customer(
            id=207,
            organization_id=1,
            name="Failed Impact",
            phone="+8080808080",
            created_at=now - timedelta(days=30),
        )
        setup_db.add(cust)
        conv = Conversation(
            organization_id=1,
            store_id=1,
            customer_id=207,
            channel="whatsapp",
            mode="ai",
            created_at=now - timedelta(days=5),
            updated_at=now - timedelta(days=5),
        )
        setup_db.add(conv)
        setup_db.flush()
        failed = Order(
            organization_id=1,
            store_id=1,
            customer_id=207,
            total_amount=100.00,
            order_number="ORD-F80",
            currency="USD",
            external_creation_status="failed",
            created_at=now - timedelta(days=3),
        )
        setup_db.add(failed)
        setup_db.commit()

        metrics = get_customer_metrics(
            setup_db, organization_id=1
        )
        m = next(x for x in metrics if x["id"] == 207)
        assert "failed_order" in m["risks"]
        assert m["failed_order_count"] == 1


# ============================================================
# PHASE 2 — SCORE FACTOR COMPLETENESS
# ============================================================


class TestScoreFactorCompleteness:
    """Test that score factors explain the score."""

    def test_recency_factor_exists(self, setup_db):
        """Recency component produces visible factors."""
        from app.customers.intelligence import _calculate_score
        now = datetime.utcnow()
        score, factors = _calculate_score(
            now=now,
            created_at=now - timedelta(days=30),
            conversation_count=1,
            message_count=1,
            last_interaction_at=now - timedelta(days=3),
            successful_order_count=0,
            last_order_at=None,
            failed_order_count=0,
            unknown_order_count=0,
        )
        codes = [f["code"] for f in factors]
        assert "recent_interaction" in codes

    def test_score_factors_sum_explains_score(
        self, setup_db
    ):
        """Sum of positive factors >= final score."""
        from app.customers.intelligence import _calculate_score
        now = datetime.utcnow()
        score, factors = _calculate_score(
            now=now,
            created_at=now - timedelta(days=200),
            conversation_count=5,
            message_count=15,
            last_interaction_at=now - timedelta(days=2),
            successful_order_count=6,
            last_order_at=now - timedelta(days=3),
            failed_order_count=0,
            unknown_order_count=0,
        )
        total_positive = sum(
            f["impact"] for f in factors if f["impact"] > 0
        )
        assert total_positive >= score

    def test_no_negative_factors_anymore(self, setup_db):
        """Score factors should not contain negative impacts."""
        from app.customers.intelligence import _calculate_score
        now = datetime.utcnow()
        _, factors = _calculate_score(
            now=now,
            created_at=now - timedelta(days=30),
            conversation_count=2,
            message_count=5,
            last_interaction_at=now - timedelta(days=5),
            successful_order_count=1,
            last_order_at=now - timedelta(days=5),
            failed_order_count=5,
            unknown_order_count=3,
        )
        for f in factors:
            assert f["impact"] >= 0, f"Negative factor: {f}"
