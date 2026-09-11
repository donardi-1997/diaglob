from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..markets import get_market
from ..models import (
    Organization,
    OrganizationMembership,
    Store,
)
from ..plan_limits import get_organization_limits
from .deps import require_permission

router = APIRouter()


class StoreCreate(BaseModel):
    name: str
    country_code: str
    currency: str | None = None
    timezone: str | None = None
    default_language: str | None = None
    shopify_domain: str | None = None
    active: bool = True


class StoreUpdate(BaseModel):
    name: str | None = None
    currency: str | None = None
    timezone: str | None = None
    default_language: str | None = None
    shopify_domain: str | None = None
    active: bool | None = None


def _slugify_store_name(
    value: str,
):
    import re
    import unicodedata

    normalized = (
        unicodedata.normalize(
            "NFKD",
            value,
        )
        .encode(
            "ascii",
            "ignore",
        )
        .decode(
            "ascii"
        )
        .lower()
    )

    slug = re.sub(
        r"[^a-z0-9]+",
        "-",
        normalized,
    ).strip("-")

    return slug or "store"


def get_active_store_usage(
    db: Session,
    organization_id: int,
):
    return (
        db.query(Store)
        .filter(
            Store.organization_id
            == organization_id,
            Store.deleted.is_(False),
            Store.active.is_(True),
        )
        .count()
    )


def ensure_active_store_capacity(
    db: Session,
    organization_id: int,
):
    organization = (
        db.query(Organization)
        .filter(
            Organization.id
            == organization_id
        )
        .first()
    )

    if not organization:
        raise HTTPException(
            status_code=404,
            detail="Organization not found",
        )

    if organization.subscription_status in {
        "past_due",
        "paused",
        "canceled",
    }:
        raise HTTPException(
            status_code=409,
            detail=(
                "Tu suscripción no está activa. "
                "Actualiza tu método de pago o "
                "renueva tu plan para activar tiendas."
            ),
        )

    limits = get_organization_limits(
        organization
    )

    active_stores = (
        get_active_store_usage(
            db,
            organization_id,
        )
    )

    limit = limits.active_stores

    if active_stores >= limit:
        plan_name = (
            (organization.plan or "none")
            .strip()
            .lower()
            .capitalize()
        )

        store_word = (
            "tienda activa"
            if limit == 1
            else "tiendas activas"
        )

        current_word = (
            "tienda activa"
            if active_stores == 1
            else "tiendas activas"
        )

        raise HTTPException(
            status_code=409,
            detail={
                "code":
                    "ACTIVE_STORE_LIMIT_REACHED",

                "message":
                    (
                        f"Tu plan {plan_name} "
                        f"permite hasta {limit} "
                        f"{store_word}. "
                        f"Actualmente tienes "
                        f"{active_stores} "
                        f"{current_word}. "
                        "Elimina una tienda o mejora "
                        "tu plan para agregar otra."
                    ),

                "resource":
                    "active_stores",

                "used":
                    active_stores,

                "limit":
                    limit,

                "remaining":
                    max(
                        limit - active_stores,
                        0,
                    ),
            },
        )


@router.get("/api/stores")
def list_stores(
    include_suspended: bool = False,
    membership: OrganizationMembership = Depends(
        require_permission("stores.read")
    ),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Store)
        .filter(
            Store.organization_id
            == membership.organization_id,

            Store.deleted.is_(False),
        )
    )

    if not include_suspended:
        query = query.filter(
            Store.active.is_(True)
        )

    if not membership.all_stores:
        allowed_ids = [
            store.id
            for store in membership.stores
            if not store.deleted
        ]

        if not allowed_ids:
            stores = []
        else:
            stores = (
                query
                .filter(
                    Store.id.in_(
                        allowed_ids
                    )
                )
                .order_by(
                    Store.name.asc()
                )
                .all()
            )
    else:
        stores = (
            query
            .order_by(
                Store.name.asc()
            )
            .all()
        )

    return {
        "items": [
            {
                "id": store.id,
                "name": store.name,
                "slug": store.slug,
                "country_code": store.country_code,
                "currency": store.currency,
                "timezone": store.timezone,
                "default_language": store.default_language,
                "shopify_domain": store.shopify_domain,
                "active": store.active,
            }
            for store in stores
        ],
        "total": len(stores),
    }


