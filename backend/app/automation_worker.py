"""Run the durable campaign worker: python -m app.automation_worker [--once]."""
import argparse
import logging
import signal
import time

from .automation_execution_engine import worker_cycle
from .db import SessionLocal

running = True

def _stop(*_args):
    global running
    running = False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=10)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    while running:
        db = SessionLocal()
        try:
            worker_cycle(db)
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
