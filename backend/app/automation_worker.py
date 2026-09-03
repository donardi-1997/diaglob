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
    claims = claim_flow_recipients(db, include_tokens=True)
    from .automation_flow_engine import utcnow

    now = utcnow()
    processed = 0
    for rid, claim_token in claims:
        try:
            result = process_flow_recipient(db, rid, now, claim_token=claim_token)
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
