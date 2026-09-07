"""Knowledge Base provisioning orchestration.

Background retry loop, thread-based scheduling, and startup reconciliation
for Bedrock/S3 Vectors provisioning.
"""

import logging
import threading
import time
from datetime import datetime, timezone

from sqlalchemy.exc import OperationalError

from ..bedrock_knowledge_base import (
    BedrockProvisioningError,
    ProvisioningErrorClassification,
    ProvisioningInProgressError,
    provision_diaglob_knowledge_base,
)
from ..db import SessionLocal
from ..models import KnowledgeBase

logger = logging.getLogger(__name__)

PROVISIONING_RETRY_DELAYS_SECONDS = (0, 60, 300, 900)


def run_knowledge_base_provisioning(knowledge_base_id: int) -> None:
    """Provision in the background so customers never wait on AWS setup."""
    for attempt, delay in enumerate(PROVISIONING_RETRY_DELAYS_SECONDS, start=1):
        if delay:
            time.sleep(delay)
        db = SessionLocal()
        try:
            knowledge_base = db.get(KnowledgeBase, knowledge_base_id)
            if not knowledge_base or knowledge_base.external_status == "ready":
                return
            try:
                provision_diaglob_knowledge_base(db, knowledge_base)
                logger.info(
                    "knowledge_base_provisioning_attempt_succeeded organization_id=%s knowledge_base_id=%s attempt=%s",
                    knowledge_base.organization_id, knowledge_base.id, attempt,
                )
                return
            except ProvisioningInProgressError:
                return
            except BedrockProvisioningError as error:
                retry_scheduled = (
                    error.classification in {
                        ProvisioningErrorClassification.RETRYABLE_INFRASTRUCTURE,
                        ProvisioningErrorClassification.PLATFORM_CONFIGURATION_ERROR,
                    }
                    and attempt < len(PROVISIONING_RETRY_DELAYS_SECONDS)
                )
                logger.error(
                    "knowledge_base_provisioning_attempt_failed organization_id=%s knowledge_base_id=%s attempt=%s stage=%s classification=%s retry_scheduled=%s",
                    knowledge_base.organization_id, knowledge_base.id, attempt,
                    error.resource, error.classification, retry_scheduled,
                )
                if retry_scheduled:
                    knowledge_base.external_status = "retrying"
                    knowledge_base.provisioning_stage = "retrying"
                    knowledge_base.provisioning_stage_started_at = datetime.now(timezone.utc)
                    db.commit()
                else:
                    return
        finally:
            db.close()


def schedule_knowledge_base_provisioning(knowledge_base_id: int) -> None:
    """Run startup recovery outside the request lifecycle."""
    threading.Thread(
        target=run_knowledge_base_provisioning,
        args=(knowledge_base_id,),
        daemon=True,
    ).start()


def reconcile_knowledge_base_provisioning() -> None:
    """Resume stranded non-terminal provisioning after a process restart."""
    db = SessionLocal()
    try:
        try:
            knowledge_bases = db.query(KnowledgeBase).filter(
                KnowledgeBase.active.is_(True),
                KnowledgeBase.external_status.in_(("pending", "provisioning", "retrying")),
            ).all()
        except OperationalError as error:
            db.rollback()
            if "no such column" in str(error).lower() and "knowledge_bases.external_status" in str(error):
                logger.warning("Skipping Knowledge Base provisioning reconciliation until migration 007 is applied")
                return
            raise
        now = datetime.now(timezone.utc)
        for knowledge_base in knowledge_bases:
            if knowledge_base.external_status == "provisioning":
                knowledge_base.external_status = "retrying"
                knowledge_base.provisioning_stage = "retrying"
                knowledge_base.provisioning_stage_started_at = now
        db.commit()
        for knowledge_base in knowledge_bases:
            logger.info(
                "Reconciling Knowledge Base provisioning: organization_id=%s knowledge_base_id=%s status=%s",
                knowledge_base.organization_id,
                knowledge_base.id,
                knowledge_base.external_status,
            )
            schedule_knowledge_base_provisioning(knowledge_base.id)
    finally:
        db.close()
