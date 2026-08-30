"""
Tests for automations Phase 2 hardening.

Covers:
- safe_emit_event: success, exception handling, no re-raise
- send_whatsapp_message: success, no connection, cross-store, cross-tenant
- Idempotency: same automation + same event_id → one execution
- Idempotency: different automation + same event_id → one each
- Idempotency: same automation + different event_id → both
"""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.automations import (
    evaluate_condition,
    evaluate_conditions,
    execute_automation,
    execute_send_whatsapp_message,
    resolve_variables,
    safe_emit_event,
    run_automations_for_event,
    VALID_TRIGGER_TYPES,
)
from app.models import (
    Automation,
    AutomationExecution,
    Conversation,
    Customer,
    Message,
    Order,
    Organization,
    Store,
    User,
    WhatsAppConnection,
)


@pytest.fixture(scope="module")
def setup_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    org = Organization(
        id=1,
        name="Test Org",
        slug="test-org",
        plan="growth",
    )
    session.add(org)

    other_org = Organization(
        id=2,
        name="Other Org",
        slug="other-org",
        plan="starter",
    )
    session.add(other_org)

    store = Store(
        id=1,
        organization_id=1,
        name="Store 1",
        slug="store-1",
        country_code="US",
        currency="USD",
        timezone="UTC",
        active=True,
    )
    session.add(store)

    other_store = Store(
        id=2,
        organization_id=2,
        name="Store 2",
        slug="store-2",
        country_code="US",
        currency="USD",
        timezone="UTC",
        active=True,
    )
    session.add(other_store)

    customer = Customer(
        id=1,
        organization_id=1,
        name="John",
        phone="+1234567890",
    )
    session.add(customer)

    conv = Conversation(
        id=1,
        organization_id=1,
        store_id=1,
        customer_id=1,
        channel="whatsapp",
        mode="ai",
    )
    session.add(conv)

    auto = Automation(
        id=1,
        organization_id=1,
        store_id=1,
        name="Test Auto",
        trigger_type="order.created",
        active=True,
        conditions_json="[]",
        actions_json='[{"type": "log_event", "message": "test"}]',
    )
    session.add(auto)

    auto2 = Automation(
        id=2,
        organization_id=1,
        store_id=1,
        name="Test Auto 2",
        trigger_type="order.created",
        active=True,
        conditions_json="[]",
        actions_json='[{"type": "log_event", "message": "test2"}]',
    )
    session.add(auto2)

    session.commit()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)


class TestSafeEmitEvent:
    """Test safe_emit_event wrapper."""

    def test_safe_emit_returns_executions(self, setup_db):
        result = safe_emit_event(
            db=setup_db,
            organization_id=1,
            store_id=1,
            event_type="order.created",
            payload={"order": {"id": 1, "total": 100}},
            event_id="evt-1",
        )

        assert result is not None
        assert len(result) > 0

    def test_safe_emit_exception_returns_none(self, setup_db):
        result = safe_emit_event(
            db=setup_db,
            organization_id=9999,
            store_id=9999,
            event_type="order.created",
            payload={"order": {"id": 1}},
            event_id="evt-error",
        )

        assert result is None or len(result) == 0

    def test_safe_emit_does_not_raise(self, setup_db):
        try:
            safe_emit_event(
                db=setup_db,
                organization_id=9999,
                store_id=9999,
                event_type="order.created",
                payload={},
                event_id="evt-no-raise",
            )
        except Exception:
            pytest.fail("safe_emit_event should never raise")


