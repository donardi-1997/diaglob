import logging

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
from ..services.customer_audience_service import (
    list_classified_audience_customers,
)
from ..services.customer_classification_service import (
    get_customer_classifications,
)
from ..services.customer_risk_service import (
    enrich_customer_detail_response,
    enrich_customer_list_response,
)
from .deps import require_permission
from .store_access import ensure_membership_store_access

router = APIRouter()
logger = logging.getLogger(__name__)


def _validate_store(
    db: Session,
    membership: OrganizationMembership,
    store_id: int,
) -> Store:
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id == membership.organization_id,
            Store.deleted.is_(False),
            Store.active.is_(True),
        )
        .first()
    )
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    return ensure_membership_store_access(membership, store)


def _authorized_customer_store_id(
    db: Session,
    membership: OrganizationMembership,
    store_id: int | None,
) -> int | None:
    """Never allow store-restricted staff to read organization-wide PCD."""
    if store_id is not None:
        _validate_store(db, membership, store_id)
        return store_id
    if membership.all_stores:
        return None

    assigned = {
        store.id for store in membership.stores
        if (
            store.organization_id == membership.organization_id
            and store.active and not store.deleted
        )
    }
    if len(assigned) != 1:
        raise HTTPException(
            status_code=403,
            detail="Explicit authorized store is required",
        )
    return next(iter(assigned))


def _audit_customer_read(
    membership: OrganizationMembership, operation: str, store_id: int | None,
) -> None:
    """PII-free event for centralized access logging; retention not yet verified."""
    logger.info(
        "CUSTOMER_PCD_READ operation=%s user_id=%s organization_id=%s store_id=%s",
        operation, membership.user_id, membership.organization_id,
        store_id if store_id is not None else "all_authorized",
    )


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
    _validate_store(db, membership, store_id)
    result = get_customer_classifications(
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
    _audit_customer_read(membership, "classifications", store_id)
    return result


@router.get(
    "/api/stores/{store_id}/customers/audience"
)
def list_customer_audience(
    store_id: int,
    search: str | None = None,
    page: int = 1,
    page_size: int = 25,
    segment: str | None = None,
    priority: str | None = None,
    health: str | None = None,
    country: str | None = None,
    classification: str | None = None,
    value_tier: str | None = None,
    needs_attention: bool | None = None,
    has_orders: bool | None = None,
    sort: str = "priority_desc",
    membership: OrganizationMembership = Depends(
        require_permission("automations.read")
    ),
    db: Session = Depends(get_db),
):
    _validate_store(db, membership, store_id)
    result = list_classified_audience_customers(
        db=db,
        organization_id=membership.organization_id,
        store_id=store_id,
        search=search,
        segment=segment,
        priority=priority,
        health=health,
        country=country,
        classification=classification,
        value_tier=value_tier,
        needs_attention=needs_attention,
        has_orders=has_orders,
        page=max(1, page),
        page_size=min(max(1, page_size), 100),
        sort=sort,
    )
    _audit_customer_read(membership, "audience", store_id)
    return result


@router.get("/api/customers/summary")
def get_customers_summary(
    store_id: int | None = None,
    membership: OrganizationMembership = Depends(
        require_permission("customers.read")
    ),
    db: Session = Depends(get_db),
):
    from ..customers.intelligence import get_summary

    store_id = _authorized_customer_store_id(db, membership, store_id)

    result = get_summary(
        db=db,
        organization_id=membership.organization_id,
        store_id=store_id,
    )
    _audit_customer_read(membership, "summary", store_id)
    return result


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

    store_id = _authorized_customer_store_id(db, membership, store_id)

    page_size = min(max(1, page_size), 100)
    page = max(1, page)

    result = get_customer_list(
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
    _audit_customer_read(membership, "list", store_id)
    return enrich_customer_list_response(
        db=db,
        organization_id=membership.organization_id,
        response=result,
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

    store_id = _authorized_customer_store_id(db, membership, store_id)

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

    _audit_customer_read(membership, "detail", store_id)
    return enrich_customer_detail_response(
        db=db,
        organization_id=membership.organization_id,
        response=result,
    )