@router.post("/api/stores")
def create_store(
    payload: StoreCreate,
    membership: OrganizationMembership = Depends(
        require_permission(
            "stores.write"
        )
    ),
    db: Session = Depends(get_db),
):
    name = payload.name.strip()

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Store name is required",
        )

    country_code = (
        payload.country_code
        .strip()
        .upper()
    )

    market = get_market(
        country_code
    )

    if not market:
        raise HTTPException(
            status_code=400,
            detail="Unsupported market",
        )

    currency = (
        payload.currency
        or market["currency"]
    ).strip().upper()

    supported_currencies = (
        market.get(
            "supported_currencies"
        )
        or [
            market["currency"]
        ]
    )

    if (
        currency
        not in supported_currencies
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Currency is not supported "
                "for this market"
            ),
        )

    timezone = (
        payload.timezone
        or market[
            "default_timezone"
        ]
    ).strip()

    default_language = (
        payload.default_language
        or market[
            "default_language"
        ]
    ).strip().lower()

    base_slug = (
        _slugify_store_name(
            name
        )
    )

    slug = base_slug
    suffix = 2

    while (
        db.query(Store)
        .filter(
            Store.organization_id
            == membership.organization_id,

            Store.slug
            == slug,
        )
        .first()
        is not None
    ):
        slug = (
            f"{base_slug}-{suffix}"
        )

        suffix += 1

    shopify_domain = (
        payload.shopify_domain.strip()
        if payload.shopify_domain
        else None
    )

    if payload.active:
        ensure_active_store_capacity(
            db,
            membership.organization_id,
        )

    store = Store(
        organization_id=
            membership.organization_id,

        name=
            name,

        slug=
            slug,

        country_code=
            country_code,

        currency=
            currency,

        timezone=
            timezone,

        default_language=
            default_language,

        shopify_domain=
            shopify_domain,

        active=
            payload.active,
    )

    db.add(store)

    db.flush()

    if not membership.all_stores:
        membership.stores.append(store)

    db.commit()
    db.refresh(store)

    # Analytics: store created
    from ..services.product_analytics import track_store_created
    track_store_created(
        user_id=membership.user_id,
        organization_id=membership.organization_id,
        store_id=store.id,
        country=country_code,
        currency=currency,
    )

    return {
        "id":
            store.id,

        "name":
            store.name,

        "slug":
            store.slug,

        "country_code":
            store.country_code,

        "currency":
            store.currency,

        "timezone":
            store.timezone,

        "default_language":
            store.default_language,

        "shopify_domain":
            store.shopify_domain,

        "active":
            store.active,
    }


@router.patch("/api/stores/{store_id}")
def update_store(
    store_id: int,
    payload: StoreUpdate,
    membership: OrganizationMembership = Depends(
        require_permission(
            "stores.write"
        )
    ),
    db: Session = Depends(get_db),
):
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,

            Store.organization_id
            == membership.organization_id,

            Store.deleted.is_(False),
        )
        .first()
    )

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found",
        )

    if payload.name is not None:
        name = (
            payload.name
            .strip()
        )

        if not name:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Store name is required"
                ),
            )

        store.name = name

    if payload.currency is not None:
        currency = (
            payload.currency
            .strip()
            .upper()
        )

        market = get_market(
            store.country_code
        )

        if market:
            supported_currencies = (
                market.get(
                    "supported_currencies"
                )
                or [
                    market["currency"]
                ]
            )

            if (
                currency
                not in supported_currencies
            ):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Currency is not supported "
                        "for this market"
                    ),
                )

        store.currency = currency

    if payload.timezone is not None:
        timezone = (
            payload.timezone
            .strip()
        )

        if not timezone:
            raise HTTPException(
                status_code=400,
                detail="Timezone is required",
            )

        store.timezone = timezone

    if (
        payload.default_language
        is not None
    ):
        language = (
            payload.default_language
            .strip()
            .lower()
        )

        if not language:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Default language "
                    "is required"
                ),
            )

        store.default_language = (
            language
        )

    if (
        payload.shopify_domain
        is not None
    ):
        store.shopify_domain = (
            payload.shopify_domain
            .strip()
            or None
        )

    if payload.active is not None:
        if (
            payload.active
            and not store.active
        ):
            ensure_active_store_capacity(
                db,
                membership.organization_id,
            )

        store.active = payload.active

    db.commit()
    db.refresh(store)

    return {
        "id":
            store.id,

        "name":
            store.name,

        "slug":
            store.slug,

        "country_code":
            store.country_code,

        "currency":
            store.currency,

        "timezone":
            store.timezone,

        "default_language":
            store.default_language,

        "shopify_domain":
            store.shopify_domain,

        "active":
            store.active,
    }


@router.delete("/api/stores/{store_id}")
def delete_store(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "stores.write"
        )
    ),
    db: Session = Depends(get_db),
):
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found",
        )

    if store.deleted:
        return {
            "deleted": True,
            "store_id": store.id,
            "already_deleted": True,
        }

    store.active = False
    store.deleted = True

    db.commit()
    db.refresh(store)

    return {
        "deleted": True,
        "store_id": store.id,
        "name": store.name,
        "active": store.active,
    }