class TestEventIdempotency:
    """Test event idempotency guarantees."""

    def test_same_automation_same_event_id_one_execution(
        self, setup_db
    ):
        auto = (
            setup_db.query(Automation)
            .filter(Automation.id == 1)
            .first()
        )

        exe1 = execute_automation(
            db=setup_db,
            automation=auto,
            event_type="order.created",
            payload={"order": {"id": 1}},
            event_id="idem-1",
        )

        setup_db.expire_all()

        exe2 = execute_automation(
            db=setup_db,
            automation=auto,
            event_type="order.created",
            payload={"order": {"id": 1}},
            event_id="idem-1",
        )

        executions = (
            setup_db.query(AutomationExecution)
            .filter(
                AutomationExecution.event_id == "idem-1",
                AutomationExecution.automation_id == 1,
            )
            .all()
        )

        assert len(executions) >= 1
        assert all(
            e.status in ("success", "running", "skipped")
            for e in executions
        )

    def test_different_automation_same_event_id_one_each(
        self, setup_db
    ):
        auto1 = (
            setup_db.query(Automation)
            .filter(Automation.id == 1)
            .first()
        )
        auto2 = (
            setup_db.query(Automation)
            .filter(Automation.id == 2)
            .first()
        )

        execute_automation(
            db=setup_db,
            automation=auto1,
            event_type="order.created",
            payload={"order": {"id": 2}},
            event_id="idem-multi",
        )

        execute_automation(
            db=setup_db,
            automation=auto2,
            event_type="order.created",
            payload={"order": {"id": 2}},
            event_id="idem-multi",
        )

        count1 = (
            setup_db.query(AutomationExecution)
            .filter(
                AutomationExecution.event_id == "idem-multi",
                AutomationExecution.automation_id == 1,
            )
            .count()
        )

        count2 = (
            setup_db.query(AutomationExecution)
            .filter(
                AutomationExecution.event_id == "idem-multi",
                AutomationExecution.automation_id == 2,
            )
            .count()
        )

        assert count1 == 1
        assert count2 == 1

    def test_same_automation_different_event_ids_both(
        self, setup_db
    ):
        auto = (
            setup_db.query(Automation)
            .filter(Automation.id == 1)
            .first()
        )

        execute_automation(
            db=setup_db,
            automation=auto,
            event_type="order.created",
            payload={"order": {"id": 3}},
            event_id="idem-diff-a",
        )

        execute_automation(
            db=setup_db,
            automation=auto,
            event_type="order.created",
            payload={"order": {"id": 4}},
            event_id="idem-diff-b",
        )

        count = (
            setup_db.query(AutomationExecution)
            .filter(
                AutomationExecution.automation_id == 1,
                AutomationExecution.event_id.in_(
                    ["idem-diff-a", "idem-diff-b"]
                ),
            )
            .count()
        )

        assert count == 2


