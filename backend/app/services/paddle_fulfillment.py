"""Server-side Paddle webhook fulfillment and customer portal.

Verified events are mirrored by Paddle IDs. Unknown tenants remain unbound;
email alone never establishes ownership. No provider entity is deleted.
"""
import json
import logging
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.parse import urlparse

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..billing import get_subscription_price_id
from ..models import Organization
from ..model_domains.paddle_billing import (
    PaddleBillingCustomer, PaddleBillingSubscription, PaddleWebhookEvent,
    PaddleAiReconciliation,
)
from .ai_usage_packages import (
    fulfill_ai_usage_package_transaction, get_ai_usage_package,
    _transaction_matches_package_price, InvalidAiUsagePackageError,
)
from .billing_service import InvalidBillingPlanError, get_billing_price_id
from .paddle_checkout import (
    verify_signed_checkout_custom_data, verify_ai_package_custom_data,
)
from .paddle_webhooks import (
    is_canonical_subscription, is_duplicate_event, is_out_of_order_event,
    process_subscription_event, process_transaction_event,
    resolve_organization, update_billing_fields,
)

log = logging.getLogger(__name__)

SUBSCRIPTION_HANDLERS = {
    "subscription.created", "subscription.updated", "subscription.canceled",
    "subscription.trialing", "subscription.activated", "subscription.past_due",
    "subscription.paused", "subscription.resumed",
}
CUSTOMER_HANDLERS = {"customer.created", "customer.updated"}
TRANSACTION_HANDLERS = {"transaction.completed"}
SUPPORTED = SUBSCRIPTION_HANDLERS | CUSTOMER_HANDLERS | TRANSACTION_HANDLERS


def subscription_grants_access(subscription: PaddleBillingSubscription | None) -> bool:
    """Only current status grants access; scheduled changes do not revoke it."""
    return bool(subscription and subscription.status in {"active", "trialing"})


