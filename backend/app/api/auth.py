import os
from datetime import datetime, timedelta, timezone

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from fastapi.security import (
    HTTPAuthorizationCredentials,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import verify_cognito_access_token
from ..db import get_db
from ..models import (
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
    User,
)
from ..permissions import get_permissions_for_role
from ..services.trial_service import create_pending_trial
from .deps import (
    bearer_scheme,
    get_current_user,
)


class RegistrationProvisionRequest(BaseModel):
    name: str
    organization_name: str | None = None


router = APIRouter()


@router.post("/api/register/provision")
def provision_registration(
    payload: RegistrationProvisionRequest,
    credentials: HTTPAuthorizationCredentials
    | None = Depends(
        bearer_scheme
    ),
    db: Session = Depends(get_db),
):
    import boto3
    import os
    import re
    import unicodedata

    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )

    if (
        credentials.scheme.lower()
        != "bearer"
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication scheme",
        )

    token = credentials.credentials

    token_payload = (
        verify_cognito_access_token(
            token
        )
    )

    cognito_sub = token_payload["sub"]

    region = (
        os.getenv(
            "AWS_REGION"
        )
        or os.getenv(
            "AWS_DEFAULT_REGION"
        )
        or "us-east-2"
    )

    cognito = boto3.client(
        "cognito-idp",
        region_name=region,
    )

    try:
        cognito_user = (
            cognito.get_user(
                AccessToken=token
            )
        )
    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail=(
                "Unable to read "
                "Cognito user"
            ),
        ) from exc

    attributes = {
        item["Name"]: item["Value"]
        for item
        in cognito_user.get(
            "UserAttributes",
            [],
        )
    }

    email = (
        attributes.get(
            "email",
            "",
        )
        .strip()
        .lower()
    )

    email_verified = (
        attributes.get(
            "email_verified",
            "false",
        )
        .lower()
        == "true"
    )

    if not email:
        raise HTTPException(
            status_code=400,
            detail=(
                "Cognito account "
                "has no email"
            ),
        )

    if not email_verified:
        raise HTTPException(
            status_code=400,
            detail=(
                "Email must be verified"
            ),
        )

    name = payload.name.strip()

    organization_name = (
        (payload.organization_name or "")
        .strip()
    )

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Name is required",
        )

    if len(name) > 150:
        raise HTTPException(
            status_code=400,
            detail="Name is too long",
        )

    if len(organization_name) > 150:
        raise HTTPException(
            status_code=400,
            detail=(
                "Organization name "
                "is too long"
            ),
        )

    # ========================================================
    # IDEMPOTENCY
    # ========================================================

    existing_user = (
        db.query(User)
        .filter(
            User.external_auth_id
            == cognito_sub
        )
        .first()
    )

    if existing_user:
        membership = (
            db.query(
                OrganizationMembership
            )
            .filter(
                OrganizationMembership.user_id
                == existing_user.id,

                OrganizationMembership.active
                .is_(True),
            )
            .first()
        )

        if membership:
            organization = (
                db.query(Organization)
                .filter(
                    Organization.id
                    == membership.organization_id
                )
                .first()
            )

            return {
                "created": False,
                "user": {
                    "id":
                        existing_user.id,
                    "name":
                        existing_user.name,
                    "email":
                        existing_user.email,
                },
                "organization": {
                    "id":
                        organization.id,
                    "name":
                        organization.name,
                    "slug":
                        organization.slug,
                },
                "role":
                    membership.role,
            }

    email_user = (
        db.query(User)
        .filter(
            User.email == email
        )
        .first()
    )

    if (
        email_user
        and email_user.external_auth_id
        is not None
        and email_user.external_auth_id
        != cognito_sub
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Email is already linked "
                "to another account"
            ),
        )

    # ========================================================
    # PENDING ORGANIZATION INVITATION
    # ========================================================

    now = datetime.utcnow()

    invitation = (
        db.query(OrganizationInvitation)
        .filter(
            OrganizationInvitation.email
            == email,

            OrganizationInvitation.status
            == "pending",
        )
        .order_by(
            OrganizationInvitation.created_at.desc()
        )
        .first()
    )

    if invitation:
        # ----------------------------------------------------
        # EXPIRATION
        # ----------------------------------------------------

        if invitation.expires_at <= now:
            invitation.status = "expired"
            db.commit()

            invitation = None

        else:
            # ------------------------------------------------
            # ACCOUNT MUST NOT BELONG TO ANOTHER ACTIVE ORG
            # ------------------------------------------------

            if email_user:
                other_active_membership = (
                    db.query(OrganizationMembership)
                    .filter(
                        OrganizationMembership.user_id
                        == email_user.id,

                        OrganizationMembership.active
                        .is_(True),

                        OrganizationMembership.organization_id
                        != invitation.organization_id,
                    )
                    .first()
                )

                if other_active_membership:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code":
                                "USER_ALREADY_HAS_ORGANIZATION",

                            "message":
                                (
                                    "Esta cuenta ya pertenece "
                                    "a otra organización activa."
                                ),
                        },
                    )

            # ------------------------------------------------
            # MEMBER CAPACITY
            # ------------------------------------------------

            _ensure_member_capacity(
                db,
                invitation.organization_id,
            )

            try:
                # --------------------------------------------
                # CREATE / LINK USER
                # --------------------------------------------

                if email_user:
                    user = email_user

                    user.external_auth_id = (
                        cognito_sub
                    )

                    user.name = name
                    user.active = True

                else:
                    user = User(
                        email=email,
                        name=name,
                        external_auth_id=
                            cognito_sub,
                        active=True,
                    )

                    db.add(user)
                    db.flush()

                # --------------------------------------------
                # EXISTING INACTIVE MEMBERSHIP?
                # --------------------------------------------

                invited_membership = (
                    db.query(
                        OrganizationMembership
                    )
                    .filter(
                        OrganizationMembership.user_id
                        == user.id,

                        OrganizationMembership.organization_id
                        == invitation.organization_id,
                    )
                    .first()
                )

                if invited_membership:
                    if invited_membership.active:
                        raise HTTPException(
                            status_code=409,
                            detail={
                                "code":
                                    "MEMBER_ALREADY_EXISTS",

                                "message":
                                    (
                                        "Ya eres miembro activo "
                                        "de esta organización."
                                    ),
                            },
                        )

                    invited_membership.role = (
                        invitation.role
                    )

                    invited_membership.all_stores = (
                        invitation.all_stores
                    )

                    invited_membership.stores = (
                        []
                        if invitation.all_stores
                        else list(
                            invitation.stores
                        )
                    )

                    invited_membership.active = True

                else:
                    invited_membership = (
                        OrganizationMembership(
                            user_id=user.id,

                            organization_id=
                                invitation.organization_id,

                            role=
                                invitation.role,

                            all_stores=
                                invitation.all_stores,

                            active=True,
                        )
                    )

                    invited_membership.stores = (
                        []
                        if invitation.all_stores
                        else list(
                            invitation.stores
                        )
                    )

                    db.add(
                        invited_membership
                    )

                invitation.status = "accepted"
                invitation.accepted_at = now

                db.commit()

                db.refresh(user)
                db.refresh(invited_membership)
                db.refresh(invitation)

                invited_organization = (
                    db.query(Organization)
                    .filter(
                        Organization.id
                        == invitation.organization_id
                    )
                    .first()
                )

            except HTTPException:
                db.rollback()
                raise

            except Exception:
                db.rollback()
                raise

            return {
                "created":
                    True,

                "invitation_accepted":
                    True,

                "user": {
                    "id":
                        user.id,

                    "name":
                        user.name,

                    "email":
                        user.email,
                },

                "organization": {
                    "id":
                        invited_organization.id,

                    "name":
                        invited_organization.name,

                    "slug":
                        invited_organization.slug,
                },

                "role":
                    invited_membership.role,
            }

    # ========================================================
    # NORMAL REGISTRATION REQUIRES ORGANIZATION NAME
    # ========================================================

    if not organization_name:
        raise HTTPException(
            status_code=400,
            detail={
                "code":
                    "ORGANIZATION_NAME_REQUIRED",

                "message":
                    (
                        "El nombre de la organización "
                        "es obligatorio."
                    ),
            },
        )

    # ========================================================
    # ORGANIZATION SLUG
    # ========================================================

    normalized = (
        unicodedata.normalize(
            "NFKD",
            organization_name,
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

    base_slug = re.sub(
        r"[^a-z0-9]+",
        "-",
        normalized,
    ).strip("-")

    if not base_slug:
        base_slug = "organization"

    slug = base_slug
    suffix = 2

    while (
        db.query(Organization)
        .filter(
            Organization.slug
            == slug
        )
        .first()
        is not None
    ):
        slug = (
            f"{base_slug}-{suffix}"
        )

        suffix += 1

    # ========================================================
    # CREATE DIAGLOB ACCOUNT
    # ========================================================

    try:
        if email_user:
            user = email_user

            user.external_auth_id = (
                cognito_sub
            )

            user.name = name
            user.active = True

        else:
            user = User(
                email=email,
                name=name,
                external_auth_id=
                    cognito_sub,
                active=True,
            )

            db.add(user)
            db.flush()

        organization = Organization(
            name=organization_name,
            slug=slug,
            active=True,
        )

        db.add(organization)
        db.flush()

        create_pending_trial(
            db,
            organization,
            now=datetime.utcnow(),
        )

        membership = (
            OrganizationMembership(
                user_id=user.id,
                organization_id=
                    organization.id,

                role="owner",
                all_stores=True,
                active=True,
            )
        )

        db.add(membership)

        db.commit()

        db.refresh(user)
        db.refresh(organization)
        db.refresh(membership)

    except Exception:
        db.rollback()
        raise

    # Analytics: signup completed
    from ..services.product_analytics import track_signup_completed
    track_signup_completed(
        user_id=user.id,
        organization_id=organization.id,
        role=membership.role,
    )

    return {
        "created": True,

        "user": {
            "id":
                user.id,
            "name":
                user.name,
            "email":
                user.email,
        },

        "organization": {
            "id":
                organization.id,
            "name":
                organization.name,
            "slug":
                organization.slug,
        },

        "role":
            membership.role,
    }


@router.get("/api/me")
def get_me(
    user: User = Depends(
        get_current_user
    ),
):
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "active": user.active,
    }


@router.delete("/api/account")
def close_account(
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    memberships = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id
            == user.id,
            OrganizationMembership.active.is_(True),
        )
        .all()
    )

    is_owner_in_any = any(
        m.role == "owner" for m in memberships
    )

    if is_owner_in_any:
        for m in memberships:
            if m.role == "owner":
                other_members = (
                    db.query(OrganizationMembership)
                    .filter(
                        OrganizationMembership.organization_id
                        == m.organization_id,
                        OrganizationMembership.active.is_(True),
                        OrganizationMembership.user_id
                        != user.id,
                    )
                    .count()
                )
                if other_members > 0:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "OWNER_HAS_MEMBERS",
                            "message": (
                                "Cannot close account: you are the owner of an organization "
                                "with other members. Transfer ownership or remove all members first."
                            ),
                        },
                    )

    for m in memberships:
        m.active = False

    user.active = False

    db.commit()

    import boto3
    from app.auth import COGNITO_USER_POOL_ID

    try:
        region = (
            os.getenv("AWS_REGION")
            or os.getenv("AWS_DEFAULT_REGION")
            or "us-east-2"
        )
        cognito = boto3.client(
            "cognito-idp",
            region_name=region,
        )
        cognito.admin_delete_user(
            UserPoolId=COGNITO_USER_POOL_ID,
            Username=user.email,
        )
    except Exception:
        pass

    return {"detail": "Account closed successfully"}