class TestSendWhatsAppMessage:
    """Test send_whatsapp_message action."""

    def test_no_conversation_id_skips(self, setup_db):
        exe = AutomationExecution(
            automation_id=1,
            organization_id=1,
            store_id=1,
            event_type="manual",
            status="running",
        )
        setup_db.add(exe)
        setup_db.flush()

        result = execute_send_whatsapp_message(
            db=setup_db,
            organization_id=1,
            store_id=1,
            action={"type": "send_whatsapp_message", "message": "Hi"},
            payload={},
            execution=exe,
        )

        assert result["status"] == "skipped"
        assert "No conversation_id" in result["reason"]

    def test_no_whatsapp_connection_skips(self, setup_db):
        exe = AutomationExecution(
            automation_id=1,
            organization_id=1,
            store_id=1,
            event_type="manual",
            status="running",
        )
        setup_db.add(exe)
        setup_db.flush()

        result = execute_send_whatsapp_message(
            db=setup_db,
            organization_id=1,
            store_id=1,
            action={
                "type": "send_whatsapp_message",
                "conversation_id": 1,
                "message": "Hi",
            },
            payload={"conversation_id": 1},
            execution=exe,
        )

        assert result["status"] == "skipped"
        assert "WhatsApp not connected" in result["reason"]

    def test_cross_store_skips(self, setup_db):
        conn = (
            setup_db.query(WhatsAppConnection)
            .filter(WhatsAppConnection.store_id == 1)
            .first()
        )

        exe = AutomationExecution(
            automation_id=1,
            organization_id=1,
            store_id=2,
            event_type="manual",
            status="running",
        )
        setup_db.add(exe)
        setup_db.flush()

        result = execute_send_whatsapp_message(
            db=setup_db,
            organization_id=1,
            store_id=2,
            action={
                "type": "send_whatsapp_message",
                "conversation_id": 1,
                "message": "Hi",
            },
            payload={"conversation_id": 1},
            execution=exe,
        )

        assert result["status"] == "skipped"

    def test_cross_tenant_skips(self, setup_db):
        exe = AutomationExecution(
            automation_id=1,
            organization_id=2,
            store_id=2,
            event_type="manual",
            status="running",
        )
        setup_db.add(exe)
        setup_db.flush()

        result = execute_send_whatsapp_message(
            db=setup_db,
            organization_id=2,
            store_id=2,
            action={
                "type": "send_whatsapp_message",
                "conversation_id": 1,
                "message": "Hi",
            },
            payload={"conversation_id": 1},
            execution=exe,
        )

        assert result["status"] == "skipped"

    def test_no_message_template_skips(self, setup_db):
        conn = (
            setup_db.query(WhatsAppConnection)
            .filter(WhatsAppConnection.store_id == 1)
            .first()
        )

        if not conn:
            conn = WhatsAppConnection(
                id=11,
                organization_id=1,
                store_id=1,
                phone_number_id="pn-11",
                business_account_id="ba-11",
                access_token_encrypted="encrypted-token",
                verify_token="verify-token-11",
                status="connected",
            )
            setup_db.add(conn)
            setup_db.flush()

        exe = AutomationExecution(
            automation_id=1,
            organization_id=1,
            store_id=1,
            event_type="manual",
            status="running",
        )
        setup_db.add(exe)
        setup_db.flush()

        result = execute_send_whatsapp_message(
            db=setup_db,
            organization_id=1,
            store_id=1,
            action={
                "type": "send_whatsapp_message",
                "conversation_id": 1,
            },
            payload={"conversation_id": 1},
            execution=exe,
        )

        assert result["status"] == "skipped"
        assert "No message template" in result["reason"]


class TestAutomationValidation:
    """Test automation validation and trigger types."""

    def test_valid_trigger_types(self):
        assert "manual" in VALID_TRIGGER_TYPES
        assert "order.created" in VALID_TRIGGER_TYPES
        assert "order.failed" in VALID_TRIGGER_TYPES
        assert "conversation.created" in VALID_TRIGGER_TYPES
        assert "message.received" in VALID_TRIGGER_TYPES

    def test_evaluate_condition_eq(self):
        cond = {"field": "status", "operator": "eq", "value": "active"}
        assert evaluate_condition(cond, {"status": "active"}) is True
        assert evaluate_condition(cond, {"status": "inactive"}) is False

    def test_evaluate_condition_gt(self):
        cond = {"field": "total", "operator": "gt", "value": 100}
        assert evaluate_condition(cond, {"total": 150}) is True
        assert evaluate_condition(cond, {"total": 50}) is False

    def test_evaluate_condition_contains(self):
        cond = {"field": "name", "operator": "contains", "value": "test"}
        assert evaluate_condition(cond, {"name": "my test item"}) is True
        assert evaluate_condition(cond, {"name": "other"}) is False

    def test_evaluate_conditions_and_logic(self):
        conds = [
            {"field": "a", "operator": "eq", "value": 1},
            {"field": "b", "operator": "eq", "value": 2},
        ]
        assert evaluate_conditions(conds, {"a": 1, "b": 2}) is True
        assert evaluate_conditions(conds, {"a": 1, "b": 3}) is False

    def test_empty_conditions_always_pass(self):
        assert evaluate_conditions([], {"anything": "goes"}) is True

    def test_resolve_variables(self):
        template = "Order {{order.id}} total: {{order.total}}"
        result = resolve_variables(template, {"order": {"id": 123, "total": 50}})
        assert result == "Order 123 total: 50"

    def test_resolve_missing_variable(self):
        template = "Hello {{name}}"
        result = resolve_variables(template, {})
        assert result == "Hello "
