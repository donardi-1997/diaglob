import os
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
    Store,
    User,
)
from ..plan_limits import get_organization_limits
from ..plans import get_plan
from ..permissions import get_permissions_for_role
from ..services.trial_service import serialize_trial_status
from .deps import (
    get_current_membership,
    serialize_store_short,
)

router = APIRouter()

TEAM_ROLES = {
    "manager",
    "operator",
    "analyst",
}


class TeamMemberCreate(BaseModel):
    email: str
    role: str = "operator"
    all_stores: bool = True
    store_ids: list[int] = []


class TeamMemberUpdate(BaseModel):
    role: str | None = None
    all_stores: bool | None = None
    store_ids: list[int] | None = None
    active: bool | None = None


class TeamInvitationCreate(BaseModel):
    email: str
    role: str = "operator"
    all_stores: bool = True
    store_ids: list[int] = []


def serialize_team_invitation(
    invitation: OrganizationInvitation,
):
    status = invitation.status

    if (
        status == "pending"
        and invitation.expires_at
        <= datetime.utcnow()
    ):
        status = "expired"

    return {
        "id":
            invitation.id,

        "organization_id":
            invitation.organization_id,

        "email":
            invitation.email,

        "role":
            invitation.role,

        "all_stores":
            bool(
                invitation.all_stores
            ),

        "active":
            status == "pending",

        "status":
            status,

        "stores": [
            serialize_store_short(store)
            for store in invitation.stores
            if not store.deleted
        ],

        "expires_at":
            invitation.expires_at.isoformat(),

        "accepted_at":
            (
                invitation.accepted_at.isoformat()
                if invitation.accepted_at
                else None
            ),

        "created_at":
            invitation.created_at.isoformat(),
    }


def serialize_team_member(
    membership: OrganizationMembership,
):
    return {
        "id": membership.id,
        "user_id": membership.user_id,
        "name": membership.user.name,
        "email": membership.user.email,
        "role": membership.role,
        "all_stores": bool(
            membership.all_stores
        ),
        "active": bool(
            membership.active
        ),
        "stores": [
            serialize_store_short(store)
            for store in membership.stores
            if not store.deleted
        ],
        "created_at":
            membership.created_at.isoformat(),
    }


def resolve_team_member_stores(
    organization_id: int,
    store_ids: list[int],
    db: Session,
):
    requested_ids = sorted(
        set(store_ids)
    )

    if not requested_ids:
        return []

    stores = (
        db.query(Store)
        .filter(
            Store.organization_id
            == organization_id,
            Store.id.in_(requested_ids),
            Store.deleted.is_(False),
        )
        .all()
    )

    found_ids = {
        store.id
        for store in stores
    }

    if found_ids != set(requested_ids):
        raise HTTPException(
            status_code=400,
            detail={
                "code":
                    "INVALID_TEAM_STORE",

                "message":
                    (
                        "Una o más tiendas no pertenecen "
                        "a esta organización."
                    ),
            },
        )

    return stores


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


