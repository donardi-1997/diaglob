"""Synthetic legacy automation GDPR tests: never attribute subjects from JSON."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Automation, AutomationExecution, Customer, Organization, Store
from app.model_domains.automation_provenance import AutomationExecutionProvenance
from app.services.shopify_privacy_legacy_automation_redaction import (
    ShopifyLegacyAutomationPrivacyError, scrub_shopify_legacy_automations,
)


@pytest.fixture
def sandbox():
    engine = create_engine(
        "sqlite:///:memory:", poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        org = Organization(name="Synthetic Legacy GDPR", slug="legacy-gdpr")
        db.add(org)
        db.flush()
        stores = [
            Store(
                organization_id=org.id, name=f"Store {n}", slug=f"legacy-store-{n}",
                shopify_domain=f"legacy-{n}.myshopify.com",
                country_code="CO", currency="COP", timezone="UTC",
                active=True, deleted=False,
            ) for n in (1, 2)
        ]
        customers = [
            Customer(organization_id=org.id, name=f"SENSITIVE_BUYER_{n}", phone=f"555{n}")
            for n in (1, 2)
        ]
        db.add_all([*stores, *customers])
        db.flush()
        rules = [
            Automation(
                organization_id=org.id, store_id=stores[0].id, name="SENSITIVE_RULE_0",
                active=True, conditions_json='[{"contains":"SENSITIVE"}]',
                actions_json='[{"message":"SENSITIVE"}]',
                description="SENSITIVE_DESCRIPTION",
            ),
            Automation(
                organization_id=org.id, store_id=stores[1].id, name="SENSITIVE_RULE_1",
                active=True, conditions_json='[{"contains":"SENSITIVE_OTHER"}]',
                actions_json='[{"message":"SENSITIVE_OTHER"}]',
            ),
            Automation(
                organization_id=org.id, store_id=None, name="SHARED_ORG_RULE",
                active=True, conditions_json='[{"contains":"SHARED"}]',
                actions_json='[{"message":"SHARED"}]',
            ),
        ]
        db.add_all(rules)
        db.flush()

        def execution(rule, store, tag, customer=None):
            row = AutomationExecution(
                automation_id=rule.id, organization_id=org.id, store_id=store,
                event_type="order_created", event_id=f"SENSITIVE_EVENT_{tag}",
                status="running", input_json=f'{{"private":"SENSITIVE_{tag}"}}',
                result_json=f'{{"private":"SENSITIVE_RESULT_{tag}"}}',
                error_message=f"SENSITIVE_ERROR_{tag}",
            )
            db.add(row)
            db.flush()
            if customer is not None:
                db.add(AutomationExecutionProvenance(
                    execution_id=row.id, organization_id=org.id, store_id=store,
                    customer_id=customer.id, source_context="explicit_dispatch_store",
                    subject_linkage="local_profile_shopify_unverified",
                    provenance_version=1,
                ))
            return row

        execs = {
            "buyer": execution(rules[0], stores[0].id, "BUYER", customers[0]),
            "other_buyer": execution(rules[0], stores[0].id, "OTHER", customers[1]),
            "unknown": execution(rules[0], stores[0].id, "UNKNOWN"),
            "other_store": execution(rules[1], stores[1].id, "FOREIGN", customers[0]),
            "shared_rule": execution(rules[2], stores[0].id, "SHARED", customers[0]),
        }
        db.commit()
        yield db, org, stores, customers, rules, execs
    engine.dispose()


def run(sandbox, ids=None):
    db, org, stores, *_ = sandbox
    return scrub_shopify_legacy_automations(
        db, organization_id=org.id, store_id=stores[0].id,
        customer_ids=ids,
    )


def test_shop_redact_scrubs_all_store_specific_payloads_not_shared_or_other_store(sandbox):
    db, org, stores, customers, rules, rows = sandbox
    result = run(sandbox, None)
    db.commit()
    assert result["legacy_execution_payloads_scrubbed"] == 3
    assert result["legacy_rules_scrubbed"] == 1
    assert result["legacy_possible_inflight_actions"] == 3
    assert result["legacy_shared_parent_executions_for_review"] == 1
    assert result["fulfillment_complete"] is False
    db.refresh(rows["buyer"])
    assert rows["buyer"].input_json == "{}"
    assert rows["buyer"].result_json == "{}"
    assert rows["buyer"].error_message is None
    assert rows["buyer"].event_id is None
    assert rows["buyer"].status == "failed"
    db.refresh(rules[0])
    assert rules[0].active is False
    assert rules[0].conditions_json == "[]"
    assert rules[0].actions_json == "[]"
    assert "SENSITIVE" not in rules[0].name
    db.refresh(rows["other_store"])
    assert "SENSITIVE_FOREIGN" in rows["other_store"].input_json
    db.refresh(rows["shared_rule"])
    assert "SENSITIVE_SHARED" in rows["shared_rule"].input_json
    db.refresh(rules[1])
    assert rules[1].active is True
    db.refresh(rules[2])
    assert rules[2].active is True
    provenance = db.query(AutomationExecutionProvenance).filter_by(
        execution_id=rows["buyer"].id,
    ).one()
    assert provenance.customer_id is None
    assert provenance.subject_linkage == "subject_link_erased"


def test_customer_redact_only_scrubs_verified_local_subject_and_flags_unattributed_json(sandbox):
    db, org, stores, customers, rules, rows = sandbox
    result = run(sandbox, {customers[0].id})
    db.commit()
    assert result["legacy_execution_payloads_scrubbed"] == 1
    assert result["legacy_rules_scrubbed"] == 0
    assert result["legacy_possible_inflight_actions"] == 1
    assert result["legacy_unattributed_executions_for_review"] == 1
    assert result["legacy_shared_parent_executions_for_review"] == 1
    assert result["legacy_rules_with_unstructured_conditions_for_review"] == 1
    db.refresh(rows["buyer"])
    assert rows["buyer"].input_json == "{}"
    db.refresh(rows["other_buyer"])
    assert "SENSITIVE_OTHER" in rows["other_buyer"].input_json
    db.refresh(rows["unknown"])
    assert "SENSITIVE_UNKNOWN" in rows["unknown"].input_json
    db.refresh(rules[0])
    assert rules[0].active is True
    assert "SENSITIVE" in rules[0].conditions_json
    assert result["fulfillment_complete"] is False


def test_empty_subject_set_cannot_wipe_entire_store(sandbox):
    db, _, _, _, _, rows = sandbox
    result = run(sandbox, set())
    assert result["legacy_execution_payloads_scrubbed"] == 0
    assert rows["buyer"].input_json != "{}"


def test_parent_store_drift_blocks_before_any_mutation(sandbox):
    db, org, stores, customers, rules, rows = sandbox
    rows["unknown"].store_id = stores[1].id
    db.flush()
    with pytest.raises(ShopifyLegacyAutomationPrivacyError, match="PARENT_STORE_DRIFT"):
        run(sandbox, None)
    db.refresh(rows["buyer"])
    assert rows["buyer"].input_json != "{}"
    assert rules[0].active is True


@pytest.mark.parametrize("bad", [{-1}, [1], {True}, {"1"}])
def test_bad_customer_scope_rejected(sandbox, bad):
    db, org, stores, *_ = sandbox
    with pytest.raises(ShopifyLegacyAutomationPrivacyError, match="SCOPE_INVALID"):
        scrub_shopify_legacy_automations(
            db, organization_id=org.id, store_id=stores[0].id,
            customer_ids=bad,
        )