def _when(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None


def verify_notification(raw_body: bytes, signature: str, secret: str) -> dict:
    """The official Paddle Python SDK verifies the raw bytes before JSON parsing."""
    if not secret or not signature:
        raise ValueError("Missing Paddle signing configuration or signature")
    from paddle_billing.Notifications import Secret, Verifier

    # FastAPI Request.body() is asynchronous; SDK accepts a protocol with
    # a bytes .body and case-sensitive Paddle-Signature header.
    adapter = SimpleNamespace(
        body=raw_body, headers={"Paddle-Signature": signature}
    )
    try:
        verified = Verifier().verify(adapter, Secret(secret))
    except (ValueError, TypeError, ConnectionRefusedError, OverflowError) as exc:
        raise ValueError("Invalid Paddle signature") from exc
    if not verified:
        raise ValueError("Invalid Paddle signature")
    try:
        event = json.loads(raw_body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid Paddle JSON") from exc
    if not isinstance(event, dict):
        raise ValueError("Invalid Paddle event")
    return event


def _is_direct(org: Organization | None) -> bool:
    return bool(
        org
        and (org.billing_provider or "paddle").lower() != "shopify"
        and org.billing_onboarding_channel != "shopify_install"
    )


def _link(record, organization_id: int | None) -> None:
    if organization_id is None:
        return
    if record.organization_id is not None and record.organization_id != organization_id:
        raise ValueError("Paddle ID already belongs to a different organization")
    record.organization_id = organization_id


def _customer(db: Session, customer_id: str, occurred_at: datetime | None,
              email: str | None = None, organization_id: int | None = None):
    if not customer_id:
        return None
    record = db.get(PaddleBillingCustomer, customer_id)
    if record is None:
        record = PaddleBillingCustomer(customer_id=customer_id, email=email)
        db.add(record)
    if not (record.last_event_at and occurred_at and occurred_at < record.last_event_at):
        if email:
            record.email = email
        if occurred_at:
            record.last_event_at = occurred_at
    _link(record, organization_id)
    return record


def _subscription(db: Session, data: dict, occurred_at: datetime | None,
                  organization_id: int | None):
    sub_id = str(data.get("id") or "")
    customer_id = str(data.get("customer_id") or "")
    if not sub_id or not customer_id:
        raise ValueError("Paddle subscription/customer ID missing")
    _customer(db, customer_id, None, organization_id=organization_id)
    record = db.get(PaddleBillingSubscription, sub_id)
    if record is None:
        record = PaddleBillingSubscription(
            subscription_id=sub_id, customer_id=customer_id,
            status=str(data.get("status") or "unknown"),
        )
        db.add(record)
    if record.customer_id != customer_id:
        raise ValueError("Paddle subscription customer changed")
    _link(record, organization_id)
    if record.last_event_at and occurred_at and occurred_at < record.last_event_at:
        return record, False

    record.status = str(data.get("status") or record.status)
    items = data.get("items") or []
    if items and isinstance(items[0], dict):
        item = items[0]
        price = item.get("price") if isinstance(item.get("price"), dict) else {}
        record.price_id = price.get("id") or item.get("price_id") or record.price_id
        record.product_id = (
            price.get("product_id") or item.get("product_id") or record.product_id
        )
    scheduled = data.get("scheduled_change")
    if isinstance(scheduled, dict):
        record.scheduled_change_action = scheduled.get("action")
        record.scheduled_change_at = _when(scheduled.get("effective_at"))
    else:
        record.scheduled_change_action = None
        record.scheduled_change_at = None
    if occurred_at:
        record.last_event_at = occurred_at
    return record, True


def _signed_organization(db: Session, data: dict) -> Organization | None:
    custom = data.get("custom_data")
    if not isinstance(custom, dict) or not custom.get("checkout_signature"):
        return None
    try:
        plan = str(custom.get("plan") or "").lower()
        months = int(custom.get("billing_period_months") or 0)
        expected_price = get_billing_price_id(plan, months, "paddle")
        valid = verify_signed_checkout_custom_data(
            custom, actual_price_id=get_subscription_price_id(data),
            expected_price_id=expected_price,
            secret=(os.getenv("PADDLE_WEBHOOK_SECRET") or "").strip(),
        )
        if not valid:
            return None
        candidate = db.get(Organization, int(custom["organization_id"]))
        return candidate if _is_direct(candidate) else None
    except (ValueError, TypeError, KeyError, InvalidBillingPlanError):
        return None


def _organization(db: Session, event_type: str, data: dict):
    custom = data.get("custom_data") or {}
    if event_type == "transaction.completed" and custom.get("purchase_type") == "ai_usage_package":
        customer_id = str(data.get("customer_id") or "")
        if custom.get("package_signature"):
            if not verify_ai_package_custom_data(
                custom, actual_price_id=get_subscription_price_id(data),
                secret=(os.getenv("PADDLE_WEBHOOK_SECRET") or "").strip(),
            ):
                return None
            org = db.get(Organization, int(custom["organization_id"]))
            if not _is_direct(org):
                return None
            # An existing customer association must never move to another tenant.
            if org.billing_customer_id and customer_id and org.billing_customer_id != customer_id:
                return None
            return org

        # Legacy server-created transactions predate metadata signatures.
        # Never trust custom_data.organization_id for attribution. A known,
        # UNIQUE Paddle customer association plus the exact catalog price
        # and response count are required; otherwise queue for reconciliation.
        if not customer_id:
            return None
        try:
            package = get_ai_usage_package(str(custom.get("package_key") or ""))
            responses = int(custom.get("responses") or 0)
        except (ValueError, TypeError, InvalidAiUsagePackageError):
            return None
        expected_price = (os.getenv(package["price_env"]) or "").strip()
        if (
            not expected_price
            or responses != package["responses"]
            or not _transaction_matches_package_price(data, expected_price)
        ):
            return None
        owners = db.query(Organization).filter(
            Organization.billing_customer_id == customer_id
        ).all()
        return owners[0] if len(owners) == 1 and _is_direct(owners[0]) else None

    sub_id = (data.get("id") if event_type in SUBSCRIPTION_HANDLERS
              else data.get("subscription_id"))
    customer_id = data.get("customer_id")
    # An existing subscription binding is authoritative. A Paddle customer
    # may have multiple subscriptions; it cannot claim a new subscription.
    bound = None
    if sub_id:
        bound = db.query(Organization).filter(
            Organization.billing_subscription_id == sub_id
        ).first()
    signed = _signed_organization(db, data)
    if signed:
        if bound and bound.id != signed.id:
            raise ValueError("Signed Paddle tenant conflicts with subscription binding")
        return signed
    if _is_direct(bound):
        return bound
    if sub_id:
        return None
    # Only customer-scoped events without a subscription may use this fallback.
    by_customer = db.query(Organization).filter(
        Organization.billing_customer_id == customer_id
    ).all() if customer_id else []
    return by_customer[0] if len(by_customer) == 1 and _is_direct(by_customer[0]) else None


def _record(db: Session, event_id: str, event_type: str, when: datetime | None):
    db.add(PaddleWebhookEvent(
        event_id=event_id, event_type=event_type, occurred_at=when,
    ))



def _pending_ai_purchase(db: Session, event_id: str, data: dict,
                         occurred: datetime | None, reason: str) -> dict:
    """Retain completed payments without inventing a tenant or granting credits."""
    transaction_id = str(data.get("id") or "").strip()
    if not transaction_id:
        raise ValueError("Completed Paddle AI purchase has no transaction ID")
    custom = data.get("custom_data") or {}
    record = db.get(PaddleAiReconciliation, transaction_id)
    if record is None:
        record = PaddleAiReconciliation(
            transaction_id=transaction_id,
            event_id=event_id,
            customer_id=str(data.get("customer_id") or "") or None,
            claimed_organization_id=str(custom.get("organization_id") or "") or None,
            package_key=str(custom.get("package_key") or "") or None,
            price_id=get_subscription_price_id(data),
            reason=reason,
            status="pending",
            occurred_at=occurred,
        )
        db.add(record)
    # Do not mark the payment as fulfilled and do not delete or discard it.
    db.commit()
    return {
        "ok": True, "pending_reconciliation": True,
        "event_type": "transaction.completed",
        "transaction_id": transaction_id, "reason": reason,
    }


def reconcile_pending_ai_transaction(db: Session, transaction_id: str) -> dict:
    """Operator-invoked recovery using live Paddle API, never user-supplied IDs.

    Pending records are permanent. A customer without a unique verified
    organization remains pending until an authorized association exists.
    """
    pending = db.get(PaddleAiReconciliation, transaction_id)
    if not pending:
        raise LookupError("No pending Paddle AI payment for that transaction")
    from ..paddle_client import get_transaction
    transaction = get_transaction(transaction_id)
    if str(transaction.get("id") or "") != transaction_id or transaction.get("status") != "completed":
        raise ValueError("Paddle transaction not confirmed completed")
    if (transaction.get("custom_data") or {}).get("purchase_type") != "ai_usage_package":
        raise ValueError("Paddle transaction is not an AI package")
    org = _organization(db, "transaction.completed", transaction)
    if not org:
        return {"ok": True, "pending_reconciliation": True, "transaction_id": transaction_id}
    result = fulfill_ai_usage_package_transaction(
        db=db, organization_id=org.id, data=transaction, occurred_at=pending.occurred_at,
    )
    if result.get("credited") or result.get("duplicate"):
        pending.status = "credited"
        pending.resolved_at = datetime.utcnow()
        db.commit()
    return {**result, "transaction_id": transaction_id}

def _sync_customer_event(db: Session, data: dict, when: datetime | None):
    customer_id = str(data.get("id") or "")
    if not customer_id:
        raise ValueError("Paddle customer ID missing")
    org = db.query(Organization).filter(
        Organization.billing_customer_id == customer_id
    ).first()
    _customer(
        db, customer_id, when,
        email=data.get("email") if isinstance(data.get("email"), str) else None,
        organization_id=org.id if _is_direct(org) else None,
    )


def _sync_subscription_event(db: Session, data: dict, when: datetime | None,
                             org: Organization | None, event_type: str):
    if event_type == "subscription.canceled" and not data.get("status"):
        data = {**data, "status": "canceled"}
    return _subscription(db, data, when, org.id if org else None)


def _sync_transaction_customer(db: Session, data: dict, org: Organization | None):
    if not org:
        return
    customer_id = str(data.get("customer_id") or "")
    if not customer_id:
        return
    _customer(db, customer_id, None, organization_id=org.id)
    sub_id = str(data.get("subscription_id") or "")
    if sub_id:
        mirror = db.get(PaddleBillingSubscription, sub_id)
        if mirror:
            _link(mirror, org.id)


def dispatch_verified_notification(event: dict, db: Session) -> dict:
    """Dispatch exactly once; business updates and receipt share one DB commit."""
    kind = str(event.get("event_type") or "")
    event_id = str(event.get("event_id") or "")
    if not kind or not event_id or not isinstance(event.get("data"), dict):
        raise ValueError("Invalid Paddle event envelope")
    if kind not in SUPPORTED:
        return {"ok": True, "ignored": True, "event_type": kind}
    if db.get(PaddleWebhookEvent, event_id):
        return {"ok": True, "duplicate": True, "event_type": kind}
    data = event["data"]
    occurred = _when(event.get("occurred_at"))

    if kind in CUSTOMER_HANDLERS:
        _sync_customer_event(db, data, occurred)
        _record(db, event_id, kind, occurred)
        db.commit()
        return {"ok": True, "event_type": kind}

    org = _organization(db, kind, data)
    custom = data.get("custom_data") or {}
    if kind == "transaction.completed" and custom.get("purchase_type") == "ai_usage_package":
        # Paid AI packages are one-time purchases, independent of the latest
        # subscription event timestamp and canonical subscription ID.
        _record(db, event_id, kind, occurred)
        if not org:
            return _pending_ai_purchase(
                db, event_id, data, occurred, "unverified_or_ambiguous_owner",
            )
        result = fulfill_ai_usage_package_transaction(
            db=db, organization_id=org.id, data=data, occurred_at=occurred,
        )
        if result.get("ignored"):
            return _pending_ai_purchase(
                db, event_id, data, occurred, str(result.get("reason") or "invalid_package"),
            )
        db.commit()
        return {**result, "event_type": kind, "transaction_id": data.get("id")}
    if kind in SUBSCRIPTION_HANDLERS:
        mirror, current = _sync_subscription_event(db, data, occurred, org, kind)
        _record(db, event_id, kind, occurred)
        if not current or not org:
            db.commit()
            return {"ok": True, "ignored": True, "reason": "unbound_or_stale_subscription", "event_type": kind}
        if not is_canonical_subscription(org, mirror.subscription_id):
            db.commit()
            return {"ok": True, "ignored": True, "reason": "non_canonical_subscription", "event_type": kind}
        if is_out_of_order_event(org, occurred):
            db.commit()
            return {"ok": True, "ignored": True, "reason": "out_of_order_event", "event_type": kind}

        price_id = get_subscription_price_id(data)
        from ..billing import get_plan_from_price_id, get_billing_period_from_price_id
        plan = get_plan_from_price_id(price_id) if price_id else None
        months = get_billing_period_from_price_id(price_id) if price_id else None
        update_billing_fields(org, data.get("customer_id"), mirror.subscription_id,
                              price_id, months)
        status = data.get("status") or ("canceled" if kind == "subscription.canceled" else None)
        return process_subscription_event(
            org, event_id, occurred, kind, plan, price_id, months,
            status, data, db,
        )

    # A completed transaction may bootstrap an organization through signed
    # plan intent. Never attribute an unsigned custom_data organization ID.
    _record(db, event_id, kind, occurred)
    if not org:
        db.commit()
        return {"ok": True, "ignored": True, "reason": "organization_not_found", "event_type": kind}
    _sync_transaction_customer(db, data, org)
    sub_id = data.get("subscription_id")
    if sub_id and not is_canonical_subscription(org, sub_id):
        db.commit()
        return {"ok": True, "ignored": True, "reason": "non_canonical_subscription", "event_type": kind}
    if is_out_of_order_event(org, occurred):
        db.commit()
        return {"ok": True, "ignored": True, "reason": "out_of_order_event", "event_type": kind}
    price_id = get_subscription_price_id(data)
    from ..billing import get_plan_from_price_id, get_billing_period_from_price_id
    plan = get_plan_from_price_id(price_id) if price_id else None
    months = get_billing_period_from_price_id(price_id) if price_id else None
    update_billing_fields(org, data.get("customer_id"), sub_id, price_id, months)
    result = process_transaction_event(org, event_id, occurred, plan, data, db)
    return {**result, "event_type": kind, "transaction_id": data.get("id")}


def create_portal_session_url(db: Session, organization: Organization) -> str:
    """A temporary, tenant-bound session URL; never saved or logged."""
    if not _is_direct(organization):
        raise ValueError("Paddle billing is unavailable for this organization")
    customer_id = organization.billing_customer_id
    customer = db.get(PaddleBillingCustomer, customer_id) if customer_id else None
    if not customer or customer.organization_id != organization.id:
        raise LookupError("Paddle billing customer has not synchronized yet")
    subscription_ids: list[str] = []
    if organization.billing_subscription_id:
        sub = db.get(PaddleBillingSubscription, organization.billing_subscription_id)
        if not sub or sub.organization_id != organization.id or sub.customer_id != customer_id:
            raise LookupError("Paddle subscription has not synchronized yet")
        subscription_ids = [sub.subscription_id]

    api_key = (os.getenv("PADDLE_API_KEY") or "").strip()
    environment = (os.getenv("PADDLE_ENVIRONMENT") or "").strip().lower()
    if not api_key or environment not in {"production", "sandbox"}:
        raise RuntimeError("Paddle API environment is not configured")
    from paddle_billing import Client, Environment, Options
    from paddle_billing.Resources.CustomerPortalSessions.Operations import CreateCustomerPortalSession

    options = Options(Environment.SANDBOX) if environment == "sandbox" else Options(Environment.PRODUCTION)
    paddle = Client(api_key, options=options)
    session = paddle.customer_portal_sessions.create(
        customer_id,
        CreateCustomerPortalSession(subscription_ids=subscription_ids),
    )
    url = str(session.urls.general.overview)
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "customer-portal.paddle.com":
        raise RuntimeError("Paddle returned an invalid customer portal URL")
    return url
