from sqlalchemy import event
from sqlalchemy import inspect as sa_inspect
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .model_domains.tenancy import (  # noqa: F401
    MembershipStore,
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
    Store,
    User,
    agent_stores,
    knowledge_base_stores,
    organization_invitation_stores,
)


# ============================================================
# ASSOCIATION TABLES
# ============================================================

# Tenant/store association tables are defined in app.model_domains.tenancy.
agent_knowledge_bases = Table(
    "agent_knowledge_bases",
    Base.metadata,
    Column(
        "agent_id",
        ForeignKey("agents.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "knowledge_base_id",
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

# ============================================================
# TENANCY DOMAIN (compatibility re-export)
# ============================================================

# Tenancy models are physically defined in app.model_domains.tenancy.
# Imports near the top preserve the historical app.models import surface.


# ============================================================
# CUSTOMER DOMAIN (compatibility re-export)
# ============================================================

# Customer models are physically defined in app.model_domains.customers.
# This import preserves the historical app.models import surface.
from .model_domains.customers import Customer, CustomerStoreProfile


# ============================================================
# AGENT
# ============================================================

class Agent(Base):
    __tablename__ = "agents"

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

    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    organization = relationship(
        "Organization",
        back_populates="agents",
    )

    stores = relationship(
        "Store",
        secondary=agent_stores,
        back_populates="agents",
    )

    knowledge_bases = relationship(
        "KnowledgeBase",
        secondary=agent_knowledge_bases,
        back_populates="agents",
    )

    conversations = relationship(
        "Conversation",
        back_populates="assigned_agent",
    )


# ============================================================
# KNOWLEDGE BASE
# ============================================================

class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

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

    scope: Mapped[str] = mapped_column(
        String(30),
        default="selected_stores",
        nullable=False,
    )

    external_id: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    external_data_source_id: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    external_status: Mapped[str | None] = mapped_column(
        String(30),
        default="pending",
        server_default="pending",
        nullable=True,
    )

    external_last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    provisioning_stage: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    provisioning_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    provisioning_stage_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    organization = relationship(
        "Organization",
        back_populates="knowledge_bases",
    )

    stores = relationship(
        "Store",
        secondary=knowledge_base_stores,
        back_populates="knowledge_bases",
    )

    agents = relationship(
        "Agent",
        secondary=agent_knowledge_bases,
        back_populates="knowledge_bases",
    )



# ============================================================
# KNOWLEDGE SOURCE
# ============================================================

class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"

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

    knowledge_base_id: Mapped[int] = mapped_column(
        ForeignKey(
            "knowledge_bases.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    source_type: Mapped[str] = mapped_column(
        String(30),
        default="file",
        nullable=False,
    )

    content_type: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    s3_bucket: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    s3_key: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )

    size_bytes: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="uploaded",
        nullable=False,
    )

    ingestion_job_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
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

    external_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    external_name: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    sheet_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    sync_status: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    sync_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    metadata_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    external_mime_type: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    external_modified_at: Mapped[datetime | None] = (
        mapped_column(
            DateTime,
            nullable=True,
        )
    )

    parent_source_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "knowledge_sources.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    external_size: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    sync_generation: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    knowledge_base = relationship(
        "KnowledgeBase",
    )


# ============================================================
# CONVERSATION
# ============================================================

class Conversation(Base):
    __tablename__ = "conversations"

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

    store_id: Mapped[int] = mapped_column(
        ForeignKey(
            "stores.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    customer_id: Mapped[int] = mapped_column(
        ForeignKey(
            "customers.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    agent_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "agents.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    channel: Mapped[str] = mapped_column(
        String(50),
        default="internal",
        nullable=False,
    )

    preview: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )

    unread: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    mode: Mapped[str] = mapped_column(
        String(20),
        default="ai",
        nullable=False,
    )

    tags: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    organization = relationship(
        "Organization",
        back_populates="conversations",
    )

    store = relationship(
        "Store",
        back_populates="conversations",
    )

    customer = relationship(
        "Customer",
        back_populates="conversations",
    )

    assigned_agent = relationship(
        "Agent",
        back_populates="conversations",
    )

    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.id",
    )


# ============================================================
# MESSAGE
# ============================================================

class Message(Base):
    __tablename__ = "messages"

    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "provider",
            "external_message_id",
            name="uq_message_provider_external",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    conversation_id: Mapped[int] = mapped_column(
        ForeignKey(
            "conversations.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    agent_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "agents.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    sender: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    provider: Mapped[str] = mapped_column(
        String(30),
        default="internal",
        nullable=False,
    )

    external_message_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    delivery_status: Mapped[str] = mapped_column(
        String(30),
        default="delivered",
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    conversation = relationship(
        "Conversation",
        back_populates="messages",
    )

    agent = relationship(
        "Agent",
    )


# ============================================================
# TENANCY USER / MEMBERSHIP DOMAIN (compatibility re-export)
# ============================================================

# User, invitation, membership, and membership-store models are physically
# defined in app.model_domains.tenancy and imported near the top of this file.

# Commerce integration models are physically defined in app.model_domains.commerce_integrations.
# These imports preserve the historical app.models import surface.
from .model_domains.commerce_integrations import (
    CommerceConnection,
    DropiConnection,
    MetaAdsConnection,
)


# ============================================================
# WHATSAPP CONNECTION
# ============================================================

class WhatsAppConnection(Base):
    __tablename__ = "whatsapp_connections"

    __table_args__ = (
        UniqueConstraint(
            "store_id",
            name="uq_whatsapp_connection_store",
        ),
        UniqueConstraint(
            "phone_number_id",
            name="uq_whatsapp_phone_number",
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

    store_id: Mapped[int] = mapped_column(
        ForeignKey(
            "stores.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        unique=True,
        index=True,
    )

    phone_number_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
    )

    business_account_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    access_token_encrypted: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    verify_token: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="connected",
        nullable=False,
        index=True,
    )

    connected_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    store = relationship(
        "Store",
    )

    organization = relationship(
        "Organization",
    )


class WhatsAppMessageTemplate(Base):
    __tablename__ = "whatsapp_message_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    whatsapp_connection_id: Mapped[int] = mapped_column(ForeignKey("whatsapp_connections.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_template_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_template_name: Mapped[str] = mapped_column(String(512), nullable=False)
    language_code: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    components: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("whatsapp_connection_id", "provider_template_name", "language_code", name="uq_whatsapp_template_connection_name_language"),)


# OAuth state models are physically defined in app.model_domains.oauth.
# These imports preserve the historical app.models import surface.
from .model_domains.oauth import NuvemshopOAuthState, ShopifyOAuthState


# ============================================================
# PRODUCT
# ============================================================

class Product(Base):
    __tablename__ = "products"

    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "shopify_product_id",
            name="uq_product_store_shopify_id",
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

    store_id: Mapped[int] = mapped_column(
        ForeignKey(
            "stores.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    shopify_product_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    handle: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    description: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )

    image_url: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    vendor: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    product_type: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    cost: Mapped[float | None] = mapped_column(
        Numeric(18, 4),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    store = relationship(
        "Store",
        back_populates="products",
    )

    variants = relationship(
        "ProductVariant",
        back_populates="product",
        cascade="all, delete-orphan",
    )


# ============================================================
# PRODUCT VARIANT
# ============================================================

class ProductVariant(Base):
    __tablename__ = "product_variants"

    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "shopify_variant_id",
            name="uq_variant_product_shopify_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey(
            "products.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    shopify_variant_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    sku: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    barcode: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    price: Mapped[float] = mapped_column(
        Numeric(18, 4),
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )

    inventory_quantity: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    available: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    product = relationship(
        "Product",
        back_populates="variants",
    )


# ============================================================
# ORDER
# ============================================================

class Order(Base):
    __tablename__ = "orders"

    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "shopify_order_id",
            name="uq_order_store_shopify_id",
        ),
        Index(
            "uq_order_store_idempotency_key",
            "store_id",
            "idempotency_key",
            unique=True,
            postgresql_where="idempotency_key IS NOT NULL",
        ),
        Index(
            "uq_order_store_shopify_draft_order_id",
            "store_id",
            "shopify_draft_order_id",
            unique=True,
            postgresql_where="shopify_draft_order_id IS NOT NULL",
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

    store_id: Mapped[int] = mapped_column(
        ForeignKey(
            "stores.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "customers.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    shopify_order_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    external_order_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    order_number: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    total_amount: Mapped[float] = mapped_column(
        Numeric(18, 4),
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )

    financial_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    payment_method: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    payment_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    fulfillment_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    lifecycle_status: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        index=True,
    )

    lifecycle_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    source: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    invoice_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    shopify_draft_order_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    idempotency_key: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    external_creation_status: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    external_last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    items = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
    )


# ============================================================
# ORDER ITEM
# ============================================================

class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    order_id: Mapped[int] = mapped_column(
        ForeignKey(
            "orders.id",
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

    store_id: Mapped[int] = mapped_column(
        ForeignKey(
            "stores.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    product_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "products.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "product_variants.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    shopify_variant_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    sku: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    unit_price: Mapped[float] = mapped_column(
        Numeric(18, 4),
        nullable=False,
    )

    unit_cost: Mapped[float | None] = mapped_column(
        Numeric(18, 4),
        nullable=True,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    order = relationship(
        "Order",
        back_populates="items",
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

    history = (
        state.attrs.active.history
    )

    if not history.has_changes():
        return

    if target.active:
        target.active_since = datetime.utcnow()
    else:
        target.active_since = None



# ============================================================
# AUTOMATIONS
# ============================================================


class Automation(Base):
    __tablename__ = "automations"

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

    store_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "stores.id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    trigger_type: Mapped[str] = mapped_column(
        String(50),
        default="manual",
        nullable=False,
        index=True,
    )

    conditions_json: Mapped[str] = mapped_column(
        Text,
        default="[]",
        nullable=False,
    )

    actions_json: Mapped[str] = mapped_column(
        Text,
        default="[]",
        nullable=False,
    )

    created_by: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    organization = relationship(
        "Organization",
    )

    store = relationship(
        "Store",
    )

    executions = relationship(
        "AutomationExecution",
        back_populates="automation",
        order_by="AutomationExecution.id.desc()",
    )

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "store_id",
            "name",
            name="uq_automation_org_store_name",
        ),
    )



class AutomationExecution(Base):
    __tablename__ = "automation_executions"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    automation_id: Mapped[int] = mapped_column(
        ForeignKey(
            "automations.id",
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

    store_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "stores.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    event_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
        index=True,
    )

    input_json: Mapped[str] = mapped_column(
        Text,
        default="{}",
        nullable=False,
    )

    result_json: Mapped[str] = mapped_column(
        Text,
        default="{}",
        nullable=False,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    automation = relationship(
        "Automation",
        back_populates="executions",
    )


# ============================================================
# AUTOMATION CAMPAIGNS V2.1
# ============================================================


class AutomationCampaign(Base):
    __tablename__ = "automation_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    automation_type: Mapped[str] = mapped_column(String(50), default="custom", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False, index=True)
    audience_type: Mapped[str] = mapped_column(String(20), default="dynamic", nullable=False)
    audience_filters: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    schedule_type: Mapped[str] = mapped_column(String(30), default="once", nullable=False)
    schedule_config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False)
    send_window_start: Mapped[str | None] = mapped_column(String(5), nullable=True)
    send_window_end: Mapped[str | None] = mapped_column(String(5), nullable=True)
    cooldown_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    channel: Mapped[str] = mapped_column(String(30), default="whatsapp", nullable=False)
    message_template: Mapped[str] = mapped_column(Text, nullable=False)
    message_mode: Mapped[str] = mapped_column(String(20), default="free_form", nullable=False)
    whatsapp_template_id: Mapped[int | None] = mapped_column(ForeignKey("whatsapp_message_templates.id", ondelete="SET NULL"), nullable=True)
    template_variables: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    execution_enabled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    members = relationship("AutomationAudienceMember", back_populates="automation", cascade="all, delete-orphan")
    runs = relationship("AutomationRun", back_populates="automation", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("organization_id", "store_id", "name", name="uq_campaign_org_store_name"),)


class AutomationAudienceMember(Base):
    __tablename__ = "automation_audience_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    automation_id: Mapped[int] = mapped_column(ForeignKey("automation_campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    included: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    automation = relationship("AutomationCampaign", back_populates="members")
    __table_args__ = (UniqueConstraint("automation_id", "customer_id", name="uq_campaign_member"),)


class AutomationRun(Base):
    __tablename__ = "automation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    automation_id: Mapped[int] = mapped_column(ForeignKey("automation_campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="simulated", nullable=False, index=True)
    run_key: Mapped[str] = mapped_column(String(100), nullable=False)
    matched_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    eligible_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sent_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    excluded_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    automation = relationship("AutomationCampaign", back_populates="runs")
    recipients = relationship("AutomationRecipientExecution", back_populates="run", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("automation_id", "run_key", name="uq_campaign_run_key"),)


class AutomationRecipientExecution(Base):
    __tablename__ = "automation_recipient_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("automation_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    exclusion_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rendered_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    template_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    run = relationship("AutomationRun", back_populates="recipients")
    __table_args__ = (UniqueConstraint("run_id", "customer_id", name="uq_campaign_run_customer"),)


class AutomationDeliveryAttempt(Base):
    __tablename__ = "automation_delivery_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipient_execution_id: Mapped[int] = mapped_column(ForeignKey("automation_recipient_executions.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AutomationRateLimit(Base):
    __tablename__ = "automation_rate_limits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("whatsapp_connections.id", ondelete="CASCADE"), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    sent_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    __table_args__ = (UniqueConstraint("connection_id", "window_start", name="uq_automation_rate_limit_window"),)


# ============================================================
# AUTOMATION FLOWS V2.2 — MULTI-STEP AUTOMATION ENGINE
# ============================================================


class AutomationFlow(Base):
    __tablename__ = "automation_flows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (
        UniqueConstraint("organization_id", "store_id", "name", name="uq_flow_org_store_name"),
    )


class AutomationFlowVersion(Base):
    __tablename__ = "automation_flow_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    flow_id: Mapped[int] = mapped_column(ForeignKey("automation_flows.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    graph: Mapped[dict] = mapped_column(JSON, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (
        UniqueConstraint("flow_id", "version_number", name="uq_flow_version_number"),
        UniqueConstraint("flow_id", "id", name="uq_flow_version_flow_id_id"),
    )


class AutomationFlowRun(Base):
    __tablename__ = "automation_flow_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    flow_id: Mapped[int] = mapped_column(ForeignKey("automation_flows.id", ondelete="CASCADE"), nullable=False, index=True)
    flow_version_id: Mapped[int] = mapped_column(ForeignKey("automation_flow_versions.id", ondelete="CASCADE"), nullable=False)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    trigger_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total_recipients: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_recipients: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_recipients: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AutomationFlowRecipientExecution(Base):
    __tablename__ = "automation_flow_recipient_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    flow_run_id: Mapped[int] = mapped_column(ForeignKey("automation_flow_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    flow_version_id: Mapped[int] = mapped_column(ForeignKey("automation_flow_versions.id", ondelete="CASCADE"), nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)
    current_node_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    claim_token: Mapped[str | None] = mapped_column(String(100), nullable=True)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("flow_run_id", "customer_id", name="uq_flow_recipient_run_customer"),)


class AutomationNodeExecution(Base):
    __tablename__ = "automation_node_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    flow_recipient_execution_id: Mapped[int] = mapped_column(ForeignKey("automation_flow_recipient_executions.id", ondelete="CASCADE"), nullable=False, index=True)
    node_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    node_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# Google integration models are physically defined in app.model_domains.google.
# These imports preserve the historical app.models import surface.
from .model_domains.google import GoogleConnection, GoogleOAuthState


# Payment models are physically defined in app.model_domains.payments.
# These imports preserve the historical app.models import surface.
from .model_domains.payments import PaymentConnection, PaymentTransaction


# AI usage package credits are physically defined in app.model_domains.ai_usage.
from .model_domains.ai_usage import AiUsageCreditGrant
