"""Tenant, membership, and store persistence models.

These definitions are physically owned by the tenancy domain while
``app.models`` keeps compatibility re-exports for existing callers. Table
names, columns, constraints, relationships, defaults, and shared SQLAlchemy
metadata are intentionally unchanged.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
    event,
    inspect as sa_inspect,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


# ============================================================
# TENANCY ASSOCIATION TABLES
# ============================================================

agent_stores = Table(
    "agent_stores",
    Base.metadata,
    Column(
        "agent_id",
        ForeignKey("agents.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "store_id",
        ForeignKey("stores.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

organization_invitation_stores = Table(
    "organization_invitation_stores",
    Base.metadata,
    Column(
        "invitation_id",
        ForeignKey(
            "organization_invitations.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    ),
    Column(
        "store_id",
        ForeignKey(
            "stores.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    ),
)

knowledge_base_stores = Table(
    "knowledge_base_stores",
    Base.metadata,
    Column(
        "knowledge_base_id",
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "store_id",
        ForeignKey("stores.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


# ============================================================
# ORGANIZATION
# ============================================================

class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    slug: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
    )

    plan: Mapped[str] = mapped_column(
        String(30),
        default="none",
        nullable=False,
    )

    billing_provider: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    billing_customer_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    billing_subscription_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    billing_price_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    billing_period_months: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )

    subscription_status: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    pending_plan: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    pending_billing_period_months: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    pending_plan_effective_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    pending_plan_prepared_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    billing_last_event_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    billing_last_event_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    auto_renew_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    stores = relationship(
        "Store",
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    customers = relationship(
        "Customer",
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    conversations = relationship(
        "Conversation",
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    agents = relationship(
        "Agent",
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    knowledge_bases = relationship(
        "KnowledgeBase",
        back_populates="organization",
        cascade="all, delete-orphan",
    )


# ============================================================
# STORE
# ============================================================

class Store(Base):
    __tablename__ = "stores"

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "slug",
            name="uq_store_org_slug",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    organization_id: Mapped[int] = mapped_column(
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    slug: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    country_code: Mapped[str] = mapped_column(
        String(2),
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )

    timezone: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    default_language: Mapped[str] = mapped_column(
        String(10),
        default="es",
        nullable=False,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    shopify_domain: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    active_since: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    keep_on_pending_downgrade: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    organization = relationship(
        "Organization",
        back_populates="stores",
    )

    conversations = relationship(
        "Conversation",
        back_populates="store",
        cascade="all, delete-orphan",
    )

    customer_profiles = relationship(
        "CustomerStoreProfile",
        back_populates="store",
        cascade="all, delete-orphan",
    )

    agents = relationship(
        "Agent",
        secondary=agent_stores,
        back_populates="stores",
    )

    knowledge_bases = relationship(
        "KnowledgeBase",
        secondary=knowledge_base_stores,
        back_populates="stores",
    )

    products = relationship(
        "Product",
        back_populates="store",
        cascade="all, delete-orphan",
    )


# ============================================================
# STORE ACTIVITY TRACKING
# ============================================================

@event.listens_for(Store, "before_insert")
def _diaglob_store_active_since_insert(
    mapper,
    connection,
    target,
):
    if target.active:
        if target.active_since is None:
            target.active_since = datetime.utcnow()
    else:
        target.active_since = None


@event.listens_for(Store, "before_update")
def _diaglob_store_active_since_update(
    mapper,
    connection,
    target,
):
    state = sa_inspect(target)
    history = state.attrs.active.history

    if not history.has_changes():
        return

    if target.active:
        target.active_since = datetime.utcnow()
    else:
        target.active_since = None


# ============================================================
# USER
# ============================================================

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    email: Mapped[str] = mapped_column(
        String(200),
        unique=True,
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    external_auth_id: Mapped[str | None] = mapped_column(
        String(200),
        unique=True,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    memberships = relationship(
        "OrganizationMembership",
        back_populates="user",
        cascade="all, delete-orphan",
    )


# ============================================================
# ORGANIZATION INVITATION
# ============================================================

class OrganizationInvitation(Base):
    __tablename__ = "organization_invitations"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    organization_id: Mapped[int] = mapped_column(
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    email: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
    )

    role: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="operator",
    )

    all_stores: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
        index=True,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    organization = relationship(
        "Organization",
    )

    stores = relationship(
        "Store",
        secondary=organization_invitation_stores,
    )


# ============================================================
# ORGANIZATION MEMBERSHIP
# ============================================================

class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "organization_id",
            name="uq_user_organization_membership",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    organization_id: Mapped[int] = mapped_column(
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    role: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="operator",
    )

    all_stores: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    user = relationship(
        "User",
        back_populates="memberships",
    )

    organization = relationship(
        "Organization",
    )

    stores = relationship(
        "Store",
        secondary="membership_stores",
    )


# ============================================================
# MEMBERSHIP <-> STORES
# ============================================================

class MembershipStore(Base):
    __tablename__ = "membership_stores"

    membership_id: Mapped[int] = mapped_column(
        ForeignKey(
            "organization_memberships.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )

    store_id: Mapped[int] = mapped_column(
        ForeignKey(
            "stores.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )


__all__ = [
    "MembershipStore",
    "Organization",
    "OrganizationInvitation",
    "OrganizationMembership",
    "Store",
    "User",
    "agent_stores",
    "knowledge_base_stores",
    "organization_invitation_stores",
]
