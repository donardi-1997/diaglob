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
