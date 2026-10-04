import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)
from fastapi.security import (
    HTTPAuthorizationCredentials,
)
from botocore.exceptions import ClientError
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import COGNITO_USER_POOL_ID, verify_cognito_access_token
from ..db import get_db
from ..models import (
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
    User,
)
from ..permissions import get_permissions_for_role
from ..services.marketing_acquisition import record_registration_conversion
from ..services.trial_service import create_pending_trial
from .deps import (
    bearer_scheme,
    get_current_user,
)


logger = logging.getLogger(__name__)


class RegistrationMarketingTouchpoint(BaseModel):
    source: str | None = Field(default=None, max_length=120)
    medium: str | None = Field(default=None, max_length=120)
    campaign: str | None = Field(default=None, max_length=255)
    content: str | None = Field(default=None, max_length=255)
    term: str | None = Field(default=None, max_length=255)
    fbclid: str | None = Field(default=None, max_length=500)
    ttclid: str | None = Field(default=None, max_length=500)
    landing_path: str | None = Field(default=None, max_length=2048)
    captured_at: str | None = Field(default=None, max_length=80)


class RegistrationMarketingContext(BaseModel):
    consented: bool = False
    event_id: str = Field(max_length=120)
    event_source_url: str | None = Field(default=None, max_length=2048)
    fbp: str | None = Field(default=None, max_length=500)
    fbc: str | None = Field(default=None, max_length=500)
    first_touch: RegistrationMarketingTouchpoint | None = None
    last_touch: RegistrationMarketingTouchpoint | None = None


class RegistrationProvisionRequest(BaseModel):
    name: str
    organization_name: str | None = None
    marketing_context: RegistrationMarketingContext | None = None


router = APIRouter()


def _relink_deleted_cognito_identity(
    *,
    cognito,
    email_user: User,
    cognito_sub: str,
    name: str,
) -> bool:
    """Relink a local user only when its previous Cognito identity is gone."""
    previous_sub = email_user.external_auth_id

    if not previous_sub or previous_sub == cognito_sub:
        return False

    try:
        cognito.admin_get_user(
            UserPoolId=COGNITO_USER_POOL_ID,
            Username=previous_sub,
        )
    except ClientError as exc:
        error_code = (
            exc.response.get("Error", {}).get("Code")
        )
        if error_code != "UserNotFoundException":
            raise
    else:
        return False

    email_user.external_auth_id = cognito_sub
    email_user.name = name
    email_user.active = True
    return True


@router.post("/api/register/provision")
def provision_registration(
    request: Request,
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
        try:
            recovered_identity = (
                _relink_deleted_cognito_identity(
                    cognito=cognito,
                    email_user=email_user,
                    cognito_sub=cognito_sub,
                    name=name,
                )
            )
        except ClientError as exc:
            logger.exception(
                "registration.identity_recovery_check_failed email=%s",
                email,
            )
            raise HTTPException(
                status_code=503,
                detail=(
                    "Unable to verify the existing "
                    "account identity"
                ),
            ) from exc

        if not recovered_identity:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "EMAIL_ALREADY_LINKED",
                    "message": (
                        "Este correo ya está vinculado "
                        "a otra cuenta activa."
                    ),
                },
            )

        db.commit()
        db.refresh(email_user)

        recovered_membership = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id
                == email_user.id,
                OrganizationMembership.active.is_(True),
            )
            .first()
        )

        if recovered_membership:
            recovered_organization = (
                db.query(Organization)
                .filter(
                    Organization.id
                    == recovered_membership.organization_id
                )
                .first()
            )

            if recovered_organization:
                return {
                    "created": False,
                    "recovered": True,
                    "user": {
                        "id": email_user.id,
                        "name": email_user.name,
                        "email": email_user.email,
                    },
                    "organization": {
                        "id": recovered_organization.id,
                        "name": recovered_organization.name,
                        "slug": recovered_organization.slug,
                    },
                    "role": recovered_membership.role,
                }

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

    if payload.marketing_context is not None:
        forwarded_for = request.headers.get("x-forwarded-for", "")
        client_ip = (
            forwarded_for.split(",", 1)[0].strip()
            if forwarded_for
            else (request.client.host if request.client else None)
        )
        try:
            record_registration_conversion(
                db,
                organization_id=organization.id,
                user_id=user.id,
                email=user.email,
                marketing_context=payload.marketing_context.model_dump(
                    exclude_none=True
                ),
                client_ip=client_ip,
                client_user_agent=request.headers.get("user-agent"),
            )
        except Exception:
            db.rollback()
            logger.exception(
                "marketing.registration_conversion_failed organization_id=%s",
                organization.id,
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
