from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.automation_flow_events import dispatch_flow_event
from app.automation_flow_graph import TRIGGER_TYPES, validate_graph
from app.automation_flow_templates import FLOW_TEMPLATES
from app.db import Base
from app.models import (
    AutomationFlow,
    AutomationFlowVersion,
    Customer,
    CustomerStoreProfile,
    Organization,
    Store,
    User,
)


def test_all_v08_templates_are_valid_and_unique():
    ids = [item["id"] for item in FLOW_TEMPLATES]
    assert len(ids) == len(set(ids))

    for template in FLOW_TEMPLATES:
        assert validate_graph(template["graph"]) == []
        trigger = next(
            node
            for node in template["graph"]["nodes"]
            if node["type"] == "trigger"
        )
        assert trigger["config"]["trigger_type"] in TRIGGER_TYPES


def test_domain_event_materializes_matching_active_flow_once():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()

    try:
        org = Organization(
            name="Flow Events",
            slug="flow-events",
            plan="growth",
            subscription_status="active",
            active=True,
        )
        session.add(org)
        session.flush()
        store = Store(
            organization_id=org.id,
            name="CO",
            slug="flow-events-co",
            country_code="CO",
            currency="COP",
            timezone="America/Bogota",
            default_language="es",
            active=True,
            deleted=False,
        )
        session.add(store)
        user = User(
            email="flow-events@example.com",
            name="Flow Events",
            external_auth_id="flow-events-user",
            active=True,
        )
        session.add(user)
        customer = Customer(
            organization_id=org.id,
            name="Cliente",
            phone="+573000000001",
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
                total_spent=100000,
            )
        )

        template = next(
            item
            for item in FLOW_TEMPLATES
            if item["id"] == "delivery_exception_followup"
        )
        flow = AutomationFlow(
            organization_id=org.id,
            store_id=store.id,
            name=template["name"],
            description=template["description"],
            status="active",
            created_by=user.id,
        )
        session.add(flow)
        session.flush()
        version = AutomationFlowVersion(
            flow_id=flow.id,
            organization_id=org.id,
            version_number=1,
            graph=template["graph"],
        )
        session.add(version)
        session.flush()
        flow.current_version_id = version.id
        flow.active_version_id = version.id
        session.commit()

        first = dispatch_flow_event(
            session,
            organization_id=org.id,
            store_id=store.id,
            event_type="shipment.delivery_exception",
            payload={"customer_id": customer.id},
            event_id="shipment:1:exception",
        )
        second = dispatch_flow_event(
            session,
            organization_id=org.id,
            store_id=store.id,
            event_type="shipment.delivery_exception",
            payload={"customer_id": customer.id},
            event_id="shipment:1:exception",
        )

        assert len(first) == 1
        assert second == []
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
