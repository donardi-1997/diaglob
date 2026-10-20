"""Validate and write provenance at the moment a legacy execution starts.

Never infer a Shopify buyer from JSON, event IDs, email, phone or free text.
A local CustomerStoreProfile link is NOT independent Shopify shop/customer
attestation; it is useful lineage for later review only.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import Automation, Customer, CustomerStoreProfile, Store
from ..model_domains.automation_provenance import AutomationExecutionProvenance


class AutomationProvenanceError(ValueError):
    """PII-free validation failure."""


@dataclass(frozen=True)
class AutomationProvenanceScope:
    organization_id: int
    store_id: int | None
    customer_id: int | None
    source_context: str
    subject_linkage: str


def prepare_execution_provenance(
    db: Session, *, automation: Automation,
    event_store_id: int | None = None,
    subject_customer_id: int | None = None,
) -> AutomationProvenanceScope:
    """Return vetted IDs. Must run before creation or side effects."""
    org = automation.organization_id
    parent_store = automation.store_id
    if not isinstance(org, int) or isinstance(org, bool) or org <= 0:
        raise AutomationProvenanceError("INVALID_AUTOMATION_ORGANIZATION")
    for value in (event_store_id, subject_customer_id):
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
        ):
            raise AutomationProvenanceError("INVALID_PROVENANCE_IDENTIFIER")

    if (
        parent_store is not None and event_store_id is not None
        and parent_store != event_store_id
    ):
        raise AutomationProvenanceError("AUTOMATION_EVENT_STORE_MISMATCH")
    store_id = event_store_id if event_store_id is not None else parent_store
    source = "explicit_dispatch_store" if event_store_id is not None else (
        "automation_store" if store_id is not None else "organization_only"
    )

    if store_id is not None:
        exists = db.query(Store.id).filter(
            Store.id == store_id,
            Store.organization_id == org,
            Store.deleted.is_(False),
            Store.active.is_(True),
        ).first()
        if exists is None:
            raise AutomationProvenanceError("UNVERIFIED_AUTOMATION_STORE")

    if subject_customer_id is not None:
        if store_id is None:
            raise AutomationProvenanceError("SUBJECT_WITHOUT_VERIFIED_STORE")
        # Require a customer in the tenant AND an explicit, unique
        # store-local mapping with an external ID. The provider cannot be
        # inferred here; this is NOT yet a verified Shopify identity.
        linked = db.query(CustomerStoreProfile.id).join(
            Customer, CustomerStoreProfile.customer_id == Customer.id,
        ).filter(
            Customer.id == subject_customer_id,
            Customer.organization_id == org,
            CustomerStoreProfile.organization_id == org,
            CustomerStoreProfile.store_id == store_id,
            CustomerStoreProfile.customer_id == subject_customer_id,
            CustomerStoreProfile.external_customer_id.is_not(None),
            CustomerStoreProfile.external_customer_id != "",
        ).limit(2).all()
        if len(linked) != 1:
            raise AutomationProvenanceError("CUSTOMER_STORE_LINK_UNVERIFIED")
        return AutomationProvenanceScope(
            organization_id=org, store_id=store_id,
            customer_id=subject_customer_id, source_context=source,
            subject_linkage="local_profile_shopify_unverified",
        )

    return AutomationProvenanceScope(
        organization_id=org, store_id=store_id, customer_id=None,
        source_context=source,
        subject_linkage=(
            "subject_not_asserted" if store_id is not None
            else "store_and_subject_not_asserted"
        ),
    )


def write_execution_provenance(
    db: Session, *, execution_id: int, scope: AutomationProvenanceScope,
) -> None:
    """Flush the minimal record in the same transaction as its execution."""
    db.add(AutomationExecutionProvenance(
        execution_id=execution_id,
        organization_id=scope.organization_id,
        store_id=scope.store_id,
        customer_id=scope.customer_id,
        source_context=scope.source_context,
        subject_linkage=scope.subject_linkage,
        provenance_version=1,
    ))
    db.flush()
