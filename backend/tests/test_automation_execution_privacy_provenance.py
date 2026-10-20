"""Only future events get provenance; no historic reconstruction from PII."""
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.automations import execute_automation, run_automations_for_event
from app.db import Base
from app.models import (
    Automation, AutomationExecution, AutomationExecutionProvenance,
    Customer, CustomerStoreProfile, Organization, Store,
)
from app.services.automation_execution_provenance import AutomationProvenanceError


@pytest.fixture
def sandbox():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        org = Organization(name="Synthetic tenant", slug="synthetic-provenance", plan="starter")
        foreign_org = Organization(name="Foreign tenant", slug="foreign-provenance", plan="starter")
        db.add_all([org, foreign_org])
        db.flush()
        stores = []
        for name, tenant in (("one", org), ("two", org), ("other", foreign_org)):
            store = Store(
                organization_id=tenant.id, name=name, slug=f"provenance-{name}",
                country_code="CO", currency="COP", timezone="UTC",
            )
            db.add(store)
            stores.append(store)
        db.flush()
        customer = Customer(
            organization_id=org.id, name="PRIVATE_SYNTHETIC_BUYER", phone="555-PRIVATE",
        )
        foreign = Customer(organization_id=foreign_org.id, name="FOREIGN_PRIVATE", phone="777")
        db.add_all([customer, foreign])
        db.flush()
        for store in stores[:2]:
            db.add(CustomerStoreProfile(
                organization_id=org.id, store_id=store.id, customer_id=customer.id,
                external_customer_id=f"700-{store.id}", currency="COP",
            ))
        db.flush()
        scoped = Automation(
            organization_id=org.id, store_id=stores[0].id,
            name="Store specific", trigger_type="order.created",
            conditions_json="[]", actions_json="[]",
        )
        global_automation = Automation(
            organization_id=org.id, store_id=None,
            name="Global", trigger_type="order.created",
            conditions_json="[]", actions_json="[]",
        )
        db.add_all([scoped, global_automation])
        db.commit()
        yield db, org, foreign_org, stores, customer, foreign, scoped, global_automation
    engine.dispose()


def _rows(db):
    return db.query(AutomationExecutionProvenance).order_by(
        AutomationExecutionProvenance.id,
    ).all()


def test_explicit_store_and_customer_link_persist_atomically(sandbox):
    db, org, _, stores, customer, _, scoped, _ = sandbox
    payload = {"private_contact": "PRIVATE_SYNTHETIC_BUYER"}
    result = execute_automation(
        db, scoped, "order.created", payload,
        event_store_id=stores[0].id, subject_customer_id=customer.id,
    )
    saved = _rows(db)
    assert len(saved) == 1
    row = saved[0]
    assert row.execution_id == result.id
    assert row.organization_id == org.id
    assert row.store_id == stores[0].id
    assert row.customer_id == customer.id
    assert row.source_context == "explicit_dispatch_store"
    assert row.subject_linkage == "local_profile_shopify_unverified"
    assert result.store_id == stores[0].id
    assert "PRIVATE_SYNTHETIC_BUYER" in result.input_json
    assert "PRIVATE_SYNTHETIC_BUYER" not in repr(row)
    assert "PRIVATE_SYNTHETIC_BUYER" not in json.dumps({
        "subject_linkage": row.subject_linkage,
        "source_context": row.source_context,
    })


def test_new_event_without_explicit_subject_does_not_guess_from_payload(sandbox):
    db, _, _, stores, customer, _, scoped, _ = sandbox
    result = execute_automation(
        db, scoped, "order.created",
        {"email": "PRIVATE_EMAIL", "customer_id": customer.id},
    )
    row = _rows(db)[0]
    assert result.id == row.execution_id
    assert row.customer_id is None
    assert row.store_id == stores[0].id
    assert row.source_context == "automation_store"
    assert row.subject_linkage == "subject_not_asserted"


def test_org_wide_automation_records_trusted_event_store_not_parent_null(sandbox):
    db, _, _, stores, customer, _, _, global_automation = sandbox
    result = execute_automation(
        db, global_automation, "order.created", {"message": "PRIVATE_DATA"},
        event_store_id=stores[1].id, subject_customer_id=customer.id,
    )
    row = _rows(db)[0]
    assert result.store_id == stores[1].id
    assert row.store_id == stores[1].id
    assert row.customer_id == customer.id
    assert row.source_context == "explicit_dispatch_store"


def test_unknown_organization_event_never_implicitly_claims_store(sandbox):
    db, _, _, _, _, _, _, global_automation = sandbox
    result = execute_automation(
        db, global_automation, "order.created", {"contact": "PRIVATE"},
    )
    row = _rows(db)[0]
    assert result.store_id is None
    assert row.store_id is None
    assert row.customer_id is None
    assert row.subject_linkage == "store_and_subject_not_asserted"


def test_scope_mismatch_and_cross_tenant_subject_fail_before_creating_execution(sandbox):
    db, _, _, stores, customer, foreign, scoped, global_automation = sandbox
    for options, code in (
        ({"event_store_id": stores[1].id}, "AUTOMATION_EVENT_STORE_MISMATCH"),
        ({"event_store_id": stores[2].id}, "AUTOMATION_EVENT_STORE_MISMATCH"),
        ({"subject_customer_id": foreign.id}, "CUSTOMER_STORE_LINK_UNVERIFIED"),
        ({"subject_customer_id": customer.id, "event_store_id": stores[2].id},
         "AUTOMATION_EVENT_STORE_MISMATCH"),
        ({"event_store_id": stores[2].id}, "UNVERIFIED_AUTOMATION_STORE"),
    ):
        automation = global_automation if code == "UNVERIFIED_AUTOMATION_STORE" else scoped
        with pytest.raises(AutomationProvenanceError, match=code):
            execute_automation(
                db, automation, "order.created", {"secret": "PRIVATE"}, **options,
            )
    assert db.query(AutomationExecution.id).count() == 0
    assert not _rows(db)


def test_dispatch_scopes_org_wide_and_store_automations_to_the_same_event_shop(sandbox):
    db, org, _, stores, customer, _, _, _ = sandbox
    results = run_automations_for_event(
        db, organization_id=org.id, store_id=stores[0].id,
        event_type="order.created", payload={"private": "PRIVATE_TEXT"},
        subject_customer_id=customer.id,
    )
    assert len(results) == 2
    assert len(_rows(db)) == 2
    assert all(row.store_id == stores[0].id for row in _rows(db))
    assert all(row.customer_id == customer.id for row in _rows(db))
    assert all(
        row.subject_linkage == "local_profile_shopify_unverified"
        for row in _rows(db)
    )


def test_historical_execution_without_origin_is_not_backfilled(sandbox):
    db, org, _, stores, _, _, scoped, _ = sandbox
    db.add(AutomationExecution(
        automation_id=scoped.id, organization_id=org.id,
        store_id=stores[0].id, event_type="order.created",
        input_json='{"PRIVATE_PII": "NOT_ATTRIBUTABLE"}',
        result_json="{}", status="success",
    ))
    db.commit()
    assert db.query(AutomationExecution).count() == 1
    assert db.query(AutomationExecutionProvenance).count() == 0
