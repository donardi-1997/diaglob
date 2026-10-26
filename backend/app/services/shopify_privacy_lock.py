"""Serialize enabled privacy execution with existing Shopify write gates."""
from __future__ import annotations

import hashlib
import os

from sqlalchemy import text
from sqlalchemy.orm import Session


def lock_shopify_privacy_scope(db: Session, organization_id: int, store_id: int) -> None:
    if os.getenv("SHOPIFY_PRIVACY_PROCESSING_ENABLED") != "true":
        return
    if db.get_bind().dialect.name == "postgresql":
        key = int.from_bytes(hashlib.sha256(
            f"diaglob.shopify.privacy:{organization_id}:{store_id}".encode(),
        ).digest()[:8], "big") & ((1 << 63) - 1)
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
