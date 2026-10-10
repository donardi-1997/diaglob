"""Read-only privacy data-surface inventory from SQLAlchemy metadata.

No database connection, PII query, export, redaction, API endpoint, or worker.
A schema inventory is not proof of complete GDPR compliance.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import MetaData

from ..db import Base
from .. import models as _models  # noqa: F401  Register all ORM domains.


@dataclass(frozen=True)
class PrivacyTableCoverage:
    table: str
    ownership: str
    coverage: str
    # "partial" is never an approval to export or delete this table.


@dataclass(frozen=True)
class PrivacyCoverageInventory:
    tables: tuple[PrivacyTableCoverage, ...]
    unclassified_sensitive_tables: tuple[str, ...]
    missing_declared_tables: tuple[str, ...]
    external_review_areas: tuple[str, ...]
    ready_for_live_privacy_processing: bool = False


# Only tables already understood in code are "partial"; every other known
# table remains uncovered pending field-level ownership and retention review.
DECLARED_COVERAGE: tuple[PrivacyTableCoverage, ...] = (
    PrivacyTableCoverage("customers", "organization_shared", "uncovered"),
    PrivacyTableCoverage("customer_store_profiles", "store", "partial"),
    PrivacyTableCoverage("orders", "store", "partial"),
    PrivacyTableCoverage("order_items", "store_via_order", "partial"),
    PrivacyTableCoverage("conversations", "store", "partial"),
    PrivacyTableCoverage("messages", "store_via_conversation", "partial"),
    PrivacyTableCoverage("conversational_checkouts", "store", "partial"),
    PrivacyTableCoverage("agent_action_approvals", "store_and_organization", "uncovered"),
    PrivacyTableCoverage("agent_chat_sessions", "store_and_organization", "uncovered"),
    PrivacyTableCoverage("agent_chat_messages", "store_via_session", "uncovered"),
    PrivacyTableCoverage("agent_chat_tool_calls", "store_via_session", "uncovered"),
    PrivacyTableCoverage("knowledge_sources", "organization_and_external", "uncovered"),
    PrivacyTableCoverage("customer_risk_reports", "shared_and_organization", "uncovered"),
    PrivacyTableCoverage("customer_risk_disputes", "shared_and_organization", "uncovered"),
    PrivacyTableCoverage("auto_fulfillment_jobs", "store_or_order", "uncovered"),
    PrivacyTableCoverage("automations", "store_or_organization", "uncovered"),
    PrivacyTableCoverage("automation_executions", "store_or_organization", "uncovered"),
    PrivacyTableCoverage("automation_campaigns", "store", "uncovered"),
    PrivacyTableCoverage("automation_audience_members", "store_via_campaign", "uncovered"),
    PrivacyTableCoverage("automation_runs", "store_via_campaign", "uncovered"),
    PrivacyTableCoverage("automation_recipient_executions", "store_via_campaign_run", "uncovered"),
    PrivacyTableCoverage("automation_delivery_attempts", "store_via_recipient", "uncovered"),
    PrivacyTableCoverage("automation_flows", "store", "uncovered"),
    PrivacyTableCoverage("automation_flow_versions", "store_via_flow", "uncovered"),
    PrivacyTableCoverage("automation_flow_runs", "store", "uncovered"),
    PrivacyTableCoverage("automation_flow_recipient_executions", "store_via_flow_run", "uncovered"),
    PrivacyTableCoverage("automation_node_executions", "store_via_recipient", "uncovered"),
)

EXTERNAL_REVIEW_AREAS: tuple[str, ...] = (
    "shopify_customer_orders_and_webhook_data",
    "ai_provider_prompts_responses_and_derived_profiles",
    "automation_executions_and_queued_payloads",
    "object_storage_and_knowledge_base_ingestions",
    "email_whatsapp_and_messaging_providers",
    "supplier_dropi_shipping_and_tracking_systems",
    "analytics_events_exports_and_ad_platforms",
    "application_logs_monitoring_and_backups",
    "retention_legal_holds_and_restore_reingestion",
)

# A column-name heuristic identifies new sources for human review, rather than
# silently classifying a new sensitive table as safe.
_SENSITIVE_COLUMN_HINTS: tuple[str, ...] = (
    "customer", "email", "phone", "address", "message", "content",
    "conversation", "recipient", "shipping", "payload", "prompt",
    "personal", "session", "contact", "identity",
)


def inspect_shopify_privacy_coverage(
    metadata: MetaData | None = None,
) -> PrivacyCoverageInventory:
    """Review table names and columns only; never execute SQL or return PII."""
    metadata = metadata if metadata is not None else Base.metadata
    known = {entry.table: entry for entry in DECLARED_COVERAGE}
    existing = set(metadata.tables)
    missing = tuple(sorted(set(known) - existing))
    unclassified = []
    for name, table in sorted(metadata.tables.items()):
        if name in known:
            continue
        fields = (column.name.lower() for column in table.columns)
        if any(
            any(hint in column_name for hint in _SENSITIVE_COLUMN_HINTS)
            for column_name in fields
        ):
            unclassified.append(name)

    return PrivacyCoverageInventory(
        tables=tuple(
            sorted(
                (entry for name, entry in known.items() if name in existing),
                key=lambda entry: entry.table,
            )
        ),
        unclassified_sensitive_tables=tuple(unclassified),
        missing_declared_tables=missing,
        external_review_areas=EXTERNAL_REVIEW_AREAS,
        # Deliberate fail-closed constant: exhaustive field provenance, external
        # processors and legal retention decisions cannot be proven by metadata.
        ready_for_live_privacy_processing=False,
    )