def ensure_member_capacity(
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


def _get_active_store_usage(
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


def get_paddle_base_url():
    import os
    paddle_env = os.getenv(
        "PADDLE_ENV",
        "production",
    )
    if paddle_env == "sandbox":
        return (
            "https://sandbox-vendors.paddle.com"
            "/api/2.0"
        )
    return (
        "https://vendors.paddle.com"
        "/api/2.0"
    )


def get_paddle_headers():
    import os
    api_key = os.getenv(
        "PADDLE_API_KEY",
        "",
    )
    return {
        "Authorization":
            f"Bearer {api_key}",
        "Content-Type":
            "application/json",
    }


@router.get("/api/organization")
def get_organization(
    membership: OrganizationMembership = Depends(
        get_current_membership
    ),
    db: Session = Depends(get_db),
):
    organization = membership.organization
    trial_status = serialize_trial_status(db, organization)

    plan = get_plan(
        organization.plan
    )

    active_stores = (
        _get_active_store_usage(
            db,
            organization.id,
        )
    )

    next_billed_at = None

    subscription_id = (
        organization.billing_subscription_id
    )

    paddle_api_key = os.getenv("PADDLE_API_KEY")

    if subscription_id and paddle_api_key:
        try:
            paddle_response = httpx.get(
                (
                    f"{get_paddle_base_url()}"
                    f"/subscriptions/{subscription_id}"
                ),
                headers=get_paddle_headers(),
                timeout=15,
            )

            if paddle_response.status_code < 400:
                paddle_payload = (
                    paddle_response.json()
                )

                paddle_data = (
                    paddle_payload.get("data")
                    or {}
                )

                next_billed_at = (
                    paddle_data.get(
                        "next_billed_at"
                    )
                )

        except (
            httpx.HTTPError,
            ValueError,
        ):
            next_billed_at = None

    return {
        "id": organization.id,
        "name": organization.name,
        "slug": organization.slug,
        "active": organization.active,
        "auto_renew_enabled":
            bool(organization.auto_renew_enabled),

        "plan": organization.plan,
        "plan_name": plan["name"],
        "subscription_status": organization.subscription_status,
        "trial": trial_status,
        "billing_period_months":
            organization.billing_period_months,

        "next_billed_at":
            next_billed_at,

        "pending_plan":
            organization.pending_plan,

        "pending_billing_period_months":
            organization.pending_billing_period_months,

        "pending_plan_effective_at":
            (
                organization.pending_plan_effective_at.isoformat()
                + "Z"
                if organization.pending_plan_effective_at
                else None
            ),

        "active_stores":
            active_stores,

        "active_store_limit":
            get_organization_limits(
                membership.organization
            ).active_stores,

        "role": membership.role,
        "all_stores": membership.all_stores,

        "permissions":
            get_permissions_for_role(
                membership.role
            ),
    }


@router.get("/api/team/invitations")
def list_team_invitations(
    membership: OrganizationMembership = Depends(
        get_current_membership
    ),
    db: Session = Depends(get_db),
):
    invitations = (
        db.query(OrganizationInvitation)
        .filter(
            OrganizationInvitation.organization_id
            == membership.organization_id,
        )
        .order_by(
            OrganizationInvitation.created_at.desc()
        )
        .all()
    )

    return {
        "items": [
            serialize_team_invitation(
                invitation
            )
            for invitation in invitations
        ],
        "total":
            len(invitations),
    }


@router.post("/api/team/invitations")
def create_team_invitation(
    payload: TeamInvitationCreate,
    membership: OrganizationMembership = Depends(
        get_current_membership
    ),
    db: Session = Depends(get_db),
):
    if membership.role not in {
        "owner",
        "manager",
    }:
        raise HTTPException(
            status_code=403,
            detail={
                "code":
                    "TEAM_MANAGEMENT_DENIED",

                "message":
                    (
                        "No tienes permiso para "
                        "invitar miembros."
                    ),
            },
        )

    email = (
        payload.email
        .strip()
        .lower()
    )

    if not email:
        raise HTTPException(
            status_code=400,
            detail={
                "code":
                    "EMAIL_REQUIRED",

                "message":
                    "El correo es obligatorio.",
            },
        )

    role = (
        payload.role
        .strip()
        .lower()
    )

    if role not in TEAM_ROLES:
        raise HTTPException(
            status_code=400,
            detail={
                "code":
                    "INVALID_TEAM_ROLE",

                "message":
                    (
                        "El rol debe ser "
                        "manager, operator o analyst."
                    ),
            },
        )

    existing_user = (
        db.query(User)
        .filter(
            User.email == email,
        )
        .first()
    )

    if existing_user:
        active_membership = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id
                == existing_user.id,

                OrganizationMembership.organization_id
                == membership.organization_id,

                OrganizationMembership.active.is_(True),
            )
            .first()
        )

        if active_membership:
            raise HTTPException(
                status_code=409,
                detail={
                    "code":
                        "MEMBER_ALREADY_EXISTS",

                    "message":
                        (
                            "Esta persona ya es miembro "
                            "activo de la organización."
                        ),
                },
            )

    now = datetime.utcnow()

    pending = (
        db.query(OrganizationInvitation)
        .filter(
            OrganizationInvitation.organization_id
            == membership.organization_id,

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

    if pending:
        if pending.expires_at > now:
            raise HTTPException(
                status_code=409,
                detail={
                    "code":
                        "INVITATION_ALREADY_PENDING",

                    "message":
                        (
                            "Ya existe una invitación "
                            "pendiente para este correo."
                        ),
                },
            )

        pending.status = "expired"
        db.flush()

    stores = (
        []
        if payload.all_stores
        else resolve_team_member_stores(
            membership.organization_id,
            payload.store_ids,
            db,
        )
    )

    invitation = OrganizationInvitation(
        organization_id=
            membership.organization_id,

        email=email,

        role=role,

        all_stores=
            payload.all_stores,

        status=
            "pending",

        expires_at=(
            now
            + timedelta(days=7)
        ),
    )

    invitation.stores = stores

    db.add(invitation)

    try:
        db.commit()
        db.refresh(invitation)

    except Exception:
        db.rollback()
        raise

    return serialize_team_invitation(
        invitation
    )


@router.delete(
    "/api/team/invitations/{invitation_id}"
)
def cancel_team_invitation(
    invitation_id: int,
    membership: OrganizationMembership = Depends(
        get_current_membership
    ),
    db: Session = Depends(get_db),
):
    if membership.role not in {
        "owner",
        "manager",
    }:
        raise HTTPException(
            status_code=403,
            detail={
                "code":
                    "TEAM_MANAGEMENT_DENIED",

                "message":
                    (
                        "No tienes permiso para "
                        "cancelar invitaciones."
                    ),
            },
        )

    invitation = (
        db.query(OrganizationInvitation)
        .filter(
            OrganizationInvitation.id
            == invitation_id,

            OrganizationInvitation.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not invitation:
        raise HTTPException(
            status_code=404,
            detail={
                "code":
                    "INVITATION_NOT_FOUND",

                "message":
                    "Invitación no encontrada.",
            },
        )

    if invitation.status != "pending":
        raise HTTPException(
            status_code=409,
            detail={
                "code":
                    "INVITATION_NOT_PENDING",

                "message":
                    (
                        "Solo se pueden cancelar "
                        "invitaciones pendientes."
                    ),
            },
        )

    if (
        invitation.expires_at
        <= datetime.utcnow()
    ):
        invitation.status = "expired"

        db.commit()

        raise HTTPException(
            status_code=409,
            detail={
                "code":
                    "INVITATION_EXPIRED",

                "message":
                    "La invitación ya expiró.",
            },
        )

    invitation.status = "cancelled"

    db.commit()
    db.refresh(invitation)

    return serialize_team_invitation(
        invitation
    )


@router.get("/api/team")
def list_team_members(
    membership: OrganizationMembership = Depends(
        get_current_membership
    ),
    db: Session = Depends(get_db),
):
    members = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id
            == membership.organization_id,
        )
        .order_by(
            OrganizationMembership.created_at.asc()
        )
        .all()
    )

    limits = get_organization_limits(
        membership.organization
    )

    active_members = sum(
        1
        for member in members
        if member.active
    )

    return {
        "items": [
            serialize_team_member(member)
            for member in members
        ],

        "usage": {
            "used":
                active_members,

            "limit":
                limits.members,

            "remaining":
                max(
                    limits.members
                    - active_members,
                    0,
                ),
        },

        "total":
            len(members),
    }


@router.post("/api/team")
def create_team_member(
    payload: TeamMemberCreate,
    membership: OrganizationMembership = Depends(
        get_current_membership
    ),
    db: Session = Depends(get_db),
):
    if membership.role not in {
        "owner",
        "manager",
    }:
        raise HTTPException(
            status_code=403,
            detail="Team management access denied",
        )

    role = (
        payload.role
        .strip()
        .lower()
    )

    if role not in TEAM_ROLES:
        raise HTTPException(
            status_code=400,
            detail={
                "code":
                    "INVALID_TEAM_ROLE",

                "message":
                    "El rol debe ser manager, operator o analyst.",
            },
        )

    email = (
        payload.email
        .strip()
        .lower()
    )

    if not email:
        raise HTTPException(
            status_code=400,
            detail="Email is required",
        )

    user = (
        db.query(User)
        .filter(
            User.email == email,
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail={
                "code":
                    "USER_NOT_REGISTERED",

                "message":
                    (
                        "El usuario todavía no existe en DIAGLOB. "
                        "Primero debe registrarse. "
                        "El flujo de invitaciones se agregará "
                        "por separado."
                    ),
            },
        )

    existing_membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id
            == user.id,

            OrganizationMembership.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if existing_membership:
        if existing_membership.active:
            raise HTTPException(
                status_code=409,
                detail={
                    "code":
                        "MEMBER_ALREADY_EXISTS",

                    "message":
                        "El usuario ya pertenece a la organización.",
                },
            )

        ensure_member_capacity(
            db,
            membership.organization_id,
        )

        stores = (
            []
            if payload.all_stores
            else resolve_team_member_stores(
                membership.organization_id,
                payload.store_ids,
                db,
            )
        )

        existing_membership.role = role
        existing_membership.all_stores = (
            payload.all_stores
        )
        existing_membership.stores = stores
        existing_membership.active = True

        db.commit()
        db.refresh(existing_membership)

        return serialize_team_member(
            existing_membership
        )

    ensure_member_capacity(
        db,
        membership.organization_id,
    )

    stores = (
        []
        if payload.all_stores
        else resolve_team_member_stores(
            membership.organization_id,
            payload.store_ids,
            db,
        )
    )

    new_membership = OrganizationMembership(
        user_id=user.id,
        organization_id=
            membership.organization_id,
        role=role,
        all_stores=payload.all_stores,
        active=True,
    )

    new_membership.stores = stores

    db.add(new_membership)
    db.commit()
    db.refresh(new_membership)

    return serialize_team_member(
        new_membership
    )


@router.delete("/api/team/{membership_id}")
def delete_team_member(
    membership_id: int,
    membership: OrganizationMembership = Depends(
        get_current_membership
    ),
    db: Session = Depends(get_db),
):
    if membership.role != "owner":
        raise HTTPException(
            status_code=403,
            detail={
                "code":
                    "OWNER_REQUIRED",

                "message":
                    (
                        "Solo el owner puede eliminar "
                        "miembros del equipo."
                    ),
            },
        )

    target = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.id
            == membership_id,

            OrganizationMembership.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not target:
        raise HTTPException(
            status_code=404,
            detail={
                "code":
                    "TEAM_MEMBER_NOT_FOUND",

                "message":
                    "Miembro no encontrado.",
            },
        )

    if target.id == membership.id:
        raise HTTPException(
            status_code=409,
            detail={
                "code":
                    "OWNER_CANNOT_DELETE_SELF",

                "message":
                    (
                        "El owner no puede eliminarse "
                        "a sí mismo."
                    ),
            },
        )

    if target.role == "owner":
        raise HTTPException(
            status_code=409,
            detail={
                "code":
                    "OWNER_CANNOT_BE_DELETED",

                "message":
                    (
                        "No se puede eliminar un owner "
                        "desde este endpoint."
                    ),
            },
        )

    if not target.active:
        return {
            "deleted": True,
            "already_inactive": True,
            "membership_id": target.id,
        }

    target.active = False

    db.commit()
    db.refresh(target)

    return {
        "deleted": True,
        "membership_id": target.id,
        "email": target.user.email,
        "active": target.active,
    }


@router.patch("/api/team/{membership_id}")
def update_team_member(
    membership_id: int,
    payload: TeamMemberUpdate,
    membership: OrganizationMembership = Depends(
        get_current_membership
    ),
    db: Session = Depends(get_db),
):
    if membership.role not in {
        "owner",
        "manager",
    }:
        raise HTTPException(
            status_code=403,
            detail="Team management access denied",
        )

    target = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.id
            == membership_id,

            OrganizationMembership.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not target:
        raise HTTPException(
            status_code=404,
            detail="Team member not found",
        )

    if (
        target.role == "owner"
        and target.id != membership.id
        and membership.role != "owner"
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Solo el owner puede modificar "
                "otro owner."
            ),
        )

    if payload.role is not None:
        role = (
            payload.role
            .strip()
            .lower()
        )

        if target.role == "owner":
            if role != "owner":
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code":
                            "OWNER_ROLE_PROTECTED",

                        "message":
                            (
                                "El owner principal no puede "
                                "cambiar de rol desde este endpoint."
                            ),
                    },
                )

        elif role not in TEAM_ROLES:
            raise HTTPException(
                status_code=400,
                detail={
                    "code":
                        "INVALID_TEAM_ROLE",

                    "message":
                        "El rol debe ser manager, operator o analyst.",
                },
            )

        else:
            target.role = role

    if payload.active is not None:
        if (
            payload.active
            and not target.active
        ):
            ensure_member_capacity(
                db,
                membership.organization_id,
            )

        if (
            target.role == "owner"
            and payload.active is False
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "code":
                        "OWNER_CANNOT_BE_DISABLED",

                    "message":
                        (
                            "El owner principal no puede "
                            "ser desactivado."
                        ),
                },
            )

        target.active = payload.active

    if payload.all_stores is not None:
        target.all_stores = (
            payload.all_stores
        )

        if target.all_stores:
            target.stores = []

    if payload.store_ids is not None:
        if target.all_stores:
            target.stores = []
        else:
            target.stores = (
                resolve_team_member_stores(
                    membership.organization_id,
                    payload.store_ids,
                    db,
                )
            )

    db.commit()
    db.refresh(target)

    return serialize_team_member(target)