@router.get("/api/me/organizations")
def get_my_organizations(
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
        .order_by(
            Organization.name.asc()
        )
        .all()
    )

    return {
        "items": [
            {
                "id": membership.organization.id,
                "name": membership.organization.name,
                "slug": membership.organization.slug,
                "role": membership.role,
                "all_stores": membership.all_stores,
                "permissions": get_permissions_for_role(
                    membership.role
                ),
            }
            for membership in memberships
        ],
        "total": len(memberships),
    }


def _get_active_member_usage(
    db: Session,
    organization_id: int,
):
    return (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id
            == organization_id,
            OrganizationMembership.active.is_(True),
        )
        .count()
    )


def _ensure_member_capacity(
    db: Session,
    organization_id: int,
):
    from ..plan_limits import get_organization_limits

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

    limits = get_organization_limits(
        organization
    )

    active_members = (
        _get_active_member_usage(
            db,
            organization_id,
        )
    )

    limit = limits.members

    if active_members >= limit:
        plan_name = (
            (organization.plan or "none")
            .strip()
            .lower()
            .capitalize()
        )

        raise HTTPException(
            status_code=409,
            detail={
                "code":
                    "MEMBER_LIMIT_REACHED",

                "message":
                    (
                        f"Tu plan {plan_name} "
                        f"permite hasta {limit} "
                        "miembros activos. "
                        f"Actualmente tienes "
                        f"{active_members}. "
                        "Desactiva un miembro o mejora "
                        "tu plan para agregar otro."
                    ),

                "resource":
                    "members",

                "used":
                    active_members,

                "limit":
                    limit,

                "remaining":
                    max(
                        limit - active_members,
                        0,
                    ),
            },
        )
