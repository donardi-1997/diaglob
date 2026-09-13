"""Store Unit Economics configuration endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StrictBool
from sqlalchemy.orm import Session

from ..api.deps import get_db, require_permission
from ..models import Store
from ..services.unit_economics_config_service import (
    get_unit_economics_config,
    replace_unit_economics_config,
)
from .store_access import ensure_membership_store_access


router = APIRouter()


class PaymentMethodCostRulePayload(BaseModel):
    payment_method: str = Field(min_length=1, max_length=50)
    fee_percent: float | None = Field(default=None, ge=0, le=100)
    fee_fixed: float | None = Field(default=None, ge=0)
    is_cod: StrictBool = False
    cod_fee_percent: float | None = Field(default=None, ge=0, le=100)


class UnitEconomicsConfigPayload(BaseModel):
    outbound_shipping_cost: float | None = Field(default=None, ge=0)
    return_logistics_cost: float | None = Field(default=None, ge=0)
    default_payment_fee_percent: float | None = Field(default=None, ge=0, le=100)
    default_payment_fee_fixed: float | None = Field(default=None, ge=0)
    default_cod_fee_percent: float | None = Field(default=None, ge=0, le=100)
    payment_methods: list[PaymentMethodCostRulePayload] = Field(default_factory=list)


def _validate_config_store(
    store_id: int,
    membership,
    db: Session,
) -> Store:
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id == membership.organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )
    if store is None:
        raise HTTPException(status_code=404, detail="store_not_found")
    return ensure_membership_store_access(membership, store)


def _raise_service_error(exc: ValueError) -> None:
    detail = str(exc)
    if detail == "store_not_found":
        raise HTTPException(status_code=404, detail=detail) from exc
    raise HTTPException(status_code=400, detail=detail) from exc


@router.get("/api/stores/{store_id}/unit-economics/config")
def read_unit_economics_config(
    store_id: int,
    membership=Depends(require_permission("stores.read")),
    db: Session = Depends(get_db),
):
    _validate_config_store(store_id, membership, db)
    try:
        return get_unit_economics_config(
            db,
            membership.organization_id,
            store_id,
        )
    except ValueError as exc:
        _raise_service_error(exc)


@router.put("/api/stores/{store_id}/unit-economics/config")
def write_unit_economics_config(
    store_id: int,
    payload: UnitEconomicsConfigPayload,
    membership=Depends(require_permission("stores.write")),
    db: Session = Depends(get_db),
):
    _validate_config_store(store_id, membership, db)
    try:
        return replace_unit_economics_config(
            db,
            membership.organization_id,
            store_id,
            payload.model_dump(),
        )
    except ValueError as exc:
        _raise_service_error(exc)
