from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    OrganizationMembership,
    Store,
)
from ..services.customer_classification_service import (
    get_customer_classifications,
)
from .deps import require_permission

router = APIRouter()


def _validate_store(
    db: Session,
    organization_id: int,
    store_id: int,
) -> Store:
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id == organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )
    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found",
        )
    return store


@router.get(
    "/api/stores/{store_id}/customers/classifications"
)
def list_customer_classifications(
    store_id: int,
    classification: str | None = None,
    value_tier: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 25,
    sort: str = "value_desc",
    membership: OrganizationMembership = Depends(
        require_permission("customers.read")
    ),
    db: Session = Depends(get_db),
):
    _validate_store(
        db,
        membership.organization_id,
        store_id,
    )
    return get_customer_classifications(
        db=db,
        organization_id=membership.organization_id,
        store_id=store_id,
        classification=classification,
        value_tier=value_tier,
        search=search,
        page=max(1, page),
        page_size=min(max(1, page_size), 100),
        sort=sort,
    )


@router.get("/api/customers/summary")
def get_customers_summary(
    store_id: int | None = None,
    membership: OrganizationMembership = Depends(
        require_permission("customers.read")
    ),
    db: Session = Depends(get_db),
):
    from ..customers.intelligence import get_summary

    if store_id is not None:
        _validate_store(
            db,
            membership.organization_id,
            store_id,
        )

    return get_summary(
        db=db,
        organization_id=membership.organization_id,
        store_id=store_id,
    )


@router.get("/api/customers")
def list_customers(
    store_id: int | None = None,
    segment: str | None = None,
    flag: str | None = None,
    search: str | None = None,
    has_orders: bool | None = None,
    page: int = 1,
    page_size: int = 25,
    sort: str = "last_interaction_desc",
    priority: str | None = None,
    health: str | None = None,
    needs_attention: bool | None = None,
    membership: OrganizationMembership = Depends(
        require_permission("customers.read")
    ),
    db: Session = Depends(get_db),
):
    from ..customers.intelligence import get_customer_list

    if store_id is not None:
        _validate_store(
            db,
            membership.organization_id,
            store_id,
        )

    page_size = min(max(1, page_size), 100)
    page = max(1, page)

    return get_customer_list(
        db=db,
        organization_id=membership.organization_id,
        store_id=store_id,
        segment=segment,
        flag=flag,
        search=search,
        has_orders=has_orders,
        page=page,
        page_size=page_size,
        sort=sort,
        priority=priority,
        health=health,
        needs_attention=needs_attention,
    )


@router.get("/api/customers/{customer_id}")
def get_customer_detail(
    customer_id: int,
    store_id: int | None = None,
    membership: OrganizationMembership = Depends(
        require_permission("customers.read")
    ),
    db: Session = Depends(get_db),
):
    from ..customers.intelligence import (
        get_customer_detail,
    )

    if store_id is not None:
        _validate_store(
            db,
            membership.organization_id,
            store_id,
        )

    result = get_customer_detail(
        db=db,
        organization_id=membership.organization_id,
        customer_id=customer_id,
        store_id=store_id,
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Customer not found",
        )

    return result
