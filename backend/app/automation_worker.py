"""Run the durable automation worker: python -m app.automation_worker [--once] [--mode campaigns|flows|both]."""
import argparse
import logging
import signal
import time

from .automation_execution_engine import worker_cycle
from .automation_flow_engine import claim_flow_recipients, reclaim_expired_flow_leases, process_flow_recipient, aggregate_flow_runs
from .db import SessionLocal

running = True

def _stop(*_args):
    global running
    running = False


def _flow_worker_cycle(db):
    """Process one cycle of flow recipient executions."""
    reclaim_expired_flow_leases(db)
    claim_flow_recipients(db)
    import uuid
    from datetime import timedelta
    from .automation_flow_engine import LEASE_SECONDS
    from .models import AutomationFlowRecipientExecution
    from .automation_flow_engine import utcnow

    now = utcnow()
    claim_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    recipient_ids = db.query(AutomationFlowRecipientExecution.id).filter(
        AutomationFlowRecipientExecution.status == "active",
        AutomationFlowRecipientExecution.next_action_at <= now,
    ).order_by(AutomationFlowRecipientExecution.id).limit(50).with_for_update(skip_locked=True).all()
    db.query(AutomationFlowRecipientExecution).filter(
        AutomationFlowRecipientExecution.id.in_([r[0] for r in recipient_ids])
    ).update({
        "status": "waiting",
        "claim_token": str(uuid.uuid4()),
        "claim_expires_at": claim_expires_at,
    }, synchronize_session=False)
    db.commit()

    processed = 0
    for (rid,) in recipient_ids:
        try:
            result = process_flow_recipient(db, rid, now)
            processed += 1
        except Exception:
            logging.exception("flow recipient %d failed", rid)
            db.rollback()
    aggregate_flow_runs(db)
    return processed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--mode", choices=["campaigns", "flows", "both"], default="both")
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    while running:
        db = SessionLocal()
        try:
            if args.mode in ("campaigns", "both"):
                worker_cycle(db)
            if args.mode in ("flows", "both"):
                _flow_worker_cycle(db)
        except Exception:
            logging.exception("automation worker cycle failed")
            db.rollback()
        finally:
            db.close()
        if args.once:
            return
        time.sleep(max(1, args.poll_seconds))

if __name__ == "__main__":
    main()
