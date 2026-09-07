from fastapi import (
    Depends,
    Header,
    HTTPException,
    Request,
)
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from sqlalchemy.orm import Session

from ..auth import verify_cognito_access_token
from ..db import get_db
from ..models import (
    Organization,
    OrganizationMembership,
    Store,
    User,
)
from ..permissions import has_permission


bearer_scheme = HTTPBearer(
    auto_error=False,
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials
    | None = Depends(
        bearer_scheme
    ),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )

    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication scheme",
        )

    payload = verify_cognito_access_token(
        credentials.credentials
    )

    cognito_sub = payload["sub"]

    user = (
        db.query(User)
        .filter(
            User.external_auth_id
            == cognito_sub,
            User.active.is_(True),
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Diaglob user not found",
        )

    return user


def get_current_membership(
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    memberships = (
        db.query(OrganizationMembership)
        .join(Organization)
        .filter(
            OrganizationMembership.user_id
            == user.id,
            OrganizationMembership.active.is_(True),
            Organization.active.is_(True),
        )
        .all()
    )

    if not memberships:
        raise HTTPException(
            status_code=403,
            detail="Organization access denied",
        )

    if len(memberships) > 1:
        raise HTTPException(
            status_code=409,
            detail=(
                "User has more than one active "
                "organization membership"
            ),
        )

    return memberships[0]


def require_permission(
    permission: str,
):
    def dependency(
        request: Request,
        membership: OrganizationMembership = Depends(
            get_current_membership
        ),
    ):
        if not has_permission(
            membership.role,
            permission,
        ):
            raise HTTPException(
                status_code=403,
                detail="Permission denied",
            )

        method = request.method.upper()

        write_request = method not in {
            "GET",
            "HEAD",
            "OPTIONS",
        }

        billing_exception = (
            permission == "billing.write"
        )

        if (
            write_request
            and not billing_exception
        ):
            organization = (
                membership.organization
            )

            plan = (
                organization.plan
                or "none"
            ).strip().lower()

            subscription_status = (
                organization.subscription_status
                or ""
            ).strip().lower()

            active_plan = (
                plan in {
                    "starter",
                    "growth",
                    "pro",
                    "scale",
                }
                and subscription_status in {
                    "active",
                    "trialing",
                }
            )

            if not active_plan:
                raise HTTPException(
                    status_code=402,
                    detail={
                        "code": "PLAN_REQUIRED",
                        "message": (
                            "No tienes un plan activo. "
                            "Elige un plan para utilizar "
                            "esta función."
                        ),
                    },
                )

        return membership

    return dependency


def get_current_organization(
    membership: OrganizationMembership = Depends(
        get_current_membership
    ),
):
    return membership.organization


def get_store_scope(
    membership: OrganizationMembership = Depends(
        get_current_membership
    ),
    x_store_id: int | None = Header(
        None,
        alias="X-Store-Id",
    ),
    db: Session = Depends(get_db),
):
    if x_store_id is None:
        return None

    store = (
        db.query(Store)
        .filter(
            Store.id == x_store_id,
            Store.organization_id
            == membership.organization_id,
            Store.active.is_(True),
        )
        .first()
    )

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found",
        )

    if membership.all_stores:
        return store

    allowed_store_ids = {
        allowed_store.id
        for allowed_store in membership.stores
    }

    if store.id not in allowed_store_ids:
        raise HTTPException(
            status_code=403,
            detail="Store access denied",
        )

    return store


def serialize_store_short(
    store: Store,
):
    return {
        "id": store.id,
        "name": store.name,
        "country_code": store.country_code,
        "currency": store.currency,
    }
