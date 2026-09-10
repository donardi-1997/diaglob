"""AI usage and purchasable response-package API."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import OrganizationMembership
from ..paddle_client import PaddleConfigError, PaddleProviderError
from ..services.ai_usage_packages import (
    AiUsagePackageUnavailableError,
    InvalidAiUsagePackageError,
    create_ai_usage_package_checkout,
    serialize_ai_usage_packages,
)
from ..services.ai_usage_service import get_ai_usage
from .deps import get_current_membership


router = APIRouter()


class AiUsagePackageCheckoutRequest(BaseModel):
    package_key: str


@router.get("/api/billing/ai-packages")
def list_ai_usage_packages(
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    return {
        "packages": serialize_ai_usage_packages(),
        "usage": get_ai_usage(db, membership.organization_id),
    }


@router.post("/api/billing/ai-packages/checkout")
def checkout_ai_usage_package(
    payload: AiUsagePackageCheckoutRequest,
    membership: OrganizationMembership = Depends(get_current_membership),
):
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")

    organization = membership.organization
    plan = (organization.plan or "none").strip().lower()
    status = (organization.subscription_status or "").strip().lower()

    if plan not in {"starter", "growth", "pro", "scale"}:
        raise HTTPException(
            status_code=409,
            detail="Necesitas un plan activo para comprar respuestas de IA extra.",
        )

    if status not in {"active", "trialing"}:
        raise HTTPException(
            status_code=409,
            detail="La suscripción debe estar activa para comprar respuestas de IA extra.",
        )

    try:
        return create_ai_usage_package_checkout(
            organization_id=organization.id,
            package_key=payload.package_key,
        )
    except InvalidAiUsagePackageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AiUsagePackageUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PaddleConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PaddleProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
