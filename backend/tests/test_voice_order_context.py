"""Order-context and COD voice fulfillment tests."""
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.automation_flow_engine import (
    _enqueue_confirmed_trigger_order,
    claim_flow_recipients,
    complete_voice_call,
    materialize_flow_trigger,
    process_flow_recipient,
    utcnow,
)
from app.automation_flow_events import dispatch_flow_event
from app.db import Base
from app.model_domains.fulfillment_automation import AutoFulfillmentJob
from app.model_domains.supplier_integrations import SupplierConnection
from app.models import (
    AutomationFlow,
    AutomationFlowRecipientExecution,
    AutomationFlowRun,
    AutomationFlowVersion,
    Customer,
    CustomerStoreProfile,
    Order,
    OrderItem,
    Organization,
    OrganizationMembership,
    Store,
    User,
)


def _setup():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()

    org = Organization(
        name="Voice Order Context",
        slug="voice-order-context",
        plan="growth",
        subscription_status="active",
        active=True,
    )
    session.add(org)
    session.flush()

    user = User(
        email="voice-flow@example.com",
        name="Voice Flow",
        active=True,
    )
    session.add(user)
    session.flush()
    membership = OrganizationMembership(
        user_id=user.id,
        organization_id=org.id,
        role="manager",
        all_stores=True,
        active=True,
    )
    session.add(membership)

    store = Store(
        organization_id=org.id,
        name="Tienda Medellín",
        slug="voice-order-context-store",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
        active=True,
        deleted=False,
    )
    session.add(store)
    session.flush()

    customer = Customer(
        organization_id=org.id,
        name="Ana Pérez",
        phone="+573001112233",
        email="ana@example.com",
        country_code="CO",
    )
    session.add(customer)
    session.flush()
    session.add(
        CustomerStoreProfile(
            organization_id=org.id,
            customer_id=customer.id,
            store_id=store.id,
            currency="COP",
            orders_count=1,
            total_spent=189900,
        )
    )

    order = Order(
        organization_id=org.id,
        store_id=store.id,
        customer_id=customer.id,
        shopify_order_id="90001",
        external_order_id="90001",
        order_number="1048",
        total_amount=189900,
        currency="COP",
        financial_status="pending",
        payment_status="pending",
        payment_method="Cash on Delivery (COD)",
        fulfillment_status="unfulfilled",
        lifecycle_status="open",
        source="shopify",
        shipping_address={
            "customer_name": "Ana Pérez",
            "country_code": "CO",
            "country": "Colombia",
            "province": "Antioquia",
            "city": "Medellín",
            "address1": "Calle 10 #20-30",
            "zip": "050001",
        },
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(order)
    session.flush()
    session.add(
        OrderItem(
            order_id=order.id,
            organization_id=org.id,
            store_id=store.id,
            title="Combo prueba",
            sku="COMBO-1",
            quantity=2,
            unit_price=94950,
            currency="COP",
        )
    )
    session.add(
        SupplierConnection(
            organization_id=org.id,
            store_id=store.id,
            provider="cj",
            status="connected",
            connected_at=datetime.utcnow(),
            auto_fulfillment_enabled=True,
            auto_origin_country_code="CN",
            auto_notify_customer=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    session.commit()
    session.refresh(membership)
    return engine, session, org, user, membership, store, customer, order


def _order_call_graph():
    return {
        "nodes": [
            {
                "id": "trigger",
                "type": "trigger",
                "config": {"trigger_type": "order_created"},
            },
            {
                "id": "call",
                "type": "call",
                "config": {
                    "call_prompt": (
                        "Hola {{customer.name}}, confirma el pedido "
                        "#{{order.number}} por {{order.total}} "
                        "{{order.currency}} para {{order.shipping.city}}."
                    ),
                    "call_language": "es",
                    "call_purpose": "order_confirmation",
                    "timeout_minutes": 5,
                },
            },
            {"id": "confirmed", "type": "end", "config": {}},
            {"id": "rejected", "type": "end", "config": {}},
            {"id": "no_answer", "type": "end", "config": {}},
            {"id": "failed", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "trigger", "target": "call"},
            {"source": "call", "target": "confirmed", "label": "confirmed"},
            {"source": "call", "target": "rejected", "label": "rejected"},
            {"source": "call", "target": "no_answer", "label": "no_answer"},
            {"source": "call", "target": "failed", "label": "failed"},
        ],
    }


def _activate_flow(session, org, user, store, graph, name):
    flow = AutomationFlow(
        organization_id=org.id,
        store_id=store.id,
        name=name,
        status="active",
        created_by=user.id,
    )
    session.add(flow)
    session.flush()
    version = AutomationFlowVersion(
        flow_id=flow.id,
        organization_id=org.id,
        version_number=1,
        graph=graph,
        published_at=utcnow(),
        activated_at=utcnow(),
    )
    session.add(version)
    session.flush()
    flow.current_version_id = version.id
    flow.active_version_id = version.id
    session.commit()
    return flow


def test_order_event_freezes_canonical_trigger_context():
    engine, session, org, user, _membership, store, customer, order = _setup()
    try:
        graph = {
            "nodes": [
                {
                    "id": "trigger",
                    "type": "trigger",
                    "config": {"trigger_type": "order_created"},
                },
                {"id": "end", "type": "end", "config": {}},
            ],
            "edges": [{"source": "trigger", "target": "end"}],
        }
        flow = _activate_flow(
            session,
            org,
            user,
            store,
            graph,
            "Freeze order context",
        )

        run_ids = dispatch_flow_event(
            session,
            organization_id=org.id,
            store_id=store.id,
            event_type="order.created",
            payload={"order": {"id": order.id}, "customer_id": customer.id},
            event_id="shopify:order:90001:created",
        )
        assert len(run_ids) == 1

        run = session.get(AutomationFlowRun, run_ids[0])
        context = run.trigger_context
        assert context["event"]["type"] == "order.created"
        assert context["order"]["number"] == "1048"
        assert context["order"]["total"] == 189900.0
        assert context["order"]["currency"] == "COP"
        assert context["order"]["is_cod"] is True
        assert context["order"]["country"] == "CO"
        assert context["order"]["shipping"]["city"] == "Medellín"
        assert context["order"]["items_summary"] == "2x Combo prueba"

        order.total_amount = 999999
        order.shipping_address = {**order.shipping_address, "city": "Bogotá"}
        session.commit()
        session.refresh(run)

        assert run.trigger_context["order"]["total"] == 189900.0
        assert run.trigger_context["order"]["shipping"]["city"] == "Medellín"
        assert flow.active_version_id is not None
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_order_confirmation_call_uses_snapshot_and_updates_order():
    engine, session, org, user, _membership, store, customer, order = _setup()
    try:
        flow = _activate_flow(
            session,
            org,
            user,
            store,
            _order_call_graph(),
            "Voice order confirmation",
        )
        trigger_context = {
            "event": {"type": "order.created", "id": "evt-1"},
            "order": {
                "id": order.id,
                "number": "1048",
                "total": 189900.0,
                "currency": "COP",
                "is_cod": True,
                "shipping": {"city": "Medellín"},
            },
        }
        materialize_flow_trigger(
            session,
            flow,
            [customer.id],
            trigger_context=trigger_context,
        )
        recipient_id, claim_token = claim_flow_recipients(
            session,
            include_tokens=True,
        )[0]

        calls = []

        def fake_voice_sender(**payload):
            calls.append(payload)
            return {"call_id": "order-call-1", "status": "queued"}

        assert process_flow_recipient(
            session,
            recipient_id,
            claim_token=claim_token,
            voice_sender=fake_voice_sender,
        ) == "waiting"

        prompt = calls[0]["prompt"]
        assert "Ana Pérez" in prompt
        assert "#1048" in prompt
        assert "189900.0 COP" in prompt
        assert "Medellín" in prompt
        assert calls[0]["metadata"]["order_id"] == order.id

        result = complete_voice_call(
            session,
            call_id="order-call-1",
            outcome="confirmed",
            transcript="Sí, lo recibo.",
            provider_status="completed",
        )
        assert result["status"] == "processed"

        session.refresh(order)
        assert order.confirmation_status == "confirmed"
        assert order.confirmation_source == "voice_ai"
        assert order.confirmed_at is not None

        run = session.query(AutomationFlowRun).filter(
            AutomationFlowRun.flow_id == flow.id,
        ).one()
        assert run.trigger_context["order"]["confirmation_status"] == "confirmed"

        recipient = session.get(AutomationFlowRecipientExecution, recipient_id)
        assert recipient.current_node_id == "confirmed"
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_confirmed_trigger_order_is_the_only_order_queued_for_fulfillment():
    engine, session, org, _user, membership, store, customer, order = _setup()
    try:
        order.confirmation_status = "confirmed"
        order.confirmation_source = "voice_ai"
        order.confirmed_at = utcnow()

        other = Order(
            organization_id=org.id,
            store_id=store.id,
            customer_id=customer.id,
            shopify_order_id="90002",
            external_order_id="90002",
            order_number="1049",
            total_amount=250000,
            currency="COP",
            financial_status="pending",
            payment_status="pending",
            payment_method="Cash on Delivery",
            fulfillment_status="unfulfilled",
            lifecycle_status="open",
            confirmation_status="confirmed",
            confirmation_source="voice_ai",
            confirmed_at=utcnow(),
            source="shopify",
            shipping_address={"country_code": "CO"},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(other)
        session.flush()

        run = AutomationFlowRun(
            flow_id=1,
            flow_version_id=1,
            organization_id=org.id,
            store_id=store.id,
            status="running",
            total_recipients=1,
            trigger_context={
                "event": {"type": "order.created", "id": "evt-1"},
                "order": {"id": order.id, "number": order.order_number},
            },
            started_at=utcnow(),
        )
        # The helper only relies on tenant/store/context and does not dereference
        # flow/version foreign keys before the job is queued.
        result = _enqueue_confirmed_trigger_order(
            session,
            membership,
            run,
        )
        assert result["status"] == "success"

        jobs = session.query(AutoFulfillmentJob).all()
        assert len(jobs) == 1
        assert jobs[0].order_id == order.id
        assert jobs[0].order_id != other.id
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
