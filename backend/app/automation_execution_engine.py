"""Durable scheduler and delivery worker for Automation Campaigns V2.1A."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .automation_campaigns import audience_metrics, json_load, render_template
from .models import (
    AutomationCampaign, AutomationDeliveryAttempt, AutomationRecipientExecution,
    AutomationRateLimit, AutomationRun, Store, WhatsAppConnection,
)
from .whatsapp_client import WhatsAppDeliveryError, send_whatsapp_text_message
from .whatsapp_security import decrypt_whatsapp_secret

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = int(os.getenv("AUTOMATION_MAX_ATTEMPTS", "3"))
BATCH_SIZE = int(os.getenv("AUTOMATION_BATCH_SIZE", "50"))
LEASE_SECONDS = int(os.getenv("AUTOMATION_LEASE_SECONDS", "120"))
MAX_PER_MINUTE = int(os.getenv("AUTOMATION_WHATSAPP_MAX_PER_MINUTE", "20"))
BACKOFF_SECONDS = (60, 300, 1800)
TERMINAL = {"sent", "failed", "skipped", "ambiguous"}


def utcnow() -> datetime:
    return datetime.utcnow()


def initial_next_run(campaign: AutomationCampaign, now: datetime | None = None) -> datetime | None:
    now = now or utcnow()
    config = json_load(campaign.schedule_config)
    if campaign.schedule_type == "once":
        value = datetime.fromisoformat(config["starts_at"].replace("Z", "+00:00"))
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
    return next_schedule_at(campaign, now - timedelta(seconds=1))


def next_schedule_at(campaign: AutomationCampaign, after: datetime) -> datetime:
    config = json_load(campaign.schedule_config)
    zone = ZoneInfo(campaign.timezone)
    local_after = after.replace(tzinfo=timezone.utc).astimezone(zone)
    time_of_day = config.get("time_of_day", "10:00")
    hour, minute = map(int, time_of_day.split(":"))
    candidate = local_after.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if campaign.schedule_type == "daily":
        if candidate <= local_after:
            candidate += timedelta(days=1)
    elif campaign.schedule_type == "weekly":
        days = sorted(int(day) for day in config.get("days_of_week", []))
        for offset in range(8):
            proposed = candidate + timedelta(days=offset)
            if proposed.weekday() in days and proposed > local_after:
                candidate = proposed
                break
    elif campaign.schedule_type == "every_n_days":
        interval = int(config["interval_days"])
        base_value = config.get("starts_at") or (campaign.created_at or utcnow()).isoformat()
        starts_at = datetime.fromisoformat(base_value.replace("Z", "+00:00"))
        if starts_at.tzinfo is None:
            starts_at = starts_at.replace(tzinfo=zone)
        base = starts_at.astimezone(zone).replace(hour=hour, minute=minute, second=0, microsecond=0)
        candidate = base
        while candidate <= local_after:
            candidate += timedelta(days=interval)
    return candidate.astimezone(timezone.utc).replace(tzinfo=None)


def materialize_due_campaigns(db: Session, now: datetime | None = None) -> int:
    """Create one snapshot run per due campaign. Unique schedule key makes restarts safe."""
    now = now or utcnow()
    # V2.1 campaigns created before migration 010 have no operational schedule state.
    # Only initialize campaigns that have never materialized a run; exhausted one-time
    # campaigns keep next_run_at NULL.
    unscheduled = db.query(AutomationCampaign).filter(
        AutomationCampaign.status == "active",
        AutomationCampaign.execution_enabled_at.isnot(None),
        AutomationCampaign.next_run_at.is_(None),
        AutomationCampaign.last_run_at.is_(None),
    ).all()
    for campaign in unscheduled:
        try:
            campaign.next_run_at = initial_next_run(campaign, now)
        except Exception:
            logger.exception("automation campaign has invalid schedule", extra={"campaign_id": campaign.id})
            campaign.status = "paused"
    if unscheduled:
        db.commit()
    query = db.query(AutomationCampaign).filter(AutomationCampaign.status == "active", AutomationCampaign.execution_enabled_at.isnot(None), AutomationCampaign.next_run_at.isnot(None), AutomationCampaign.next_run_at <= now)
    if db.bind and db.bind.dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    campaigns = query.limit(BATCH_SIZE).all()
    created = 0
    for campaign in campaigns:
        try:
            ZoneInfo(campaign.timezone)
        except Exception:
            logger.exception("automation campaign has invalid timezone", extra={"campaign_id": campaign.id})
            campaign.status = "paused"
            campaign.next_run_at = None
            continue
        # Do not overlap campaign runs: execution-time cooldown can then be
        # checked without two same-campaign recipients racing to send.
        unfinished = db.query(AutomationRun.id).filter(
            AutomationRun.automation_id == campaign.id,
            AutomationRun.status.in_(("pending", "running")),
        ).first()
        if unfinished:
            continue
        scheduled_for = campaign.next_run_at
        run = AutomationRun(automation_id=campaign.id, organization_id=campaign.organization_id, status="pending", run_key=f"scheduled:{scheduled_for.isoformat()}", scheduled_for=scheduled_for, started_at=now)
        try:
            # The unique scheduled_for invariant handles a race after a worker restart.
            with db.begin_nested():
                db.add(run)
                db.flush()
        except IntegrityError:
            continue
        store = db.get(Store, campaign.store_id)
        members = [member.customer_id for member in campaign.members if member.included]
        metrics = audience_metrics(db, campaign.organization_id, campaign.store_id, campaign.audience_type, json_load(campaign.audience_filters), members)
        run.matched_count = len(metrics)
        for customer in metrics:
            message = render_template(campaign.message_template, customer, store)
            if not customer.get("phone"):
                recipient = AutomationRecipientExecution(run_id=run.id, customer_id=customer["id"], status="skipped", exclusion_reason="no_phone")
                run.excluded_count += 1
            elif message is None:
                recipient = AutomationRecipientExecution(run_id=run.id, customer_id=customer["id"], status="skipped", exclusion_reason="invalid_template_data")
                run.excluded_count += 1
            else:
                recipient = AutomationRecipientExecution(run_id=run.id, customer_id=customer["id"], status="queued", rendered_message=message, next_attempt_at=now)
                run.eligible_count += 1
            db.add(recipient)
        campaign.last_run_at = now
        campaign.next_run_at = None if campaign.schedule_type == "once" else next_schedule_at(campaign, now)
        created += 1
    db.commit()
    return created


def reclaim_expired_leases(db: Session, now: datetime | None = None) -> None:
    now = now or utcnow()
    # No provider request started: safe to retry.
    db.query(AutomationRecipientExecution).filter(AutomationRecipientExecution.status == "processing", AutomationRecipientExecution.lease_expires_at < now).update({"status": "queued", "next_attempt_at": now, "claimed_at": None, "lease_expires_at": None}, synchronize_session=False)
    # A provider request may have been made: preserve at-most-once retry semantics.
    db.query(AutomationRecipientExecution).filter(AutomationRecipientExecution.status == "sending", AutomationRecipientExecution.lease_expires_at < now).update({"status": "ambiguous", "error_code": "lease_expired_sending", "error_message": "Worker stopped after provider request began", "lease_expires_at": None}, synchronize_session=False)
    db.commit()


def claim_recipients(db: Session, now: datetime | None = None, limit: int = BATCH_SIZE) -> list[int]:
    now = now or utcnow()
    query = db.query(AutomationRecipientExecution.id).join(AutomationRun).join(AutomationCampaign).filter(AutomationRecipientExecution.status.in_(("queued", "retry_wait")), AutomationRecipientExecution.next_attempt_at <= now, AutomationCampaign.status == "active")
    if db.bind and db.bind.dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    ids = [row[0] for row in query.order_by(AutomationRecipientExecution.id).limit(limit).all()]
    if ids:
        db.query(AutomationRecipientExecution).filter(AutomationRecipientExecution.id.in_(ids), AutomationRecipientExecution.status.in_(("queued", "retry_wait"))).update({"status": "processing", "claimed_at": now, "lease_expires_at": now + timedelta(seconds=LEASE_SECONDS)}, synchronize_session=False)
    db.commit()
    return ids


def _acquire_rate_slot(db: Session, connection_id: int, now: datetime) -> bool:
    window = now.replace(second=0, microsecond=0)
    row = db.query(AutomationRateLimit).filter(AutomationRateLimit.connection_id == connection_id, AutomationRateLimit.window_start == window).with_for_update().first()
    if row is None:
        row = AutomationRateLimit(connection_id=connection_id, window_start=window, sent_count=0)
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
        except IntegrityError:
            # Another PostgreSQL worker opened this bucket concurrently.
            row = db.query(AutomationRateLimit).filter(AutomationRateLimit.connection_id == connection_id, AutomationRateLimit.window_start == window).with_for_update().one()
    if row.sent_count >= MAX_PER_MINUTE:
        db.commit()
        return False
    row.sent_count += 1
    db.commit()
    return True


def _finish_attempt(db: Session, recipient: AutomationRecipientExecution, status: str, now: datetime, *, code: str | None = None, message: str | None = None, provider_id: str | None = None) -> None:
    recipient.status = status; recipient.error_code = code; recipient.error_message = message; recipient.provider_message_id = provider_id or recipient.provider_message_id; recipient.lease_expires_at = None
    if status == "sent":
        recipient.sent_at = now
    attempt = db.query(AutomationDeliveryAttempt).filter(AutomationDeliveryAttempt.recipient_execution_id == recipient.id, AutomationDeliveryAttempt.attempt_number == recipient.attempt_count).first()
    if attempt:
        attempt.status = status; attempt.error_code = code; attempt.error_message = message; attempt.provider_message_id = provider_id; attempt.finished_at = now
    db.commit()


def process_recipient(db: Session, recipient_id: int, now: datetime | None = None, sender=send_whatsapp_text_message) -> str:
    """Claim is already committed. This function never holds a DB transaction during HTTP I/O."""
    now = now or utcnow()
    recipient = db.get(AutomationRecipientExecution, recipient_id)
    if not recipient or recipient.status != "processing":
        return "not_claimed"
    run = db.get(AutomationRun, recipient.run_id)
    campaign = db.get(AutomationCampaign, run.automation_id)
    if campaign.status != "active":
        recipient.status = "queued"; recipient.next_attempt_at = now + timedelta(minutes=1); recipient.lease_expires_at = None; db.commit(); return "paused"
    zone = ZoneInfo(campaign.timezone)
    local_now = now.replace(tzinfo=timezone.utc).astimezone(zone)
    if campaign.send_window_start and campaign.send_window_end:
        clock = local_now.strftime("%H:%M")
        if not campaign.send_window_start <= clock < campaign.send_window_end:
            recipient.status = "queued"; recipient.next_attempt_at = next_schedule_at(campaign, now) if campaign.schedule_type != "once" else (now + timedelta(minutes=15)); recipient.lease_expires_at = None; db.commit(); return "outside_window"
    cooldown_cutoff = now - timedelta(days=campaign.cooldown_days)
    recent = db.query(AutomationRecipientExecution.id).join(AutomationRun).filter(AutomationRun.automation_id == campaign.id, AutomationRecipientExecution.customer_id == recipient.customer_id, AutomationRecipientExecution.status == "sent", AutomationRecipientExecution.sent_at >= cooldown_cutoff, AutomationRecipientExecution.id != recipient.id).first()
    if recent:
        _finish_attempt(db, recipient, "skipped", now, code="cooldown", message="Customer is within campaign cooldown")
        return "cooldown"
    connection = db.query(WhatsAppConnection).filter(WhatsAppConnection.store_id == campaign.store_id, WhatsAppConnection.organization_id == campaign.organization_id, WhatsAppConnection.status == "connected").first()
    if not connection:
        _finish_attempt(db, recipient, "failed", now, code="channel_unavailable", message="WhatsApp connection is unavailable")
        return "failed"
    if not _acquire_rate_slot(db, connection.id, now):
        recipient = db.get(AutomationRecipientExecution, recipient_id); recipient.status = "queued"; recipient.next_attempt_at = now.replace(second=0, microsecond=0) + timedelta(minutes=1); recipient.lease_expires_at = None; db.commit(); return "rate_limited"
    recipient.status = "sending"
    # Attempts count provider calls, never claims or local deferrals.
    recipient.attempt_count += 1
    db.add(AutomationDeliveryAttempt(recipient_execution_id=recipient.id, attempt_number=recipient.attempt_count, status="sending"))
    db.commit()
    customer = db.get(__import__("app.models", fromlist=["Customer"]).Customer, recipient.customer_id)
    try:
        result = sender(connection.phone_number_id, decrypt_whatsapp_secret(connection.access_token_encrypted), customer.phone, recipient.rendered_message or "")
    except WhatsAppDeliveryError as exc:
        recipient = db.get(AutomationRecipientExecution, recipient_id)
        if exc.category == "ambiguous":
            _finish_attempt(db, recipient, "ambiguous", now, code=exc.code, message=str(exc)); return "ambiguous"
        if exc.category == "transient" and recipient.attempt_count < MAX_ATTEMPTS:
            recipient.status = "retry_wait"; recipient.next_attempt_at = now + timedelta(seconds=BACKOFF_SECONDS[min(recipient.attempt_count - 1, len(BACKOFF_SECONDS) - 1)]); recipient.lease_expires_at = None; _finish_attempt(db, recipient, "retry_wait", now, code=exc.code, message=str(exc)); return "retry_wait"
        _finish_attempt(db, recipient, "failed", now, code=exc.code, message=str(exc)); return "failed"
    recipient = db.get(AutomationRecipientExecution, recipient_id)
    _finish_attempt(db, recipient, "sent", now, provider_id=result.get("message_id"))
    return "sent"


def aggregate_runs(db: Session, now: datetime | None = None) -> None:
    now = now or utcnow()
    for run in db.query(AutomationRun).filter(AutomationRun.status.in_(("pending", "running"))).all():
        states = [row[0] for row in db.query(AutomationRecipientExecution.status).filter(AutomationRecipientExecution.run_id == run.id).all()]
        if not states or not all(state in TERMINAL for state in states):
            run.status = "running"; continue
        run.sent_count = states.count("sent"); run.failed_count = states.count("failed") + states.count("ambiguous"); run.excluded_count = states.count("skipped")
        run.status = "completed" if run.failed_count == 0 else ("partial" if run.sent_count else "failed")
        run.completed_at = now
    db.commit()


def worker_cycle(db: Session, now: datetime | None = None, sender=send_whatsapp_text_message) -> int:
    now = now or utcnow()
    reclaim_expired_leases(db, now)
    materialize_due_campaigns(db, now)
    ids = claim_recipients(db, now)
    for recipient_id in ids:
        process_recipient(db, recipient_id, now, sender)
    aggregate_runs(db, now)
    return len(ids)
