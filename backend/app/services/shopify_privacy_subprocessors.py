"""External subprocessor manifest with read-only per-shop activation detection.

A connection row means personal data may already have been shared with that
third party; it is NOT proof of a data-processing agreement, an independent
verification, or an erasure performed by the processor. Every entry stays
``unverified`` until an external artifact is independently validated through
the control registry. Activation detection never selects tokens, emails,
identifiers or other personal values — only row counts.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..instagram_models import InstagramConnection
from ..models import (
    CommerceConnection,
    DropiConnection,
    GoogleConnection,
    MetaAdsConnection,
    PaymentConnection,
    Store,
    WhatsAppConnection,
)
from ..model_domains.knowledge import KnowledgeBase, KnowledgeSource
from ..model_domains.paddle_billing import PaddleBillingCustomer
from ..model_domains.shipments import CarrierConnection
from ..model_domains.supplier_integrations import SupplierConnection
from ..telegram_models import TelegramConnection
from .shopify_privacy_controls import PROCESSOR_CONTROLS, _verified_request
from .shopify_privacy_scope_preview import preview_shopify_privacy_scope


class ShopifyPrivacySubprocessorError(ValueError):
    """Stable, PII-free subprocessor manifest failure codes."""


# Detector identifiers are plain strings so the manifest stays frozen and
# JSON-serializable; dispatch happens in ``_detector_counts``.
DETECTOR_STORE_COMMERCE_PROVIDER = "store_commerce_provider"
DETECTOR_STORE_DROPI = "store_dropi"
DETECTOR_STORE_SUPPLIER_CJ = "store_supplier_cj"
DETECTOR_STORE_META_ADS = "store_meta_ads"
DETECTOR_ORG_GOOGLE = "organization_google"
DETECTOR_STORE_WHATSAPP = "store_whatsapp"
DETECTOR_STORE_TELEGRAM = "store_telegram"
DETECTOR_STORE_INSTAGRAM = "store_instagram"
DETECTOR_STORE_PAYMENT_PROVIDER = "store_payment_provider"
DETECTOR_ORG_PADDLE = "organization_paddle_customers"
DETECTOR_ORG_KNOWLEDGE_BASES = "organization_knowledge_bases"
DETECTOR_ORG_KNOWLEDGE_SOURCES = "organization_knowledge_sources"
DETECTOR_STORE_CARRIERS = "store_carriers"
DETECTOR_MANUAL = "manual_confirmation"


@dataclass(frozen=True)
class SubprocessorManifestEntry:
    key: str
    name: str
    purpose: str
    data_categories: tuple[str, ...]
    control: str
    scope: str  # "store" | "organization" | "manual"
    detector: str
    provider: str | None = None


# Every processor that can receive, store or derive personal data in this
# codebase must appear here AND in PROCESSOR_CONTROLS. A control name shared
# with the evidence registry is how operator confirmation is recorded.
SUBPROCESSOR_MANIFEST: tuple[SubprocessorManifestEntry, ...] = (
    SubprocessorManifestEntry(
        key="shopify_admin_api",
        name="Shopify Admin API",
        purpose="Order, fulfillment, draft-order and compliance-webhook processing",
        data_categories=(
            "orders_and_fulfillment",
            "customer_contact_for_order_processing",
            "store_configuration",
        ),
        control="shopify_admin_api",
        scope="store",
        detector=DETECTOR_STORE_COMMERCE_PROVIDER,
        provider="shopify",
    ),
    SubprocessorManifestEntry(
        key="nuvemshop_admin_api",
        name="Nuvemshop Admin API",
        purpose="Non-Shopify storefront catalog, order and webhook processing",
        data_categories=(
            "orders_and_fulfillment",
            "customer_contact_for_order_processing",
            "store_configuration",
        ),
        control="nuvemshop_admin_api",
        scope="store",
        detector=DETECTOR_STORE_COMMERCE_PROVIDER,
        provider="nuvemshop",
    ),
    SubprocessorManifestEntry(
        key="dropi_supplier",
        name="Dropi",
        purpose="Dropshipping catalog, order forwarding and shipping status",
        data_categories=("product_catalog", "order_and_shipping_data"),
        control="dropi_supplier",
        scope="store",
        detector=DETECTOR_STORE_DROPI,
    ),
    SubprocessorManifestEntry(
        key="cj_supplier",
        name="CJ Dropshipping",
        purpose="Supplier orders, fulfillment and tracking webhooks",
        data_categories=("supplier_order_data", "shipping_and_tracking_data"),
        control="cj_supplier",
        scope="store",
        detector=DETECTOR_STORE_SUPPLIER_CJ,
    ),
    SubprocessorManifestEntry(
        key="advertising_meta",
        name="Meta Ads",
        purpose=(
            "Advertising account synchronization; Meta Pixel activation is a "
            "future release gate and is not implemented"
        ),
        data_categories=("advertising_account_data", "conversion_attribution"),
        control="advertising_meta",
        scope="store",
        detector=DETECTOR_STORE_META_ADS,
    ),
    SubprocessorManifestEntry(
        key="google_workspace_apis",
        name="Google Drive and Sheets APIs",
        purpose="Knowledge-base document ingestion from Drive and Sheets",
        data_categories=(
            "google_account_identity",
            "drive_and_sheets_documents",
        ),
        control="google_workspace_apis",
        scope="organization",
        detector=DETECTOR_ORG_GOOGLE,
    ),
    SubprocessorManifestEntry(
        key="whatsapp_provider",
        name="WhatsApp Business provider",
        purpose="Outbound and inbound WhatsApp messaging",
        data_categories=("message_content", "recipient_contact_data"),
        control="whatsapp_provider",
        scope="store",
        detector=DETECTOR_STORE_WHATSAPP,
    ),
    SubprocessorManifestEntry(
        key="telegram_messaging",
        name="Telegram Bot API",
        purpose="Telegram bot messaging",
        data_categories=("message_content", "recipient_contact_data"),
        control="telegram_messaging",
        scope="store",
        detector=DETECTOR_STORE_TELEGRAM,
    ),
    SubprocessorManifestEntry(
        key="instagram_messaging",
        name="Instagram Messaging",
        purpose="Instagram direct messaging",
        data_categories=("message_content", "recipient_contact_data"),
        control="instagram_messaging",
        scope="store",
        detector=DETECTOR_STORE_INSTAGRAM,
    ),
    SubprocessorManifestEntry(
        key="email_delivery",
        name="Transactional email provider",
        purpose="Transactional email delivery",
        data_categories=("email_content", "recipient_contact_data"),
        control="email_delivery",
        scope="manual",
        detector=DETECTOR_MANUAL,
    ),
    SubprocessorManifestEntry(
        key="mercado_pago_payments",
        name="Mercado Pago",
        purpose="PIX payment processing and webhook status",
        data_categories=("payment_transaction_data", "payer_contact_data"),
        control="mercado_pago_payments",
        scope="store",
        detector=DETECTOR_STORE_PAYMENT_PROVIDER,
        provider="mercado_pago",
    ),
    SubprocessorManifestEntry(
        key="nequi_payments",
        name="Nequi",
        purpose="Nequi push payment processing and webhook status",
        data_categories=("payment_transaction_data", "payer_contact_data"),
        control="nequi_payments",
        scope="store",
        detector=DETECTOR_STORE_PAYMENT_PROVIDER,
        provider="nequi",
    ),
    SubprocessorManifestEntry(
        key="paddle_billing",
        name="Paddle",
        purpose="App subscription billing and invoicing",
        data_categories=("billing_contact_email", "subscription_and_invoice_data"),
        control="paddle_billing",
        scope="organization",
        detector=DETECTOR_ORG_PADDLE,
    ),
    SubprocessorManifestEntry(
        key="aws_bedrock",
        name="AWS Bedrock knowledge bases",
        purpose="AI retrieval over knowledge-base ingestions",
        data_categories=("knowledge_base_documents", "prompts_and_responses"),
        control="aws_bedrock",
        scope="organization",
        detector=DETECTOR_ORG_KNOWLEDGE_BASES,
    ),
    SubprocessorManifestEntry(
        key="files_and_object_storage",
        name="S3 object storage",
        purpose="Uploaded knowledge documents and generated artifacts",
        data_categories=("uploaded_documents", "generated_artifacts"),
        control="files_and_object_storage",
        scope="organization",
        detector=DETECTOR_ORG_KNOWLEDGE_SOURCES,
    ),
    SubprocessorManifestEntry(
        key="carrier_logistics",
        name="Carrier logistics network",
        purpose="Label, shipment and tracking event exchange",
        data_categories=("shipment_recipient_data", "tracking_events"),
        control="carrier_logistics",
        scope="store",
        detector=DETECTOR_STORE_CARRIERS,
    ),
)


def _validate_tenant(organization_id: int, store_id: int) -> None:
    for label, value in (("organization_id", organization_id), ("store_id", store_id)):
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ShopifyPrivacySubprocessorError(f"UNVERIFIED_SUBPROCESSOR_{label.upper()}")


def _count(db: Session, model, *conditions) -> int:
    return int(db.query(model).filter(*conditions).count())


def _detector_counts(
    db: Session,
    entry: SubprocessorManifestEntry,
    *,
    organization_id: int,
    store_id: int,
) -> tuple[int, int | None]:
    """Return (rows, connected_rows|None) without selecting any row values."""
    detector = entry.detector
    if detector == DETECTOR_MANUAL:
        return 0, None

    if detector == DETECTOR_STORE_COMMERCE_PROVIDER:
        base = (
            CommerceConnection.organization_id == organization_id,
            CommerceConnection.store_id == store_id,
            CommerceConnection.provider == entry.provider,
        )
        return (
            _count(db, CommerceConnection, *base),
            _count(db, CommerceConnection, *base, CommerceConnection.status == "connected"),
        )

    if detector == DETECTOR_STORE_DROPI:
        base = (
            DropiConnection.organization_id == organization_id,
            DropiConnection.store_id == store_id,
        )
        return (
            _count(db, DropiConnection, *base),
            _count(db, DropiConnection, *base, DropiConnection.status == "connected"),
        )

    if detector == DETECTOR_STORE_SUPPLIER_CJ:
        base = (
            SupplierConnection.organization_id == organization_id,
            SupplierConnection.store_id == store_id,
            SupplierConnection.provider == "cj",
        )
        return (
            _count(db, SupplierConnection, *base),
            _count(db, SupplierConnection, *base, SupplierConnection.status == "connected"),
        )

    if detector == DETECTOR_STORE_META_ADS:
        base = (
            MetaAdsConnection.organization_id == organization_id,
            MetaAdsConnection.store_id == store_id,
        )
        return (
            _count(db, MetaAdsConnection, *base),
            _count(db, MetaAdsConnection, *base, MetaAdsConnection.status == "connected"),
        )

    if detector == DETECTOR_ORG_GOOGLE:
        base = (GoogleConnection.organization_id == organization_id,)
        return (
            _count(db, GoogleConnection, *base),
            _count(db, GoogleConnection, *base, GoogleConnection.status == "connected"),
        )

    if detector == DETECTOR_STORE_WHATSAPP:
        base = (
            WhatsAppConnection.organization_id == organization_id,
            WhatsAppConnection.store_id == store_id,
        )
        return (
            _count(db, WhatsAppConnection, *base),
            _count(db, WhatsAppConnection, *base, WhatsAppConnection.status == "connected"),
        )

    if detector == DETECTOR_STORE_TELEGRAM:
        base = (
            TelegramConnection.organization_id == organization_id,
            TelegramConnection.store_id == store_id,
        )
        return (
            _count(db, TelegramConnection, *base),
            _count(db, TelegramConnection, *base, TelegramConnection.status == "connected"),
        )

    if detector == DETECTOR_STORE_INSTAGRAM:
        base = (
            InstagramConnection.organization_id == organization_id,
            InstagramConnection.store_id == store_id,
        )
        return (
            _count(db, InstagramConnection, *base),
            _count(db, InstagramConnection, *base, InstagramConnection.status == "connected"),
        )

    if detector == DETECTOR_STORE_PAYMENT_PROVIDER:
        base = (
            PaymentConnection.organization_id == organization_id,
            PaymentConnection.store_id == store_id,
            PaymentConnection.provider == entry.provider,
        )
        return (
            _count(db, PaymentConnection, *base),
            _count(db, PaymentConnection, *base, PaymentConnection.status == "connected"),
        )

    if detector == DETECTOR_ORG_PADDLE:
        base = (PaddleBillingCustomer.organization_id == organization_id,)
        # No connection status exists; presence of a billing customer row is
        # itself the activation signal for this processor.
        return _count(db, PaddleBillingCustomer, *base), None

    if detector == DETECTOR_ORG_KNOWLEDGE_BASES:
        base = (KnowledgeBase.organization_id == organization_id,)
        return (
            _count(db, KnowledgeBase, *base),
            _count(db, KnowledgeBase, *base, KnowledgeBase.active.is_(True)),
        )

    if detector == DETECTOR_ORG_KNOWLEDGE_SOURCES:
        base = (KnowledgeSource.organization_id == organization_id,)
        return _count(db, KnowledgeSource, *base), None

    if detector == DETECTOR_STORE_CARRIERS:
        base = (
            CarrierConnection.organization_id == organization_id,
            CarrierConnection.store_id == store_id,
        )
        return (
            _count(db, CarrierConnection, *base),
            _count(db, CarrierConnection, *base, CarrierConnection.status == "connected"),
        )

    raise ShopifyPrivacySubprocessorError("UNKNOWN_SUBPROCESSOR_DETECTOR")


def _activation(rows: int, connected: int | None, detector: str) -> str:
    if detector == DETECTOR_MANUAL:
        return "manual_confirmation_required"
    if rows <= 0:
        return "not_detected"
    if connected is not None and connected > 0:
        return "connected"
    return "present_unverified"


def inspect_shopify_privacy_subprocessors(
    db: Session,
    *,
    organization_id: int,
    store_id: int,
) -> dict:
    """List every external processor with activation counts for one shop.

    Callers must already have a signed, verified tenant/shop mapping. Row
    counts are the only values returned; no connection is exported, decrypted
    or validated against the provider.
    """
    _validate_tenant(organization_id, store_id)
    store = db.query(Store.id).filter(
        Store.id == store_id,
        Store.organization_id == organization_id,
    ).first()
    if store is None:
        raise ShopifyPrivacySubprocessorError("SUBPROCESSOR_SHOP_NOT_FOUND")

    subprocessors = []
    for entry in SUBPROCESSOR_MANIFEST:
        rows, connected = _detector_counts(
            db, entry, organization_id=organization_id, store_id=store_id,
        )
        subprocessors.append({
            "key": entry.key,
            "name": entry.name,
            "purpose": entry.purpose,
            "data_categories": list(entry.data_categories),
            "control": entry.control,
            "scope": entry.scope,
            "activation": _activation(rows, connected, entry.detector),
            "connection_rows": rows,
            "connected_rows": connected,
            "verification_status": "unverified",
            "independently_verified": False,
            "external_erasure_verified": False,
        })

    referenced_controls = {entry.control for entry in SUBPROCESSOR_MANIFEST}
    return {
        "manifest_version": 1,
        "subprocessors": subprocessors,
        "manifest_entry_count": len(subprocessors),
        "active_processor_count": sum(
            1 for item in subprocessors if item["activation"] in {"connected", "present_unverified"}
        ),
        "controls_without_manifest_entry": sorted(
            set(PROCESSOR_CONTROLS) - referenced_controls
        ),
        "manifest_entries_without_control": sorted(
            referenced_controls - set(PROCESSOR_CONTROLS)
        ),
        "independently_verified": False,
        "external_erasure_verified": False,
        "fulfillment_complete": False,
    }


def inspect_shopify_privacy_case_subprocessors(
    db: Session,
    *,
    request_id: str,
) -> dict:
    """Subprocessor view for one signed privacy case's verified shop only."""
    request = _verified_request(db, request_id)
    preview = preview_shopify_privacy_scope(db, request)
    manifest = inspect_shopify_privacy_subprocessors(
        db,
        organization_id=request.organization_id,
        store_id=request.store_id,
    )
    return {
        "request_id": request_id,
        "topic": request.topic,
        "shop_scope": preview.scope_status,
        **manifest,
    }
