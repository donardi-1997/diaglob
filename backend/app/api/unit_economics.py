"""Store Unit Economics configuration endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..api.deps import get_db, require_permission
from ..services.unit_economics_config_service import (
    get_unit_economics_config,
    replace_unit_economics_config,
)


router = APIRouter()


class PaymentMethodCostRulePayload(BaseModel):
    payment_method: str
    fee_percent: float | None = None
    fee_fixed: float | None = None
    is_cod: bool = False
    cod_fee_percent: float | None = None


class UnitEconomicsConfigPayload(BaseModel):
    outbound_shipping_cost: float | None = None
    return_logistics_cost: float | None = None
    default_payment_fee_percent: float | None = None
    default_payment_fee_fixed: float | None = None
    default_cod_fee_percent: float | None = None
    payment_methods: list[PaymentMethodCostRulePayload] = Field(default_factory=list)


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
    try:
        return replace_unit_economics_config(
            db,
            membership.organization_id,
            store_id,
            payload.model_dump(),
        )
    except ValueError as exc:
        _raise_service_error(exc)
