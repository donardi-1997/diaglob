import secrets
import json
import os
import hmac
import hashlib
import logging
import re
import time
import threading
import httpx
from typing import Literal

import httpx
from datetime import datetime, timedelta, timezone

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from .auth import verify_cognito_access_token
from .knowledge_storage import (
    delete_knowledge_file,
    delete_knowledge_prefix,
    upload_knowledge_file,
)
from .ai_generation import generate_grounded_answer
from .commerce import search_products
from .markets import AMERICA_MARKETS, get_market
from .billing import (
    calculate_local_proration,
    get_billing_period_from_price_id,
    get_paddle_price_id,
    get_plan_from_price_id,
    get_subscription_price_id,
    verify_paddle_signature,
)
from .plans import (
    get_plan,
)

from .plan_limits import (
    get_organization_limits,
    get_limits_for_plan,
)
from .rag import retrieve_agent_knowledge
from .ai_reply_service import (
    generate_auto_reply,
    _detect_handoff,
)
from .permissions import (
    get_permissions_for_role,
    has_permission,
)
from .db import Base, SessionLocal, engine, get_db
from .models import (
    Agent,
    Automation,
    AutomationCampaign,
    AutomationAudienceMember,
    AutomationRun,
    AutomationRecipientExecution,
    AutomationExecution,
    AutomationFlow,
    AutomationFlowVersion,
    AutomationFlowRun,
    AutomationFlowRecipientExecution,
    AutomationNodeExecution,
    CommerceConnection,
    Conversation,
    Customer,
    CustomerStoreProfile,
    DropiConnection,
    GoogleConnection,
    GoogleOAuthState,
    KnowledgeBase,
    KnowledgeSource,
    Order,
    Product,
    ProductVariant,
    Message,
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
    ShopifyOAuthState,
    Store,
    User,
    WhatsAppConnection,
    WhatsAppMessageTemplate,
)

from .shopify_oauth import (
    SHOPIFY_SCOPES,
    build_authorization_url,
    exchange_access_token,
    generate_oauth_state,
    normalize_shop_domain,
    verify_shopify_hmac,
)

from .shopify_security import (
    encrypt_shopify_secret,
    decrypt_shopify_secret,
)

from .shopify_sync import (
    test_shopify_connection,
    sync_shopify_products,
)

from .shopify_orders import (
    create_shopify_draft_order,
    list_shopify_orders,
    get_shopify_order,
)

from .automations import (
    execute_automation,
    emit_event,
    safe_emit_event,
    VALID_TRIGGER_TYPES,
)

from .analytics import (
    get_summary,
    get_timeseries,
    get_conversations_analytics,
    get_commerce_analytics,
    get_automations_analytics,
    get_date_range,
)

from .shopify_client import (
    ShopifyAuthError,
    ShopifyAPIError,
    ShopifyGraphQLError,
    ShopifyUserError,
)

from .dropi_security import (
    encrypt_dropi_secret,
)

from .whatsapp_security import (
    decrypt_whatsapp_secret,
    encrypt_whatsapp_secret,
)

from .whatsapp_client import (
    list_whatsapp_templates,
    send_whatsapp_text_message,
)
from .whatsapp_compliance import MESSAGE_MODES, TEMPLATE_VARIABLES

from .google_security import (
    encrypt_google_secret,
    decrypt_google_secret,
)

from .google_sheets_client import (
    extract_spreadsheet_id,
    get_spreadsheet_metadata,
    fetch_sheet_values,
    normalize_to_csv,
)

from .google_drive_client import (
    GoogleDriveFileTooLarge,
    MAX_TOTAL_SYNC_BYTES,
    list_drive_files,
    list_drive_folders,
    list_folder_children,
    get_file_metadata,
    download_drive_file,
    export_google_doc,
    is_supported_mime_type,
    is_google_doc,
    validate_folder_sync_limits,
)
from .automation_campaigns import (
    audience_metrics,
    explain,
    json_load,
    render_template,
    simulate_campaign,
    validate_campaign,
)
from .automation_execution_engine import initial_next_run

from .bedrock_ingestion import (
    start_ingestion_job,
    get_ingestion_status,
    map_google_api_error,
    STATUS_INDEXING,
    STATUS_SYNCED,
    STATUS_FAILED,
)

from .bedrock_knowledge_base import (
    BedrockProvisioningError,
    ProvisioningErrorClassification,
    ProvisioningInProgressError,
    provision_diaglob_knowledge_base,
    delete_diaglob_knowledge_base,
)

Base.metadata.create_all(bind=engine)

logger = logging.getLogger(__name__)

PROVISIONING_RETRY_DELAYS_SECONDS = (0, 60, 300, 900)


def run_knowledge_base_provisioning(knowledge_base_id: int) -> None:
    """Provision in the background so customers never wait on AWS setup."""
    for attempt, delay in enumerate(PROVISIONING_RETRY_DELAYS_SECONDS, start=1):
        if delay:
            time.sleep(delay)
        db = SessionLocal()
        try:
            knowledge_base = db.get(KnowledgeBase, knowledge_base_id)
            if not knowledge_base or knowledge_base.external_status == "ready":
                return
            try:
                provision_diaglob_knowledge_base(db, knowledge_base)
                logger.info(
                    "knowledge_base_provisioning_attempt_succeeded organization_id=%s knowledge_base_id=%s attempt=%s",
                    knowledge_base.organization_id, knowledge_base.id, attempt,
                )
                return
            except ProvisioningInProgressError:
                return
            except BedrockProvisioningError as error:
                retry_scheduled = (
                    error.classification in {
                        ProvisioningErrorClassification.RETRYABLE_INFRASTRUCTURE,
                        ProvisioningErrorClassification.PLATFORM_CONFIGURATION_ERROR,
                    }
                    and attempt < len(PROVISIONING_RETRY_DELAYS_SECONDS)
                )
                logger.error(
                    "knowledge_base_provisioning_attempt_failed organization_id=%s knowledge_base_id=%s attempt=%s stage=%s classification=%s retry_scheduled=%s",
                    knowledge_base.organization_id, knowledge_base.id, attempt,
                    error.resource, error.classification, retry_scheduled,
                )
                if retry_scheduled:
                    knowledge_base.external_status = "retrying"
                    knowledge_base.provisioning_stage = "retrying"
                    knowledge_base.provisioning_stage_started_at = datetime.now(timezone.utc)
                    db.commit()
                else:
                    return
        finally:
            db.close()


def schedule_knowledge_base_provisioning(knowledge_base_id: int) -> None:
    """Run startup recovery outside the request lifecycle."""
    threading.Thread(
        target=run_knowledge_base_provisioning,
        args=(knowledge_base_id,),
        daemon=True,
    ).start()


def reconcile_knowledge_base_provisioning() -> None:
    """Resume stranded non-terminal provisioning after a process restart."""
    db = SessionLocal()
    try:
        try:
            knowledge_bases = db.query(KnowledgeBase).filter(
                KnowledgeBase.active.is_(True),
                KnowledgeBase.external_status.in_(("pending", "provisioning", "retrying")),
            ).all()
        except OperationalError as error:
            db.rollback()
            if "no such column" in str(error).lower() and "knowledge_bases.external_status" in str(error):
                logger.warning("Skipping Knowledge Base provisioning reconciliation until migration 007 is applied")
                return
            raise
        now = datetime.now(timezone.utc)
        for knowledge_base in knowledge_bases:
            if knowledge_base.external_status == "provisioning":
                knowledge_base.external_status = "retrying"
                knowledge_base.provisioning_stage = "retrying"
                knowledge_base.provisioning_stage_started_at = now
        db.commit()
        for knowledge_base in knowledge_bases:
            logger.info(
                "Reconciling Knowledge Base provisioning: organization_id=%s knowledge_base_id=%s status=%s",
                knowledge_base.organization_id,
                knowledge_base.id,
                knowledge_base.external_status,
            )
            schedule_knowledge_base_provisioning(knowledge_base.id)
    finally:
        db.close()

app = FastAPI(
    title="Diaglob API",
    version="0.5.0",
    description="Backend API for Diaglob",
)


@app.on_event("startup")
def reconcile_knowledge_base_provisioning_on_startup() -> None:
    reconcile_knowledge_base_provisioning()


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "https://diaglob.tech",
        "https://www.diaglob.tech",
        "https://app.diaglob.tech",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# SECURITY HEADERS MIDDLEWARE
# ============================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next,
    ) -> Response:
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )

        return response


app.add_middleware(SecurityHeadersMiddleware)


# ============================================================
# RATE LIMITING (simple in-memory)
# ============================================================

import time
from collections import defaultdict

_rate_limit_store: dict[str, list[float]] = defaultdict(list)

RATE_LIMIT_RULES = {
    "/api/auth/login": (10, 60),
    "/api/auth/register": (5, 60),
    "/api/billing/checkout": (10, 60),
    "/api/billing/upgrade": (10, 60),
    "/api/billing/upgrade/preview": (20, 60),
    "/api/billing/downgrade": (10, 60),
    "/webhooks/whatsapp": (100, 60),
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next,
    ) -> Response:
        path = request.url.path
        client_ip = (
            request.client.host
            if request.client
            else "unknown"
        )

        rule = RATE_LIMIT_RULES.get(path)

        if rule:
            max_requests, window_seconds = rule
            key = f"{path}:{client_ip}"
            now = time.time()

            _rate_limit_store[key] = [
                t
                for t in _rate_limit_store[key]
                if now - t < window_seconds
            ]

            if len(_rate_limit_store[key]) >= max_requests:
                response = Response(
                    content='{"detail":"Rate limit exceeded"}',
                    status_code=429,
                    media_type="application/json",
                )
                origin = request.headers.get("origin", "")
                allowed_origins = [
                    "http://localhost:5173",
                    "http://127.0.0.1:5173",
                    "http://localhost:5174",
                    "http://127.0.0.1:5174",
                    "https://diaglob.tech",
                    "https://www.diaglob.tech",
                    "https://app.diaglob.tech",
                ]
                if origin in allowed_origins:
                    response.headers["Access-Control-Allow-Origin"] = origin
                    response.headers["Access-Control-Allow-Credentials"] = "true"
                return response

            _rate_limit_store[key].append(now)

        return await call_next(request)


app.add_middleware(RateLimitMiddleware)


class ProductVariantCreate(BaseModel):
    title: str
    sku: str | None = None
    barcode: str | None = None
    price: float
    currency: str | None = None
    inventory_quantity: int = 0
    available: bool = True
    shopify_variant_id: str | None = None


class ProductCreate(BaseModel):
    title: str
    handle: str | None = None
    description: str = ""
    image_url: str | None = None
    vendor: str | None = None
    product_type: str | None = None
    active: bool = True
    shopify_product_id: str | None = None
    variants: list[ProductVariantCreate] = []


class ProductSearchRequest(BaseModel):
    query: str
    limit: int = 10


class BillingAutoRenewRequest(BaseModel):
    enabled: bool


class BillingCheckoutRequest(BaseModel):
    plan: str
    billing_period_months: int = 1

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


class ShopifyConnectRequest(BaseModel):
    shop_domain: str


class DropiConnectRequest(BaseModel):
    api_token: str


class WhatsAppConnectRequest(BaseModel):
    phone_number_id: str
    business_account_id: str
    access_token: str


class RegistrationProvisionRequest(BaseModel):
    name: str
    organization_name: str | None = None


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


class MessageCreate(BaseModel):
    text: str
    sender: str = "human"


class AgentAskRequest(BaseModel):
    question: str
    number_of_results: int = 5


class AgentCreate(BaseModel):
    name: str
    role: str
    active: bool = True
    store_ids: list[int] = []
    knowledge_base_ids: list[int] = []


class AgentUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    active: bool | None = None
    store_ids: list[int] | None = None
    knowledge_base_ids: list[int] | None = None


class KnowledgeBaseCreate(BaseModel):
    name: str
    scope: str = "selected_stores"
    active: bool = True
    store_ids: list[int] = []


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = None
    scope: str | None = None
    active: bool | None = None
    store_ids: list[int] | None = None


class AutomationCreate(BaseModel):
    name: str
    description: str | None = None
    store_id: int | None = None
    active: bool = True
    trigger_type: str = "manual"
    conditions_json: list[dict] = []
    actions_json: list[dict] = []


class AutomationUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    store_id: int | None = None
    active: bool | None = None
    trigger_type: str | None = None
    conditions_json: list[dict] | None = None
    actions_json: list[dict] | None = None


class AutomationRunRequest(BaseModel):
    event_type: str = "manual"
    payload: dict = {}


class AutomationCampaignPayload(BaseModel):
    name: str
    automation_type: str = "custom"
    status: str = "draft"
    audience_type: str = "dynamic"
    audience_filters: dict = {}
    member_ids: list[int] = []
    selection_mode: str = "explicit"
    selected_customer_ids: list[int] = []
    excluded_customer_ids: list[int] = []
    schedule_type: str = "once"
    schedule_config: dict = {}
    timezone: str | None = None
    send_window_start: str | None = None
    send_window_end: str | None = None
    cooldown_days: int = 0
    channel: str = "whatsapp"
    message_template: str = ""
    message_mode: str = "free_form"
    whatsapp_template_id: int | None = None
    template_variables: dict = {}


class AudiencePreviewRequest(BaseModel):
    audience_type: str = "dynamic"
    audience_filters: dict = {}
    member_ids: list[int] = []
    selection_mode: str = "explicit"
    selected_customer_ids: list[int] = []
    excluded_customer_ids: list[int] = []


bearer_scheme = HTTPBearer(
    auto_error=False,
)





@app.post("/api/register/provision")
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

            ensure_member_capacity(
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


def get_active_member_usage(
    db: Session,
    organization_id: int,
):
    """
    Cuenta los miembros activos de toda la organización.

    El owner también consume un cupo.
    Miembros inactivos no consumen capacidad.
    """

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
    """
    Valida capacidad global de miembros
    para toda la organización.
    """

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
        get_active_member_usage(
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
                        "Suspende una tienda o mejora "
                        "tu plan para activar otra."
                    ),

                "resource":
                    "stores",

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
        # ====================================================
        # RBAC
        # ====================================================

        if not has_permission(
            membership.role,
            permission,
        ):
            raise HTTPException(
                status_code=403,
                detail="Permission denied",
            )

        # ====================================================
        # SUSCRIPCIÓN
        #
        # Los GET siguen disponibles para permitir
        # navegación y consulta en modo lectura.
        #
        # Las acciones operativas requieren plan activo.
        #
        # billing.write queda permitido porque un usuario
        # sin plan necesita poder comprar uno.
        # ====================================================

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


def serialize_knowledge_source(
    source: KnowledgeSource,
):
    return {
        "id": source.id,
        "organization_id": source.organization_id,
        "knowledge_base_id": source.knowledge_base_id,
        "name": source.name,
        "source_type": source.source_type,
        "content_type": source.content_type,
        "size_bytes": source.size_bytes,
        "status": source.status,
        "ingestion_job_id": source.ingestion_job_id,
        "error_message": source.error_message,
        "active": source.active,
        "created_at": (
            source.created_at.isoformat()
            if source.created_at
            else None
        ),
        "external_id": source.external_id,
        "external_name": source.external_name,
        "sheet_name": source.sheet_name,
        "last_synced_at": (
            source.last_synced_at.isoformat()
            if source.last_synced_at
            else None
        ),
        "sync_status": source.sync_status,
        "sync_error": source.sync_error,
        "external_mime_type": source.external_mime_type,
        "external_modified_at": (
            source.external_modified_at.isoformat()
            if source.external_modified_at
            else None
        ),
        "parent_source_id": source.parent_source_id,
        "external_size": source.external_size,
        "sync_generation": source.sync_generation,
    }


def serialize_knowledge_base(
    knowledge_base: KnowledgeBase,
):
    return {
        "id": knowledge_base.id,
        "organization_id": knowledge_base.organization_id,
        "name": knowledge_base.name,
        "scope": knowledge_base.scope,
        "external_id": knowledge_base.external_id,
        "external_status": knowledge_base.external_status,
        "external_last_error": knowledge_base.external_last_error,
        "provisioning_stage": knowledge_base.provisioning_stage,
        "provisioning_started_at": (
            knowledge_base.provisioning_started_at.isoformat()
            if knowledge_base.provisioning_started_at
            else None
        ),
        "provisioning_stage_started_at": (
            knowledge_base.provisioning_stage_started_at.isoformat()
            if knowledge_base.provisioning_stage_started_at
            else None
        ),
        "active": knowledge_base.active,
        "stores": [
            serialize_store_short(store)
            for store in knowledge_base.stores
            if store.active
        ],
        "agents": [
            {
                "id": agent.id,
                "name": agent.name,
                "role": agent.role,
                "active": agent.active,
            }
            for agent in knowledge_base.agents
        ],
    }


def _require_knowledge_base_ready(
    db: Session,
    organization_id: int,
    knowledge_base_id: int,
) -> KnowledgeBase:
    knowledge_base = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.organization_id == organization_id,
        )
        .first()
    )
    if not knowledge_base:
        raise HTTPException(
            status_code=404,
            detail="Knowledge Base not found",
        )
    if (
        knowledge_base.external_status != "ready"
        or not knowledge_base.external_id
        or not knowledge_base.external_data_source_id
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "KNOWLEDGE_BASE_NOT_READY",
                "message": "Knowledge Base provisioning is not ready.",
                "status": knowledge_base.external_status or "pending",
            },
        )
    return knowledge_base


def serialize_agent(
    agent: Agent,
):
    return {
        "id": agent.id,
        "organization_id": agent.organization_id,
        "name": agent.name,
        "role": agent.role,
        "active": agent.active,
        "stores": [
            serialize_store_short(store)
            for store in agent.stores
            if store.active
        ],
        "knowledge_bases": [
            {
                "id": knowledge_base.id,
                "name": knowledge_base.name,
                "scope": knowledge_base.scope,
                "active": knowledge_base.active,
            }
            for knowledge_base in agent.knowledge_bases
        ],
    }


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


def resolve_member_stores(
    membership: OrganizationMembership,
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
            == membership.organization_id,
            Store.id.in_(requested_ids),
            Store.active.is_(True),
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
            detail="One or more stores are invalid",
        )

    allowed_ids = get_allowed_store_ids(
        membership
    )

    if (
        allowed_ids is not None
        and not set(requested_ids).issubset(
            set(allowed_ids)
        )
    ):
        raise HTTPException(
            status_code=403,
            detail="Store access denied",
        )

    return stores


def resolve_organization_knowledge_bases(
    organization_id: int,
    knowledge_base_ids: list[int],
    db: Session,
):
    requested_ids = sorted(
        set(knowledge_base_ids)
    )

    if not requested_ids:
        return []

    knowledge_bases = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.organization_id
            == organization_id,
            KnowledgeBase.id.in_(requested_ids),
        )
        .all()
    )

    found_ids = {
        knowledge_base.id
        for knowledge_base in knowledge_bases
    }

    if found_ids != set(requested_ids):
        raise HTTPException(
            status_code=400,
            detail="One or more knowledge bases are invalid",
        )

    return knowledge_bases


def get_allowed_store_ids(
    membership: OrganizationMembership,
):
    if membership.all_stores:
        return None

    return [
        store.id
        for store in membership.stores
        if store.active
    ]


@app.get("/")
def root():
    return {
        "name": "Diaglob API",
        "version": "0.5.0",
    }


@app.get("/health")
def health():
    db_status = "disconnected"

    try:
        with engine.connect() as conn:
            conn.execute(
                __import__(
                    "sqlalchemy",
                    fromlist=["text"],
                ).text("SELECT 1")
            )
            db_status = "connected"
    except Exception:
        db_status = "error"

    return {
        "status": "ok" if db_status == "connected" else "degraded",
        "service": "diaglob-api",
        "database": db_status,
        "multitenant": True,
        "multistore": True,
    }


# ============================================================
# TEAM
# ============================================================

TEAM_ROLES = {
    "manager",
    "operator",
    "analyst",
}


# ============================================================
# TEAM INVITATIONS
# ============================================================

@app.get("/api/team/invitations")
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


@app.post("/api/team/invitations")
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


@app.delete(
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


@app.get("/api/team")
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


@app.post("/api/team")
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


@app.delete("/api/team/{membership_id}")
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


@app.patch("/api/team/{membership_id}")
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


@app.get("/api/me")
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


@app.delete("/api/account")
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


@app.get("/api/me/organizations")
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




@app.post("/api/billing/webhook")
async def paddle_billing_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    raw_body = await request.body()

    signature = request.headers.get(
        "Paddle-Signature",
        "",
    )

    webhook_secret = os.getenv(
        "PADDLE_WEBHOOK_SECRET"
    )

    if not webhook_secret:
        raise HTTPException(
            status_code=503,
            detail=(
                "Paddle webhook secret "
                "not configured"
            ),
        )

    try:
        verify_paddle_signature(
            raw_body,
            signature,
            webhook_secret,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=401,
            detail=str(exc),
        ) from exc

    try:
        event = json.loads(
            raw_body.decode("utf-8")
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid webhook payload",
        ) from exc

    event_id = event.get(
        "event_id"
    )

    event_type = event.get(
        "event_type"
    )

    occurred_at_raw = event.get(
        "occurred_at"
    )

    data = event.get(
        "data"
    ) or {}

    if not event_id or not event_type:
        raise HTTPException(
            status_code=400,
            detail="Invalid Paddle event",
        )

    # ========================================================
    # EVENTOS QUE DIAGLOB PROCESA
    # ========================================================

    subscription_events = {
        "subscription.created",
        "subscription.activated",
        "subscription.updated",
        "subscription.past_due",
        "subscription.paused",
        "subscription.resumed",
        "subscription.canceled",
    }

    transaction_events = {
        "transaction.completed",
    }

    supported_events = (
        subscription_events
        | transaction_events
    )

    if event_type not in supported_events:
        return {
            "ok": True,
            "ignored": True,
            "event_type": event_type,
        }

    is_subscription_event = (
        event_type in subscription_events
    )

    is_transaction_event = (
        event_type in transaction_events
    )

    # ========================================================
    # IDENTIFICADORES DE PADDLE
    # ========================================================
    #
    # En subscription.*:
    #   data.id = subscription_id
    #
    # En transaction.completed:
    #   data.id = transaction_id
    #   data.subscription_id = subscription_id
    # ========================================================

    if is_subscription_event:
        subscription_id = data.get(
            "id"
        )
    else:
        subscription_id = data.get(
            "subscription_id"
        )

    transaction_id = None

    if is_transaction_event:
        transaction_id = data.get(
            "id"
        )

    customer_id = data.get(
        "customer_id"
    )

    custom_data = (
        data.get("custom_data")
        or {}
    )

    organization_id_raw = (
        custom_data.get(
            "organization_id"
        )
    )

    # ========================================================
    # BUSCAR ORGANIZACIÓN
    #
    # Prioridad:
    # 1. custom_data.organization_id
    # 2. subscription_id conocido
    # 3. customer_id conocido
    # ========================================================

    organization = None

    if organization_id_raw:
        try:
            organization_id = int(
                organization_id_raw
            )
        except (
            TypeError,
            ValueError,
        ):
            organization_id = None

        if organization_id is not None:
            organization = (
                db.query(Organization)
                .filter(
                    Organization.id
                    == organization_id
                )
                .first()
            )

    if (
        organization is None
        and subscription_id
    ):
        organization = (
            db.query(Organization)
            .filter(
                Organization.billing_subscription_id
                == subscription_id
            )
            .first()
        )

    if (
        organization is None
        and customer_id
    ):
        organization = (
            db.query(Organization)
            .filter(
                Organization.billing_customer_id
                == customer_id
            )
            .first()
        )

    if organization is None:
        return {
            "ok": True,
            "ignored": True,
            "reason":
                "organization_not_found",
            "event_type":
                event_type,
        }

    # ========================================================
    # PROTEGER SUSCRIPCION CANONICA
    # ========================================================
    #
    # Una organización solo puede tener una suscripción
    # administrada por DIAGLOB.
    #
    # Si llega un webhook de otra suscripción, por ejemplo
    # una suscripción duplicada creada accidentalmente,
    # no debe modificar plan, estado ni tiendas.
    # ========================================================

    if (
        subscription_id
        and organization.billing_subscription_id
        and subscription_id
        != organization.billing_subscription_id
    ):
        return {
            "ok": True,
            "ignored": True,
            "reason":
                "non_canonical_subscription",
            "event_type":
                event_type,
            "organization_id":
                organization.id,
            "subscription_id":
                subscription_id,
            "canonical_subscription_id":
                organization.billing_subscription_id,
        }

    # ========================================================
    # IDEMPOTENCIA
    # ========================================================

    if (
        organization.billing_last_event_id
        == event_id
    ):
        return {
            "ok": True,
            "duplicate": True,
            "event_type": event_type,
        }

    # ========================================================
    # FECHA DEL EVENTO
    # ========================================================

    occurred_at = None

    if occurred_at_raw:
        try:
            occurred_at = (
                datetime.fromisoformat(
                    occurred_at_raw.replace(
                        "Z",
                        "+00:00",
                    )
                )
                .replace(
                    tzinfo=None
                )
            )
        except ValueError:
            occurred_at = None

    if (
        occurred_at is not None
        and organization.billing_last_event_at
        is not None
        and occurred_at
        < organization.billing_last_event_at
    ):
        return {
            "ok": True,
            "ignored": True,
            "reason":
                "out_of_order_event",
            "event_type":
                event_type,
        }

    # ========================================================
    # PRECIO Y PLAN
    #
    # La estructura items[].price.id funciona tanto para
    # subscriptions como para transactions de Paddle.
    # ========================================================

    price_id = (
        get_subscription_price_id(
            data
        )
    )

    plan_key = None
    billing_period_months = None

    if price_id:
        plan_key = (
            get_plan_from_price_id(
                price_id
            )
        )

        billing_period_months = (
            get_billing_period_from_price_id(
                price_id
            )
        )

    # ========================================================
    # DATOS COMUNES DE BILLING
    # ========================================================

    organization.billing_provider = (
        "paddle"
    )

    if customer_id:
        organization.billing_customer_id = (
            customer_id
        )

    if subscription_id:
        organization.billing_subscription_id = (
            subscription_id
        )

    if price_id:
        organization.billing_price_id = (
            price_id
        )

    if (
        billing_period_months is not None
        and not organization.pending_plan
    ):
        organization.billing_period_months = (
            billing_period_months
        )

    # ========================================================
    # TRANSACTION.COMPLETED
    #
    # Vincula el pago real con la organización.
    #
    # IMPORTANTE:
    # NO modifica subscription_status.
    # Los eventos subscription.* son la autoridad del estado.
    # Tampoco activa/suspende tiendas.
    # ========================================================

    if is_transaction_event:

        if (
            organization.pending_plan
            and organization.pending_plan_effective_at
            and occurred_at is not None
            and occurred_at
            >= organization.pending_plan_effective_at
        ):
            target_plan = (
                organization.pending_plan
            )

            target_period = int(
                organization.pending_billing_period_months
                or organization.billing_period_months
                or 1
            )

            current_rank = (
                BILLING_PLAN_ORDER.get(
                    organization.plan,
                    0,
                )
            )

            target_rank = (
                BILLING_PLAN_ORDER.get(
                    target_plan,
                    0,
                )
            )

            is_plan_downgrade = (
                target_rank
                < current_rank
            )

            target_limit = int(
                get_limits_for_plan(
                    target_plan
                ).active_stores
            )

            # ====================================================
            # TIENDAS ELEGIDAS POR EL CLIENTE
            # ====================================================
            #
            # Pueden estar activas o suspendidas.
            #
            # Una tienda suspendida seleccionada se activará
            # cuando entre en vigencia el nuevo plan.
            #
            # Las eliminadas no son válidas.
            # ====================================================

            selected_all = (
                db.query(Store)
                .filter(
                    Store.organization_id
                    == organization.id,
                    Store.keep_on_pending_downgrade.is_(True),
                )
                .order_by(Store.id.asc())
                .all()
            )

            intended_selection_count = min(
                len(selected_all),
                target_limit,
            )

            selected_valid = [
                store
                for store in selected_all
                if not store.deleted
            ]

            selected_valid = (
                selected_valid[
                    :target_limit
                ]
            )

            keep_ids = {
                store.id
                for store in selected_valid
            }

            if not is_plan_downgrade:
                # En un cambio de período o upgrade programado
                # no modificamos el estado de las tiendas.
                keep_ids = {
                    store.id
                    for store in (
                        db.query(Store)
                        .filter(
                            Store.organization_id
                            == organization.id,
                            Store.deleted.is_(False),
                            Store.active.is_(True),
                        )
                        .all()
                    )
                }

                intended_selection_count = (
                    len(keep_ids)
                )

                selected_valid = []

            # ====================================================
            # FALLBACK
            # ====================================================
            #
            # Solo completamos cupos si una tienda que el cliente
            # había seleccionado fue eliminada.
            #
            # Si el cliente eligió voluntariamente menos tiendas
            # que el máximo del plan, respetamos esa decisión.
            #
            # El fallback usa únicamente tiendas que YA estén
            # activas, priorizando las que llevan más tiempo
            # activas.
            #
            # Nunca reactivamos una suspendida que no fue elegida.
            # ====================================================

            missing_selected = max(
                0,
                intended_selection_count
                - len(selected_valid),
            )

            if missing_selected > 0:
                fallback_stores = (
                    db.query(Store)
                    .filter(
                        Store.organization_id
                        == organization.id,
                        Store.deleted.is_(False),
                        Store.active.is_(True),
                        Store.id.notin_(keep_ids)
                        if keep_ids
                        else True,
                    )
                    .order_by(
                        Store.active_since.is_(None),
                        Store.active_since.asc(),
                        Store.id.asc(),
                    )
                    .limit(
                        missing_selected
                    )
                    .all()
                )

                for store in fallback_stores:
                    keep_ids.add(
                        store.id
                    )

            # ====================================================
            # APLICAR ESTADO FINAL
            # ====================================================

            stores = (
                db.query(Store)
                .filter(
                    Store.organization_id
                    == organization.id,
                    Store.deleted.is_(False),
                )
                .all()
            )

            for store in stores:
                should_be_active = (
                    store.id in keep_ids
                )

                if store.active != should_be_active:
                    store.active = (
                        should_be_active
                    )

            # Limpiar selección temporal.
            for store in selected_all:
                store.keep_on_pending_downgrade = False

            organization.plan = (
                target_plan
            )

            organization.billing_period_months = (
                target_period
            )

            organization.pending_plan = None
            organization.pending_billing_period_months = None
            organization.pending_plan_effective_at = None
            organization.pending_plan_prepared_at = None

        elif (
            plan_key
            and not organization.pending_plan
        ):
            organization.plan = (
                plan_key
            )

        organization.billing_last_event_id = (
            event_id
        )

        if occurred_at is not None:
            organization.billing_last_event_at = (
                occurred_at
            )

        db.commit()

        return {
            "ok": True,
            "event_type":
                event_type,
            "organization_id":
                organization.id,
            "transaction_id":
                transaction_id,
            "customer_id":
                organization.billing_customer_id,
            "subscription_id":
                organization.billing_subscription_id,
            "price_id":
                organization.billing_price_id,
            "plan":
                organization.plan,
            "subscription_status":
                organization.subscription_status,
        }

    # ========================================================
    # SUBSCRIPTION EVENTS
    # ========================================================

    status = data.get(
        "status"
    )

    if status:
        organization.subscription_status = (
            status
        )

    # Paddle es también la autoridad sobre
    # la renovación automática.
    if is_subscription_event:
        scheduled_change = (
            data.get("scheduled_change")
        )

        scheduled_action = (
            scheduled_change.get("action")
            if isinstance(
                scheduled_change,
                dict,
            )
            else None
        )

        if status == "canceled":
            organization.auto_renew_enabled = False

        elif scheduled_action == "cancel":
            organization.auto_renew_enabled = False

        elif status in {
            "active",
            "trialing",
        }:
            organization.auto_renew_enabled = True

    # Solo cambiamos el plan desde subscription.*
    # cuando Paddle nos entrega un Price ID reconocido
    # y la suscripción está en un estado válido.
    if (
        plan_key
        and status in {
            "active",
            "trialing",
            "past_due",
        }
    ):
        current_rank = (
            BILLING_PLAN_ORDER.get(
                organization.plan,
                0,
            )
        )

        incoming_rank = (
            BILLING_PLAN_ORDER.get(
                plan_key,
                0,
            )
        )

        pending_plan = (
            organization.pending_plan
        )

        pending_rank = (
            BILLING_PLAN_ORDER.get(
                pending_plan,
                0,
            )
            if pending_plan
            else 0
        )

        has_pending_change = bool(
            pending_plan
            and organization.pending_plan_effective_at
        )

        incoming_is_current_plan = (
            plan_key
            == organization.plan
        )

        incoming_is_pending_target = (
            has_pending_change
            and plan_key
            == pending_plan
        )

        # Mientras existe un cambio programado:
        #
        # Paddle puede notificar tanto el Price actual como el
        # Price futuro preparado por el worker.
        #
        # El plan/período de DIAGLOB no cambia hasta recibir
        # transaction.completed en la fecha efectiva.
        if (
            has_pending_change
            and (
                incoming_is_current_plan
                or incoming_is_pending_target
            )
        ):
            pass

        else:
            # Un plan superior representa un upgrade real.
            # También permite sincronizar cambios normales
            # cuando no existe un downgrade pendiente.
            organization.plan = (
                plan_key
            )

            organization.pending_plan = None
            organization.pending_billing_period_months = None
            organization.pending_plan_effective_at = None
            organization.pending_plan_prepared_at = None

            (
                db.query(Store)
                .filter(
                    Store.organization_id
                    == organization.id,
                )
                .update(
                    {
                        Store.keep_on_pending_downgrade:
                            False,
                    },
                    synchronize_session=False,
                )
            )

    # ========================================================
    # CANCELACIÓN / PAUSA
    #
    # No borramos datos.
    # Suspendemos las tiendas activas.
    # ========================================================

    if status in {
        "canceled",
        "paused",
    }:
        (
            db.query(Store)
            .filter(
                Store.organization_id
                == organization.id,
                Store.deleted.is_(False),
                Store.active.is_(True),
            )
            .update(
                {
                    Store.active: False,
                    Store.active_since: None,
                },
                synchronize_session=False,
            )
        )

    # Si la suscripción terminó realmente,
    # la organización queda sin plan contratado.
    if status == "canceled":
        organization.plan = "none"

    organization.billing_last_event_id = (
        event_id
    )

    if occurred_at is not None:
        organization.billing_last_event_at = (
            occurred_at
        )

    db.commit()

    return {
        "ok": True,
        "event_type":
            event_type,
        "organization_id":
            organization.id,
        "subscription_status":
            organization.subscription_status,
        "plan":
            organization.plan,
    }



# ============================================================
# BILLING - AUTO RENEW
# ============================================================

@app.patch("/api/billing/auto-renew")
def update_billing_auto_renew(
    payload: BillingAutoRenewRequest,
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
            detail="Billing access denied",
        )

    organization = membership.organization

    subscription_id = (
        organization.billing_subscription_id
    )

    if not subscription_id:
        raise HTTPException(
            status_code=409,
            detail=(
                "La organización no tiene una "
                "suscripción Paddle asociada."
            ),
        )

    status = (
        organization.subscription_status
        or ""
    ).strip().lower()

    if status not in {
        "active",
        "trialing",
    }:
        raise HTTPException(
            status_code=409,
            detail=(
                "La renovación automática solo puede "
                "modificarse mientras la suscripción "
                "está activa."
            ),
        )

    subscription_url = (
        f"{get_paddle_base_url()}"
        f"/subscriptions/{subscription_id}"
    )

    # --------------------------------------------------------
    # CONSULTAR ESTADO ACTUAL EN PADDLE
    # --------------------------------------------------------

    try:
        response = httpx.get(
            subscription_url,
            headers=get_paddle_headers(),
            timeout=30,
        )

    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "No fue posible consultar Paddle."
            ),
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={
                "message":
                    "Paddle rechazó la consulta "
                    "de la suscripción.",
                "paddle_status":
                    response.status_code,
                "paddle_response":
                    response.text,
            },
        )

    paddle_subscription = (
        response.json().get("data")
        or {}
    )

    scheduled_change = (
        paddle_subscription.get(
            "scheduled_change"
        )
    )

    scheduled_action = (
        scheduled_change.get("action")
        if isinstance(
            scheduled_change,
            dict,
        )
        else None
    )

    # ========================================================
    # ACTIVAR RENOVACIÓN
    # ========================================================

    if payload.enabled:

        # Ya está renovando normalmente.
        if scheduled_action is None:
            organization.auto_renew_enabled = True

            db.commit()

            return {
                "ok": True,
                "auto_renew_enabled": True,
                "scheduled_change": None,
                "message":
                    "La renovación automática ya está activa.",
            }

        # No debemos borrar silenciosamente un pause u otro
        # cambio que no haya sido creado por este control.
        if scheduled_action != "cancel":
            raise HTTPException(
                status_code=409,
                detail=(
                    "La suscripción tiene otro cambio "
                    "programado en Paddle y no puede "
                    "reactivarse automáticamente."
                ),
            )

        try:
            response = httpx.patch(
                subscription_url,
                headers=get_paddle_headers(),
                json={
                    "scheduled_change": None,
                },
                timeout=30,
            )

        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502,
                detail=(
                    "No fue posible reactivar "
                    "la renovación en Paddle."
                ),
            ) from exc

        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail={
                    "message":
                        "Paddle rechazó la reactivación "
                        "de la renovación.",
                    "paddle_status":
                        response.status_code,
                    "paddle_response":
                        response.text,
                },
            )

        paddle_data = (
            response.json().get("data")
            or {}
        )

        organization.auto_renew_enabled = True

        db.commit()

        return {
            "ok": True,
            "auto_renew_enabled": True,
            "scheduled_change":
                paddle_data.get(
                    "scheduled_change"
                ),
            "next_billed_at":
                paddle_data.get(
                    "next_billed_at"
                ),
            "message":
                "Renovación automática activada.",
        }

    # ========================================================
    # DESACTIVAR RENOVACIÓN
    # ========================================================

    if scheduled_action == "cancel":

        organization.auto_renew_enabled = False

        db.commit()

        return {
            "ok": True,
            "auto_renew_enabled": False,
            "scheduled_change":
                scheduled_change,
            "effective_at":
                scheduled_change.get(
                    "effective_at"
                ),
            "message":
                "La renovación ya estaba desactivada.",
        }

    if scheduled_action is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "La suscripción ya tiene otro "
                "cambio programado en Paddle."
            ),
        )

    cancel_url = (
        f"{subscription_url}/cancel"
    )

    try:
        response = httpx.post(
            cancel_url,
            headers=get_paddle_headers(),
            json={
                "effective_from":
                    "next_billing_period",
            },
            timeout=30,
        )

    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "No fue posible programar "
                "la cancelación en Paddle."
            ),
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={
                "message":
                    "Paddle rechazó la cancelación "
                    "programada.",
                "paddle_status":
                    response.status_code,
                "paddle_response":
                    response.text,
            },
        )

    paddle_data = (
        response.json().get("data")
        or {}
    )

    scheduled_change = (
        paddle_data.get(
            "scheduled_change"
        )
        or {}
    )

    # Una cancelación futura hace irrelevante
    # cualquier downgrade interno pendiente.
    organization.pending_plan = None
    organization.pending_billing_period_months = None
    organization.pending_plan_effective_at = None
    organization.pending_plan_prepared_at = None

    (
        db.query(Store)
        .filter(
            Store.organization_id
            == organization.id,
        )
        .update(
            {
                Store.keep_on_pending_downgrade:
                    False,
            },
            synchronize_session=False,
        )
    )

    organization.auto_renew_enabled = False

    db.commit()

    return {
        "ok": True,
        "auto_renew_enabled": False,
        "scheduled_change":
            paddle_data.get(
                "scheduled_change"
            ),
        "effective_at":
            scheduled_change.get(
                "effective_at"
            ),
        "next_billed_at":
            paddle_data.get(
                "next_billed_at"
            ),
        "message":
            "Renovación automática desactivada.",
    }


# ============================================================
# BILLING - PLAN UPGRADES
# ============================================================

class BillingUpgradeRequest(BaseModel):
    plan: str


BILLING_PLAN_ORDER = {
    "starter": 1,
    "growth": 2,
    "pro": 3,
    "scale": 4,
}


def get_paddle_base_url():
    environment = (
        os.getenv(
            "PADDLE_ENVIRONMENT",
            "sandbox",
        )
        .strip()
        .lower()
    )

    if environment == "production":
        return "https://api.paddle.com"

    return "https://sandbox-api.paddle.com"


def get_paddle_headers():
    api_key = os.getenv("PADDLE_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Paddle API key not configured",
        )

    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def get_billing_price_id(
    plan_key: str,
    billing_period_months: int = 1,
):
    try:
        return get_paddle_price_id(
            plan_key,
            billing_period_months,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


def validate_plan_upgrade(
    organization: Organization,
    target_plan: str,
):
    import logging as _vpu_log
    logger = _vpu_log.getLogger(__name__)

    current_plan = (
        organization.plan
        or "none"
    ).strip().lower()

    target_plan = target_plan.strip().lower()

    if target_plan not in BILLING_PLAN_ORDER:
        logger.warning(
            "billing.preview.rejected org=%s reason=invalid_target_plan current=%s target=%s",
            organization.id,
            current_plan,
            target_plan,
        )
        raise HTTPException(
            status_code=400,
            detail="Invalid target plan",
        )

    if current_plan not in BILLING_PLAN_ORDER:
        logger.warning(
            "billing.preview.rejected org=%s reason=no_active_subscription current=%s",
            organization.id,
            current_plan,
        )
        raise HTTPException(
            status_code=409,
            detail=(
                "No tienes una suscripcion activa "
                "para actualizar. Usa el checkout normal."
            ),
        )

    if (
        BILLING_PLAN_ORDER[target_plan]
        <= BILLING_PLAN_ORDER[current_plan]
    ):
        logger.warning(
            "billing.preview.rejected org=%s reason=not_upgrade current=%s target=%s",
            organization.id,
            current_plan,
            target_plan,
        )
        raise HTTPException(
            status_code=409,
            detail=(
                "Este endpoint solo permite "
                "escalar hacia un plan superior."
            ),
        )

    return (
        current_plan,
        target_plan,
    )



@app.post("/api/billing/upgrade/preview")
def preview_billing_upgrade(
    payload: BillingUpgradeRequest,
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
            detail="Billing access denied",
        )

    organization = (
        db.query(Organization)
        .filter(
            Organization.id
            == membership.organization_id
        )
        .first()
    )

    if not organization:
        raise HTTPException(
            status_code=404,
            detail="Organization not found",
        )

    try:
        (
            current_plan,
            target_plan,
        ) = validate_plan_upgrade(
            organization,
            payload.plan,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    import logging as _log
    logger = _log.getLogger(__name__)
    logger.info(
        "billing.preview org=%s current=%s target=%s",
        organization.id,
        current_plan,
        target_plan,
    )

    if (
        organization.subscription_status
        and organization.subscription_status
        not in {"active", "trialing"}
    ):
        logger.warning(
            "billing.preview.rejected org=%s reason=subscription_not_active status=%s",
            organization.id,
            organization.subscription_status,
        )
        raise HTTPException(
            status_code=409,
            detail=(
                "La suscripcion debe estar activa "
                "para realizar un upgrade."
            ),
        )

    paddle_api_key = os.getenv("PADDLE_API_KEY")

    if (
        paddle_api_key
        and organization.billing_subscription_id
    ):
        try:
            target_price_id = get_paddle_price_id(
                target_plan,
                organization.billing_period_months,
            )
        except ValueError:
            _log.getLogger(__name__).warning(
                "billing.preview paddle_price_unavailable org=%s plan=%s period=%s",
                organization.id,
                target_plan,
                organization.billing_period_months,
            )
            target_price_id = None

        if target_price_id:
            body = {
                "items": [
                    {
                        "price_id": target_price_id,
                        "quantity": 1,
                    }
                ],
                "proration_billing_mode":
                    "prorated_immediately",
                "on_payment_failure":
                    "prevent_change",
            }

            try:
                response = httpx.patch(
                    (
                        f"{get_paddle_base_url()}"
                        f"/subscriptions/"
                        f"{organization.billing_subscription_id}"
                        f"/preview"
                    ),
                    headers=get_paddle_headers(),
                    json=body,
                    timeout=30,
                )
            except httpx.RequestError:
                response = None

            if response is not None and response.status_code < 400:
                paddle_data = (
                    response.json().get("data")
                    or {}
                )

                immediate_transaction = (
                    paddle_data.get(
                        "immediate_transaction"
                    )
                    or {}
                )

                details = (
                    immediate_transaction.get("details")
                    or {}
                )

                totals = (
                    details.get("totals")
                    or {}
                )

                line_items = (
                    details.get("line_items")
                    or []
                )

                charge_amount = 0
                credit_amount = 0

                for line_item in line_items:
                    line_totals = (
                        line_item.get("totals")
                        or {}
                    )

                    try:
                        line_total = int(
                            line_totals.get("total")
                            or 0
                        )
                    except (
                        TypeError,
                        ValueError,
                    ):
                        line_total = 0

                    if line_total > 0:
                        charge_amount += line_total

                    elif line_total < 0:
                        credit_amount += abs(
                            line_total
                        )

                try:
                    result_amount = int(
                        totals.get("total")
                        or 0
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    result_amount = 0

                currency_code = (
                    totals.get("currency_code")
                    or "USD"
                )

                if result_amount > 0:
                    result_action = "charge"

                elif result_amount < 0:
                    result_action = "credit"

                else:
                    result_action = "none"

                normalized_update_summary = {
                    "charge": {
                        "amount": str(
                            charge_amount
                        ),
                        "currency_code":
                            currency_code,
                    },
                    "credit": {
                        "amount": str(
                            credit_amount
                        ),
                        "currency_code":
                            currency_code,
                    },
                    "result": {
                        "action":
                            result_action,
                        "amount": str(
                            abs(result_amount)
                        ),
                        "currency_code":
                            currency_code,
                    },
                }

                next_transaction = (
                    paddle_data.get(
                        "next_transaction"
                    )
                    or {}
                )

                next_billing_period = (
                    next_transaction.get(
                        "billing_period"
                    )
                    or {}
                )

                return {
                    "current_plan": current_plan,
                    "target_plan": target_plan,
                    "subscription_id":
                        organization.billing_subscription_id,
                    "next_billed_at":
                        (
                            paddle_data.get(
                                "next_billed_at"
                            )
                            or next_billing_period.get(
                                "starts_at"
                            )
                        ),
                    "currency_code":
                        currency_code,
                    "amount_due":
                        str(result_amount),
                    "subtotal":
                        totals.get("subtotal"),
                    "tax":
                        totals.get("tax"),
                    "update_summary":
                        normalized_update_summary,
                    "immediate_transaction":
                        immediate_transaction,
                    "next_transaction":
                        paddle_data.get(
                            "next_transaction"
                        ),
                }

    # ============================================================
    # FALLBACK: LOCAL PRORATION CALCULATION
    # ============================================================
    # Used when:
    #   - Paddle API key not configured
    #   - No billing subscription yet
    #   - Paddle API unreachable
    # ============================================================

    from datetime import timedelta

    billing_period = (
        organization.billing_period_months or 1
    )

    now = datetime.utcnow()

    period_end = (
        now + timedelta(days=30 * billing_period)
    )

    period_start = (
        now - timedelta(days=30 * billing_period)
    )

    local_preview = calculate_local_proration(
        current_plan=current_plan,
        target_plan=target_plan,
        billing_period_months=billing_period,
        current_period_start=period_start,
        current_period_end=period_end,
        now=now,
    )

    amount_cents = int(
        float(local_preview["amount_due_now"]) * 100
    )

    credit_cents = int(
        float(local_preview["credit"]) * 100
    )

    charge_cents = int(
        float(local_preview["charge"]) * 100
    )

    return {
        "current_plan": current_plan,
        "target_plan": target_plan,
        "subscription_id":
            organization.billing_subscription_id,
        "next_billed_at":
            local_preview["next_billed_at"],
        "currency_code":
            local_preview["currency"],
        "amount_due":
            str(amount_cents),
        "subtotal": None,
        "tax": None,
        "update_summary": {
            "charge": {
                "amount": str(charge_cents),
                "currency_code":
                    local_preview["currency"],
            },
            "credit": {
                "amount": str(credit_cents),
                "currency_code":
                    local_preview["currency"],
            },
            "result": {
                "action": (
                    "charge"
                    if amount_cents > 0
                    else "none"
                ),
                "amount": str(abs(amount_cents)),
                "currency_code":
                    local_preview["currency"],
            },
        },
        "immediate_transaction": None,
        "next_transaction": None,
        "_source": "local",
    }


@app.post("/api/billing/upgrade")
def apply_billing_upgrade(
    payload: BillingUpgradeRequest,
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
            detail="Billing access denied",
        )

    organization = (
        db.query(Organization)
        .filter(
            Organization.id
            == membership.organization_id
        )
        .first()
    )

    if not organization:
        raise HTTPException(
            status_code=404,
            detail="Organization not found",
        )

    (
        current_plan,
        target_plan,
    ) = validate_plan_upgrade(
        organization,
        payload.plan,
    )

    target_price_id = get_paddle_price_id(
        target_plan,
        organization.billing_period_months,
    )

    body = {
        "items": [
            {
                "price_id": target_price_id,
                "quantity": 1,
            }
        ],
        "proration_billing_mode":
            "prorated_immediately",
        "on_payment_failure":
            "prevent_change",
        "custom_data": {
            "organization_id":
                str(organization.id),
            "plan":
                target_plan,
        },
    }

    try:
        response = httpx.patch(
            (
                f"{get_paddle_base_url()}"
                f"/subscriptions/"
                f"{organization.billing_subscription_id}"
            ),
            headers=get_paddle_headers(),
            json=body,
            timeout=45,
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail="Unable to contact Paddle",
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={
                "message":
                    "Unable to upgrade Paddle subscription",
                "paddle_status":
                    response.status_code,
                "paddle_response":
                    response.text,
            },
        )

    paddle_data = (
        response.json().get("data")
        or {}
    )

    # Paddle confirmó el upgrade.
    #
    # Sincronizamos DIAGLOB inmediatamente para que la UI
    # no dependa de que el webhook llegue en ese instante.
    #
    # Los webhooks siguen siendo autoridad para eventos
    # posteriores y cambios externos.

    paddle_price_id = (
        get_subscription_price_id(
            paddle_data
        )
        or target_price_id
    )

    confirmed_plan = (
        get_plan_from_price_id(
            paddle_price_id
        )
        if paddle_price_id
        else None
    )

    organization.plan = (
        confirmed_plan
        or target_plan
    )

    organization.billing_price_id = (
        paddle_price_id
    )

    confirmed_period = (
        get_billing_period_from_price_id(
            paddle_price_id
        )
        if paddle_price_id
        else None
    )

    if confirmed_period is not None:
        organization.billing_period_months = (
            confirmed_period
        )

    organization.pending_plan = None
    organization.pending_billing_period_months = None
    organization.pending_plan_effective_at = None
    organization.pending_plan_prepared_at = None

    (
        db.query(Store)
        .filter(
            Store.organization_id
            == organization.id,
        )
        .update(
            {
                Store.keep_on_pending_downgrade:
                    False,
            },
            synchronize_session=False,
        )
    )

    db.commit()
    db.refresh(organization)

    return {
        "ok": True,
        "current_plan": current_plan,
        "target_plan": target_plan,
        "subscription_id":
            organization.billing_subscription_id,
        "paddle_status":
            paddle_data.get("status"),
        "next_billed_at":
            paddle_data.get("next_billed_at"),
        "message":
            "Upgrade enviado a Paddle",
    }




# ============================================================
# BILLING - PLAN DOWNGRADES
# ============================================================

class BillingDowngradeRequest(BaseModel):
    plan: str
    billing_period_months: int | None = None
    store_ids: list[int] | None = None


def validate_plan_downgrade(
    organization: Organization,
    target_plan: str,
    db: Session,
    target_billing_period_months: int | None = None,
):
    current_plan = (
        organization.plan
        or "none"
    ).lower()

    target_plan = (
        target_plan
        or ""
    ).strip().lower()

    if target_plan not in BILLING_PLAN_ORDER:
        raise HTTPException(
            status_code=400,
            detail="Plan de destino inválido",
        )

    current_rank = (
        BILLING_PLAN_ORDER.get(
            current_plan,
            0,
        )
    )

    target_rank = (
        BILLING_PLAN_ORDER.get(
            target_plan,
            0,
        )
    )

    if current_rank <= 0:
        raise HTTPException(
            status_code=400,
            detail="La organización no tiene un plan activo",
        )

    current_period = int(
        organization.billing_period_months
        or 1
    )

    target_period = int(
        target_billing_period_months
        or current_period
    )

    if target_period not in {
        1,
        3,
        6,
        12,
    }:
        raise HTTPException(
            status_code=400,
            detail="Período de facturación inválido",
        )

    plan_changes = (
        target_plan
        != current_plan
    )

    period_changes = (
        target_period
        != current_period
    )

    # ========================================================
    # MVP: EL PERÍODO DE UNA SUSCRIPCIÓN EXISTENTE ES FIJO
    # ========================================================
    #
    # El cliente puede cambiar de nivel de plan, pero debe
    # conservar siempre la duración contratada actualmente.
    #
    # Ejemplos:
    #
    # Starter 1M -> Growth 1M   permitido
    # Starter 1M -> Pro 1M      permitido
    # Starter 1M -> Starter 3M  bloqueado
    # Starter 1M -> Growth 3M   bloqueado
    # ========================================================

    if period_changes:
        raise HTTPException(
            status_code=409,
            detail=(
                "No puedes cambiar el período de facturación "
                "de una suscripción activa. Puedes cambiar de "
                "plan manteniendo tu período actual."
            ),
        )

    if not plan_changes:
        raise HTTPException(
            status_code=400,
            detail="No hay ningún cambio para realizar",
        )

    # Un upgrade que mantiene exactamente el mismo período
    # debe utilizar el flujo inmediato con prorrata.
    if (
        target_rank > current_rank
        and not period_changes
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Los upgrades con el mismo período "
                "deben realizarse con prorrata inmediata"
            ),
        )

    if (
        organization.subscription_status
        not in {
            "active",
            "trialing",
        }
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "La suscripción debe estar activa "
                "para programar el cambio"
            ),
        )

    if not organization.billing_subscription_id:
        raise HTTPException(
            status_code=409,
            detail="No existe una suscripción Paddle asociada",
        )

    if not organization.auto_renew_enabled:
        raise HTTPException(
            status_code=409,
            detail=(
                "Activa la renovación automática antes de "
                "programar un cambio de plan o período"
            ),
        )

    return (
        current_plan,
        target_plan,
        current_period,
        target_period,
    )


def get_downgrade_active_stores(
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
        .order_by(
            Store.active_since.is_(None),
            Store.active_since.asc(),
            Store.id.asc(),
        )
        .all()
    )


def configure_pending_downgrade_stores(
    db: Session,
    organization: Organization,
    target_plan: str,
    requested_store_ids: list[int] | None,
):
    target_limit = int(
        get_limits_for_plan(
            target_plan
        ).active_stores
    )

    available_stores = (
        db.query(Store)
        .filter(
            Store.organization_id
            == organization.id,
            Store.deleted.is_(False),
        )
        .order_by(Store.id.asc())
        .all()
    )

    available_ids = {
        store.id
        for store in available_stores
    }

    requested_ids = list(
        dict.fromkeys(
            requested_store_ids
            or []
        )
    )

    invalid_ids = [
        store_id
        for store_id in requested_ids
        if store_id not in available_ids
    ]

    if invalid_ids:
        raise HTTPException(
            status_code=400,
            detail=(
                "Una o más tiendas seleccionadas "
                "no están disponibles."
            ),
        )

    if len(requested_ids) > target_limit:
        raise HTTPException(
            status_code=400,
            detail=(
                f"El plan {target_plan} permite "
                f"máximo {target_limit} tiendas activas."
            ),
        )

    (
        db.query(Store)
        .filter(
            Store.organization_id
            == organization.id,
        )
        .update(
            {
                Store.keep_on_pending_downgrade:
                    False,
            },
            synchronize_session=False,
        )
    )

    if requested_ids:
        (
            db.query(Store)
            .filter(
                Store.organization_id
                == organization.id,
                Store.id.in_(
                    requested_ids
                ),
            )
            .update(
                {
                    Store.keep_on_pending_downgrade:
                        True,
                },
                synchronize_session=False,
            )
        )

    return {
        "target_store_limit":
            target_limit,

        "selected_store_ids":
            requested_ids,
    }


@app.post("/api/billing/downgrade/preview")
def preview_billing_downgrade(
    payload: BillingDowngradeRequest,
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
            detail="Billing access denied",
        )

    organization = (
        membership.organization
    )

    print(
        "[DOWNGRADE APPLY START]",
        "organization=",
        organization.id,
        "current_plan=",
        organization.plan,
        "target=",
        payload.plan,
        "store_ids=",
        payload.store_ids,
    )

    (
        current_plan,
        target_plan,
        current_period,
        target_period,
    ) = validate_plan_downgrade(
        organization,
        payload.plan,
        db,
        payload.billing_period_months,
    )

    price_id = (
        get_billing_price_id(
            target_plan,
            target_period,
        )
    )

    # ========================================================
    # PREVIEW SEGÚN TIPO DE CAMBIO
    # ========================================================
    #
    # Si cambia la duración:
    #
    #   1M -> 3M
    #   1M -> 6M
    #   3M -> 12M
    #
    # NO simulamos todavía el Price nuevo en Paddle.
    #
    # El cliente conserva exactamente su período actual hasta
    # current_billing_period.ends_at.
    #
    # DIAGLOB guardará el cambio como pendiente y el worker
    # actualizará Paddle cerca de esa renovación.
    #
    # Si la duración NO cambia, este endpoint corresponde a un
    # downgrade real de plan y conservamos el preview existente.
    # ========================================================

    is_period_change = (
        target_period
        != current_period
    )

    if is_period_change:
        url = (
            f"{get_paddle_base_url()}"
            f"/subscriptions/"
            f"{organization.billing_subscription_id}"
        )

        try:
            response = httpx.get(
                url,
                headers=get_paddle_headers(),
                timeout=30,
            )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502,
                detail=(
                    "No fue posible consultar Paddle: "
                    f"{exc}"
                ),
            )

        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail={
                    "message":
                        "Paddle rechazó la consulta de la suscripción",
                    "paddle_status":
                        response.status_code,
                    "paddle_response":
                        response.text,
                },
            )

        subscription_data = (
            response.json().get("data")
            or {}
        )

        current_billing_period = (
            subscription_data.get(
                "current_billing_period"
            )
            or {}
        )

        effective_at = (
            current_billing_period.get(
                "ends_at"
            )
        )

        if not effective_at:
            effective_at = (
                subscription_data.get(
                    "next_billed_at"
                )
            )

        if not effective_at:
            raise HTTPException(
                status_code=502,
                detail=(
                    "Paddle no devolvió la fecha de fin "
                    "del período actual"
                ),
            )

        paddle_data = {
            "next_billed_at":
                effective_at,
            "immediate_transaction":
                None,
            "next_transaction":
                None,
        }

    else:
        url = (
            f"{get_paddle_base_url()}"
            f"/subscriptions/"
            f"{organization.billing_subscription_id}"
            f"/preview"
        )

        body = {
            "items": [
                {
                    "price_id":
                        price_id,
                    "quantity":
                        1,
                }
            ],
            "proration_billing_mode":
                "do_not_bill",
            "on_payment_failure":
                "prevent_change",
        }

        try:
            response = httpx.patch(
                url,
                headers=get_paddle_headers(),
                json=body,
                timeout=30,
            )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502,
                detail=(
                    "No fue posible consultar Paddle: "
                    f"{exc}"
                ),
            )

        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail={
                    "message":
                        "Paddle rechazó el preview del downgrade",
                    "paddle_status":
                        response.status_code,
                    "paddle_response":
                        response.text,
                },
            )

        paddle_data = (
            response.json().get("data")
            or {}
        )

    available_stores = (
        db.query(Store)
        .filter(
            Store.organization_id
            == organization.id,
            Store.deleted.is_(False),
        )
        .order_by(
            Store.active.desc(),
            Store.active_since.is_(None),
            Store.active_since.asc(),
            Store.id.asc(),
        )
        .all()
    )

    target_store_limit = int(
        get_limits_for_plan(
            target_plan
        ).active_stores
    )

    return {
        "ok": True,

        "target_store_limit":
            target_store_limit,

        "requires_store_selection":
            bool(
                available_stores
                and (
                    BILLING_PLAN_ORDER.get(
                        target_plan,
                        0,
                    )
                    <
                    BILLING_PLAN_ORDER.get(
                        current_plan,
                        0,
                    )
                )
            ),

        "available_stores": [
            {
                "id":
                    store.id,
                "name":
                    store.name,
                "active":
                    bool(store.active),
                "active_since":
                    (
                        store.active_since.isoformat()
                        + "Z"
                        if store.active_since
                        else None
                    ),
            }
            for store in available_stores
        ],
        "current_plan":
            current_plan,
        "target_plan":
            target_plan,
        "current_billing_period_months":
            current_period,
        "target_billing_period_months":
            target_period,
        "subscription_id":
            organization.billing_subscription_id,
        "effective_at":
            paddle_data.get(
                "next_billed_at"
            ),
        "next_billed_at":
            paddle_data.get(
                "next_billed_at"
            ),
        "immediate_transaction":
            paddle_data.get(
                "immediate_transaction"
            ),
        "next_transaction":
            paddle_data.get(
                "next_transaction"
            ),
    }


@app.post("/api/billing/downgrade")
def apply_billing_downgrade(
    payload: BillingDowngradeRequest,
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
            detail="Billing access denied",
        )

    organization = (
        membership.organization
    )

    (
        current_plan,
        target_plan,
        current_period,
        target_period,
    ) = validate_plan_downgrade(
        organization,
        payload.plan,
        db,
        payload.billing_period_months,
    )

    subscription_id = (
        organization.billing_subscription_id
    )

    # ========================================================
    # CONFIGURAR TIENDAS DEL PLAN FUTURO
    # ========================================================

    is_plan_downgrade = (
        BILLING_PLAN_ORDER.get(
            target_plan,
            0,
        )
        <
        BILLING_PLAN_ORDER.get(
            current_plan,
            0,
        )
    )

    if is_plan_downgrade:
        selection = (
            configure_pending_downgrade_stores(
                db,
                organization,
                target_plan,
                payload.store_ids,
            )
        )
    else:
        # Cambio de período o upgrade + cambio de período:
        # las tiendas actuales permanecen intactas.
        (
            db.query(Store)
            .filter(
                Store.organization_id
                == organization.id,
            )
            .update(
                {
                    Store.keep_on_pending_downgrade:
                        False,
                },
                synchronize_session=False,
            )
        )

        selection = {
            "target_store_limit":
                int(
                    get_limits_for_plan(
                        target_plan
                    ).active_stores
                ),
            "selected_store_ids":
                [],
        }

    # ========================================================
    # CONSULTAR FECHA REAL DE RENOVACION EN PADDLE
    # ========================================================
    #
    # IMPORTANTE:
    # NO cambiamos el Price ID todavía.
    #
    # Paddle debe seguir viendo el plan ACTUAL durante todo
    # el período ya pagado para que:
    #
    # - los upgrades se calculen contra el plan actual;
    # - no alteremos la renovación antes de tiempo;
    # - el cliente conserve correctamente su servicio.
    # ========================================================

    get_url = (
        f"{get_paddle_base_url()}"
        f"/subscriptions/"
        f"{subscription_id}"
    )

    try:
        response = httpx.get(
            get_url,
            headers=get_paddle_headers(),
            timeout=30,
        )

    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "No fue posible consultar Paddle: "
                f"{exc}"
            ),
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={
                "message":
                    "No fue posible consultar la suscripción",
                "paddle_status":
                    response.status_code,
                "paddle_response":
                    response.text,
            },
        )

    paddle_data = (
        response.json().get("data")
        or {}
    )

    next_billed_at_raw = (
        paddle_data.get(
            "next_billed_at"
        )
    )

    if not next_billed_at_raw:
        raise HTTPException(
            status_code=409,
            detail=(
                "Paddle no informó la próxima "
                "fecha de renovación"
            ),
        )

    try:
        effective_at = (
            datetime.fromisoformat(
                next_billed_at_raw.replace(
                    "Z",
                    "+00:00",
                )
            )
            .replace(
                tzinfo=None
            )
        )

    except ValueError:
        raise HTTPException(
            status_code=502,
            detail=(
                "Paddle devolvió una fecha "
                "de renovación inválida"
            ),
        )

    # ========================================================
    # GUARDAR DOWNGRADE SOLO EN DIAGLOB
    # ========================================================

    organization.pending_plan = (
        target_plan
    )

    organization.pending_billing_period_months = (
        target_period
    )

    organization.pending_plan_effective_at = (
        effective_at
    )

    organization.pending_plan_prepared_at = None

    db.commit()

    db.refresh(organization)

    print(
        "[DOWNGRADE APPLY COMMIT]",
        "organization=",
        organization.id,
        "plan=",
        organization.plan,
        "pending=",
        organization.pending_plan,
        "effective=",
        organization.pending_plan_effective_at,
        "prepared=",
        organization.pending_plan_prepared_at,
    )

    return {
        "ok": True,

        "current_plan":
            current_plan,

        "pending_plan":
            target_plan,

        "pending_billing_period_months":
            target_period,

        "effective_at":
            next_billed_at_raw,

        "subscription_id":
            subscription_id,

        "selected_store_ids":
            selection.get(
                "selected_store_ids",
                [],
            ),

        "target_store_limit":
            selection.get(
                "target_store_limit",
            ),

        "paddle_status":
            paddle_data.get(
                "status"
            ),

        "message":
            (
                "Downgrade programado. "
                "Paddle conservará el plan actual "
                "hasta el procesamiento de la renovación."
            ),
    }


@app.delete("/api/billing/downgrade")
def cancel_billing_downgrade(
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
            detail="Billing access denied",
        )

    organization = (
        membership.organization
    )

    if not organization.pending_plan:
        return {
            "ok": True,
            "pending_plan": None,
        }

    # Paddle nunca fue modificado al programar el downgrade,
    # por lo tanto cancelar solo limpia el estado pendiente
    # dentro de DIAGLOB.

    organization.pending_plan = None
    organization.pending_billing_period_months = None
    organization.pending_plan_effective_at = None
    organization.pending_plan_prepared_at = None

    (
        db.query(Store)
        .filter(
            Store.organization_id
            == organization.id,
        )
        .update(
            {
                Store.keep_on_pending_downgrade:
                    False,
            },
            synchronize_session=False,
        )
    )

    db.commit()

    return {
        "ok": True,
        "pending_plan": None,
        "message":
            "Cambio de plan programado cancelado",
    }




# ============================================================
# BILLING - PROCESS PENDING DOWNGRADES
# ============================================================

def process_pending_downgrades(
    db: Session,
    now: datetime | None = None,
):
    now = (
        now
        or datetime.utcnow()
    )

    preparation_window = timedelta(
        hours=2
    )

    organizations = (
        db.query(Organization)
        .filter(
            Organization.pending_plan.isnot(None),
            Organization.pending_plan_effective_at.isnot(None),
            Organization.pending_plan_prepared_at.is_(None),
            Organization.billing_subscription_id.isnot(None),
        )
        .all()
    )

    results = []

    for organization in organizations:

        effective_at = (
            organization.pending_plan_effective_at
        )

        if not effective_at:
            continue

        prepare_at = (
            effective_at
            - preparation_window
        )

        if now < prepare_at:
            continue

        # Si ya pasó demasiado tiempo tampoco repetimos
        # cambios a ciegas. La renovación/webhook resolverá
        # el estado correspondiente.
        if now >= effective_at:
            results.append({
                "organization_id":
                    organization.id,
                "status":
                    "effective_time_reached",
            })

            continue

        target_plan = (
            organization.pending_plan
            or ""
        ).lower()

        if target_plan not in BILLING_PLAN_ORDER:
            results.append({
                "organization_id":
                    organization.id,
                "status":
                    "invalid_pending_plan",
            })

            continue

        target_period = int(
            organization.pending_billing_period_months
            or organization.billing_period_months
            or 1
        )

        if target_period not in {
            1,
            3,
            6,
            12,
        }:
            results.append({
                "organization_id":
                    organization.id,
                "status":
                    "invalid_pending_period",
                "pending_billing_period_months":
                    target_period,
            })

            continue

        try:
            target_price_id = (
                get_paddle_price_id(
                    target_plan,
                    target_period,
                )
            )

        except Exception as exc:
            results.append({
                "organization_id":
                    organization.id,
                "status":
                    "price_error",
                "error":
                    str(exc),
            })

            continue

        if not target_price_id:
            results.append({
                "organization_id":
                    organization.id,
                "status":
                    "price_not_configured",
                "pending_plan":
                    target_plan,
            })

            continue

        subscription_id = (
            organization.billing_subscription_id
        )

        url = (
            f"{get_paddle_base_url()}"
            f"/subscriptions/"
            f"{subscription_id}"
        )

        body = {
            "items": [
                {
                    "price_id":
                        target_price_id,
                    "quantity":
                        1,
                }
            ],

            "proration_billing_mode":
                "do_not_bill",

            "on_payment_failure":
                "prevent_change",

            "custom_data": {
                "organization_id":
                    str(organization.id),

                "pending_plan":
                    target_plan,

                "pending_billing_period_months":
                    target_period,

                "diaglob_plan_change":
                    "scheduled",
            },
        }

        try:
            response = httpx.patch(
                url,
                headers=get_paddle_headers(),
                json=body,
                timeout=30,
            )

        except httpx.HTTPError as exc:
            results.append({
                "organization_id":
                    organization.id,
                "status":
                    "paddle_network_error",
                "error":
                    str(exc),
            })

            continue

        if response.status_code >= 400:
            results.append({
                "organization_id":
                    organization.id,
                "status":
                    "paddle_rejected",
                "paddle_status":
                    response.status_code,
                "paddle_response":
                    response.text,
            })

            continue

        organization.pending_plan_prepared_at = (
            now
        )

        db.commit()

        results.append({
            "organization_id":
                organization.id,
            "status":
                "prepared",
            "current_plan":
                organization.plan,
            "pending_plan":
                target_plan,
            "pending_billing_period_months":
                target_period,
            "effective_at":
                effective_at.isoformat(),
            "prepared_at":
                now.isoformat(),
        })

    return results




@app.post("/api/internal/billing/process-downgrades")
def process_downgrades_internal(
    x_internal_secret: str | None = Header(
        None,
        alias="X-Internal-Secret",
    ),
    db: Session = Depends(get_db),
):
    expected_secret = (
        os.getenv(
            "DIAGLOB_INTERNAL_SECRET"
        )
    )

    if (
        not expected_secret
        or not x_internal_secret
        or not secrets.compare_digest(
            x_internal_secret,
            expected_secret,
        )
    ):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized internal request",
        )

    results = (
        process_pending_downgrades(
            db
        )
    )

    return {
        "ok": True,
        "processed":
            len(results),
        "results":
            results,
    }


@app.post("/api/billing/checkout")
def create_billing_checkout(
    payload: BillingCheckoutRequest,
    membership: OrganizationMembership = Depends(
        get_current_membership
    ),
):
    # El checkout debe estar disponible aunque
    # la organización todavía no tenga plan.
    #
    # Solo roles administrativos pueden contratar
    # o cambiar una suscripción.
    if membership.role not in {
        "owner",
        "manager",
    }:
        raise HTTPException(
            status_code=403,
            detail="Billing access denied",
        )

    organization = membership.organization

    if (
        organization.billing_subscription_id
        and organization.subscription_status
        in {
            "active",
            "trialing",
            "past_due",
        }
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "La organización ya tiene una suscripción activa. "
                "Usa upgrade o downgrade en lugar de crear "
                "un checkout nuevo."
            ),
        )

    plan_key = (
        payload.plan
        .strip()
        .lower()
    )

    if plan_key not in {
        "starter",
        "growth",
        "pro",
        "scale",
    }:
        raise HTTPException(
            status_code=400,
            detail="Plan inválido",
        )

    try:
        price_id = get_paddle_price_id(
            plan_key,
            payload.billing_period_months,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    api_key = os.getenv(
        "PADDLE_API_KEY"
    )

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "Paddle no está configurado"
            ),
        )

    organization = (
        membership.organization
    )

    body = {
        "items": [
            {
                "price_id": price_id,
                "quantity": 1,
            }
        ],
        "collection_mode":
            "automatic",
        "custom_data": {
            "organization_id":
                str(organization.id),
            "plan":
                plan_key,
            "billing_period_months":
                payload.billing_period_months,
        },
    }

    headers = {
        "Authorization":
            f"Bearer {api_key}",
        "Content-Type":
            "application/json",
    }

    environment = (
        os.getenv(
            "PADDLE_ENVIRONMENT",
            "sandbox",
        )
        .strip()
        .lower()
    )

    if environment == "production":
        base_url = (
            "https://api.paddle.com"
        )
    else:
        base_url = (
            "https://sandbox-api.paddle.com"
        )

    try:
        response = httpx.post(
            f"{base_url}/transactions",
            headers=headers,
            json=body,
            timeout=20,
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "No fue posible conectar "
                "con Paddle"
            ),
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={
                "message":
                    "Paddle rechazó "
                    "la transacción",
                "provider_response":
                    response.json(),
            },
        )

    data = response.json().get(
        "data",
        {}
    )

    checkout = (
        data.get("checkout")
        or {}
    )

    checkout_url = checkout.get(
        "url"
    )

    if not checkout_url:
        raise HTTPException(
            status_code=502,
            detail=(
                "Paddle no devolvió "
                "una URL de checkout"
            ),
        )

    return {
        "plan":
            plan_key,
        "transaction_id":
            data.get("id"),
        "checkout_url":
            checkout_url,
    }


@app.get("/api/organization")
def get_organization(
    membership: OrganizationMembership = Depends(
        get_current_membership
    ),
    db: Session = Depends(get_db),
):
    organization = membership.organization

    plan = get_plan(
        organization.plan
    )

    active_stores = (
        get_active_store_usage(
            db,
            organization.id,
        )
    )

    # ========================================================
    # BILLING PERIOD / NEXT RENEWAL
    # ========================================================
    #
    # La fecha viene directamente de Paddle.
    # Si Paddle no está configurado o no responde,
    # no bloqueamos /api/organization:
    # simplemente devolvemos next_billed_at = None.
    #
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


@app.get("/api/stores")
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

    # En el selector global solamente queremos
    # tiendas operativas.
    #
    # Configuración puede pedir también las
    # tiendas suspendidas.
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



def serialize_conversation(
    conversation: Conversation,
):
    customer = conversation.customer
    store = conversation.store

    profile = next(
        (
            item
            for item in customer.store_profiles
            if item.store_id == store.id
        ),
        None,
    )

    return {
        "id": conversation.id,

        "organization_id":
            conversation.organization_id,

        "store": {
            "id": store.id,
            "name": store.name,
            "country_code":
                store.country_code,
            "currency":
                store.currency,
            "timezone":
                store.timezone,
            "default_language":
                store.default_language,
        },

        "name": customer.name,
        "preview": conversation.preview,
        "time": format_relative_time(
            conversation.updated_at,
        ),
        "unread": conversation.unread,
        "channel": conversation.channel,
        "phone": customer.phone,
        "email": customer.email,
        "country_code":
            customer.country_code,

        "orders":
            profile.orders_count
            if profile
            else 0,

        "total_spent":
            float(profile.total_spent)
            if profile
            else 0,

        "currency":
            profile.currency
            if profile
            else store.currency,

        "last_order":
            profile.last_order_ref
            if profile
            else None,

        "agent": (
            {
                "id":
                    conversation.assigned_agent.id,
                "name":
                    conversation.assigned_agent.name,
                "role":
                    conversation.assigned_agent.role,
            }
            if conversation.assigned_agent
            else None
        ),

        "mode":
            conversation.mode,

        "tags": [
            tag
            for tag in conversation.tags.split(",")
            if tag
        ],
    }


def serialize_message(
    message: Message,
):
    data = {
        "id": message.id,
        "sender": message.sender,
        "text": message.text,
        "time": message.created_at.strftime(
            "%H:%M"
        ),
    }

    if message.agent:
        data["agent"] = {
            "id": message.agent.id,
            "name": message.agent.name,
            "role": message.agent.role,
        }

    return data


def format_relative_time(
    timestamp: datetime,
):
    delta = datetime.utcnow() - timestamp

    minutes = max(
        0,
        int(delta.total_seconds() / 60),
    )

    if minutes < 1:
        return "ahora"

    if minutes < 60:
        return f"{minutes} min"

    hours = minutes // 60

    if hours < 24:
        return f"{hours} h"

    days = hours // 24

    return f"{days} d"


def get_scoped_conversation(
    conversation_id: int,
    membership: OrganizationMembership,
    store: Store | None,
    db: Session,
):
    query = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.organization_id
            == membership.organization_id,
        )
    )

    if store is not None:
        query = query.filter(
            Conversation.store_id == store.id
        )

    else:
        allowed_store_ids = get_allowed_store_ids(
            membership
        )

        if allowed_store_ids is not None:
            if not allowed_store_ids:
                raise HTTPException(
                    status_code=404,
                    detail="Conversation not found",
                )

            query = query.filter(
                Conversation.store_id.in_(
                    allowed_store_ids
                )
            )

    conversation = query.first()

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    return conversation



# ============================================================
# AGENTS
# ============================================================


# ============================================================
# KNOWLEDGE SOURCES
# ============================================================

@app.get(
    "/api/knowledge-bases/{knowledge_base_id}/sources"
)
def list_knowledge_sources(
    knowledge_base_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.read")
    ),
    db: Session = Depends(get_db),
):
    knowledge_base = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.id
            == knowledge_base_id,
            KnowledgeBase.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not knowledge_base:
        raise HTTPException(
            status_code=404,
            detail="Knowledge base not found",
        )

    sources = (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.organization_id
            == membership.organization_id,
            KnowledgeSource.knowledge_base_id
            == knowledge_base_id,
            KnowledgeSource.active.is_(True),
        )
        .order_by(
            KnowledgeSource.created_at.desc()
        )
        .all()
    )

    google_connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id
            == membership.organization_id,
        )
        .first()
    )

    return {
        "items": [
            {
                **serialize_knowledge_source(source),
                "freshness": _derive_freshness(
                    source,
                    google_connection,
                ),
            }
            for source in sources
        ],
        "total": len(sources),
    }


@app.post(
    "/api/knowledge-bases/{knowledge_base_id}/sources"
)
async def upload_knowledge_source(
    knowledge_base_id: int,
    file: UploadFile = File(...),
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    knowledge_base = _require_knowledge_base_ready(
        db,
        membership.organization_id,
        knowledge_base_id,
    )

    filename = (
        file.filename
        or "document"
    )

    extension = (
        filename.rsplit(".", 1)[-1].lower()
        if "." in filename
        else ""
    )

    allowed_extensions = {
        "pdf",
        "txt",
        "md",
        "html",
        "doc",
        "docx",
        "csv",
        "xlsx",
    }

    if extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type",
        )

    content = await file.read()

    max_size = (
        25 * 1024 * 1024
    )

    if not content:
        raise HTTPException(
            status_code=400,
            detail="File is empty",
        )

    if len(content) > max_size:
        raise HTTPException(
            status_code=400,
            detail="File exceeds 25 MB limit",
        )

    try:
        uploaded = (
            upload_knowledge_file(
                organization_id=
                    membership.organization_id,
                knowledge_base_id=
                    knowledge_base.id,
                filename=filename,
                content=content,
                content_type=
                    file.content_type,
            )
        )

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Unable to upload "
                "knowledge document"
            ),
        ) from exc

    source = KnowledgeSource(
        organization_id=
            membership.organization_id,
        knowledge_base_id=
            knowledge_base.id,
        name=filename,
        source_type="file",
        content_type=
            file.content_type,
        s3_bucket=
            uploaded["bucket"],
        s3_key=
            uploaded["key"],
        size_bytes=
            len(content),
        status="uploaded",
        active=True,
    )

    db.add(source)
    db.commit()
    db.refresh(source)

    return serialize_knowledge_source(
        source
    )


@app.delete(
    "/api/knowledge-bases/{knowledge_base_id}/sources/{source_id}"
)
def delete_knowledge_source(
    knowledge_base_id: int,
    source_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    kb = _require_knowledge_base_ready(
        db,
        membership.organization_id,
        knowledge_base_id,
    )
    source = (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.id
            == source_id,
            KnowledgeSource.organization_id
            == membership.organization_id,
            KnowledgeSource.knowledge_base_id
            == knowledge_base_id,
        )
        .first()
    )

    if not source:
        raise HTTPException(
            status_code=404,
            detail="Knowledge source not found",
        )

    sources_to_delete = [source]
    if source.source_type == "google_drive_folder":
        sources_to_delete.extend(
            db.query(KnowledgeSource)
            .filter(
                KnowledgeSource.parent_source_id
                == source.id,
                KnowledgeSource.organization_id
                == membership.organization_id,
                KnowledgeSource.knowledge_base_id
                == knowledge_base_id,
                KnowledgeSource.active.is_(True),
            )
            .all()
        )

    # A folder is metadata only; its children own the S3 artifacts.
    try:
        for item in sources_to_delete:
            if item.s3_bucket and item.s3_key:
                delete_knowledge_file(
                    item.s3_bucket,
                    item.s3_key,
                )
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail=(
                "Unable to delete "
                "knowledge document"
            ),
        ) from exc

    for item in sources_to_delete:
        item.active = False
        item.status = "deleted"
    db.flush()

    # Trigger Bedrock reindex to remove
    # deleted content from vector index
    ingestion_job_id = None
    reindex_status = "not_configured"

    job_id = start_ingestion_job(
        kb.external_id,
        kb.external_data_source_id,
    )
    if job_id:
        ingestion_job_id = job_id
        reindex_status = "indexing"
    else:
        reindex_status = "reindex_failed"

    db.commit()

    return {
        "id": source.id,
        "deleted": True,
        "reindex_status": reindex_status,
        "ingestion_job_id": ingestion_job_id,
    }


@app.get("/api/agents")
def list_agents(
    membership: OrganizationMembership = Depends(
        require_permission("agents.read")
    ),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Agent)
        .filter(
            Agent.organization_id
            == membership.organization_id
        )
        .order_by(
            Agent.name.asc()
        )
    )

    allowed_store_ids = get_allowed_store_ids(
        membership
    )

    if allowed_store_ids is not None:
        if not allowed_store_ids:
            agents = []
        else:
            agents = (
                query
                .filter(
                    Agent.stores.any(
                        Store.id.in_(
                            allowed_store_ids
                        )
                    )
                )
                .all()
            )
    else:
        agents = query.all()

    return {
        "items": [
            serialize_agent(agent)
            for agent in agents
        ],
        "total": len(agents),
    }



@app.post("/api/agents/{agent_id}/ask")
def ask_agent(
    agent_id: int,
    payload: AgentAskRequest,
    membership: OrganizationMembership = Depends(
        require_permission("agents.read")
    ),
    db: Session = Depends(get_db),
):
    question = payload.question.strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Question is required",
        )

    number_of_results = max(
        1,
        min(
            payload.number_of_results,
            10,
        ),
    )

    agent = (
        db.query(Agent)
        .filter(
            Agent.id == agent_id,
            Agent.organization_id
            == membership.organization_id,
            Agent.active.is_(True),
        )
        .first()
    )

    if not agent:
        raise HTTPException(
            status_code=404,
            detail="Agent not found",
        )

    allowed_store_ids = (
        get_allowed_store_ids(
            membership
        )
    )

    if allowed_store_ids is not None:
        agent_store_ids = {
            store.id
            for store in agent.stores
            if store.active
        }

        if not agent_store_ids.intersection(
            set(allowed_store_ids)
        ):
            raise HTTPException(
                status_code=404,
                detail="Agent not found",
            )

    connected_knowledge_bases = [
        knowledge_base
        for knowledge_base
        in agent.knowledge_bases
        if (
            knowledge_base.active
            and knowledge_base.external_status == "ready"
            and knowledge_base.external_id
            and knowledge_base.external_data_source_id
        )
    ]

    if not connected_knowledge_bases:
        return {
            "agent": {
                "id": agent.id,
                "name": agent.name,
                "role": agent.role,
            },
            "question": question,
            "answer": (
                "Este agente todavía no tiene "
                "fuentes de conocimiento conectadas."
            ),
            "sources": [],
        }

    try:
        evidence = (
            retrieve_agent_knowledge(
                agent=agent,
                query=question,
                number_of_results=
                    number_of_results,
            )
        )

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Knowledge retrieval failed"
            ),
        ) from exc

    try:
        answer = (
            generate_grounded_answer(
                question=question,
                evidence=evidence,
                agent_name=
                    agent.name,
                agent_role=
                    agent.role,
            )
        )

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "AI generation failed"
            ),
        ) from exc

    sources = []

    for result in evidence:
        location = (
            result.get(
                "location",
                {},
            )
        )

        s3_uri = (
            location
            .get(
                "s3Location",
                {},
            )
            .get("uri")
        )

        sources.append(
            {
                "score":
                    result.get(
                        "score"
                    ),

                "uri":
                    s3_uri,

                "data_source_id":
                    result
                    .get(
                        "metadata",
                        {},
                    )
                    .get(
                        "x-amz-bedrock-kb-data-source-id"
                    ),

                "preview":
                    result
                    .get(
                        "text",
                        "",
                    )[:300],
            }
        )

    return {
        "agent": {
            "id":
                agent.id,

            "name":
                agent.name,

            "role":
                agent.role,
        },

        "question":
            question,

        "answer":
            answer,

        "sources":
            sources,

        "knowledge": {
            "connected_bases":
                len(
                    connected_knowledge_bases
                ),

            "results":
                len(
                    evidence
                ),
        },
    }


@app.get("/api/agents/{agent_id}")
def get_agent(
    agent_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("agents.read")
    ),
    db: Session = Depends(get_db),
):
    agent = (
        db.query(Agent)
        .filter(
            Agent.id == agent_id,
            Agent.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not agent:
        raise HTTPException(
            status_code=404,
            detail="Agent not found",
        )

    allowed_store_ids = get_allowed_store_ids(
        membership
    )

    if allowed_store_ids is not None:
        agent_store_ids = {
            store.id
            for store in agent.stores
        }

        if not agent_store_ids.intersection(
            allowed_store_ids
        ):
            raise HTTPException(
                status_code=404,
                detail="Agent not found",
            )

    return serialize_agent(agent)


@app.post("/api/agents")
def create_agent(
    payload: AgentCreate,
    membership: OrganizationMembership = Depends(
        require_permission("agents.write")
    ),
    db: Session = Depends(get_db),
):
    name = payload.name.strip()
    role = payload.role.strip()

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Agent name is required",
        )

    if not role:
        raise HTTPException(
            status_code=400,
            detail="Agent role is required",
        )

    stores = resolve_member_stores(
        membership,
        payload.store_ids,
        db,
    )

    knowledge_bases = (
        resolve_organization_knowledge_bases(
            membership.organization_id,
            payload.knowledge_base_ids,
            db,
        )
    )

    agent = Agent(
        organization_id=
            membership.organization_id,
        name=name,
        role=role,
        active=payload.active,
    )

    agent.stores = stores
    agent.knowledge_bases = knowledge_bases

    db.add(agent)
    db.commit()
    db.refresh(agent)

    return serialize_agent(agent)


@app.patch("/api/agents/{agent_id}")
def update_agent(
    agent_id: int,
    payload: AgentUpdate,
    membership: OrganizationMembership = Depends(
        require_permission("agents.write")
    ),
    db: Session = Depends(get_db),
):
    agent = (
        db.query(Agent)
        .filter(
            Agent.id == agent_id,
            Agent.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not agent:
        raise HTTPException(
            status_code=404,
            detail="Agent not found",
        )

    allowed_store_ids = get_allowed_store_ids(
        membership
    )

    if allowed_store_ids is not None:
        current_store_ids = {
            store.id
            for store in agent.stores
        }

        if not current_store_ids.intersection(
            allowed_store_ids
        ):
            raise HTTPException(
                status_code=404,
                detail="Agent not found",
            )

    if payload.name is not None:
        name = payload.name.strip()

        if not name:
            raise HTTPException(
                status_code=400,
                detail="Agent name is required",
            )

        agent.name = name

    if payload.role is not None:
        role = payload.role.strip()

        if not role:
            raise HTTPException(
                status_code=400,
                detail="Agent role is required",
            )

        agent.role = role

    if payload.active is not None:
        agent.active = payload.active

    if payload.store_ids is not None:
        agent.stores = resolve_member_stores(
            membership,
            payload.store_ids,
            db,
        )

    if payload.knowledge_base_ids is not None:
        agent.knowledge_bases = (
            resolve_organization_knowledge_bases(
                membership.organization_id,
                payload.knowledge_base_ids,
                db,
            )
        )

    db.commit()
    db.refresh(agent)

    return serialize_agent(agent)


# ============================================================
# KNOWLEDGE BASES
# ============================================================

@app.get("/api/knowledge-bases")
def list_knowledge_bases(
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.read")
    ),
    db: Session = Depends(get_db),
):
    query = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.organization_id
            == membership.organization_id
        )
        .order_by(
            KnowledgeBase.name.asc()
        )
    )

    knowledge_bases = query.all()

    allowed_store_ids = get_allowed_store_ids(
        membership
    )

    if allowed_store_ids is not None:
        allowed_set = set(
            allowed_store_ids
        )

        knowledge_bases = [
            knowledge_base
            for knowledge_base
            in knowledge_bases
            if (
                knowledge_base.scope
                == "organization"
                or bool(
                    {
                        store.id
                        for store
                        in knowledge_base.stores
                    }.intersection(
                        allowed_set
                    )
                )
            )
        ]

    return {
        "items": [
            serialize_knowledge_base(
                knowledge_base
            )
            for knowledge_base
            in knowledge_bases
        ],
        "total": len(
            knowledge_bases
        ),
    }


@app.get(
    "/api/knowledge-bases/{knowledge_base_id}"
)
def get_knowledge_base(
    knowledge_base_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.read")
    ),
    db: Session = Depends(get_db),
):
    knowledge_base = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.id
            == knowledge_base_id,
            KnowledgeBase.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not knowledge_base:
        raise HTTPException(
            status_code=404,
            detail="Knowledge base not found",
        )

    allowed_store_ids = get_allowed_store_ids(
        membership
    )

    if (
        allowed_store_ids is not None
        and knowledge_base.scope
        != "organization"
    ):
        kb_store_ids = {
            store.id
            for store
            in knowledge_base.stores
        }

        if not kb_store_ids.intersection(
            allowed_store_ids
        ):
            raise HTTPException(
                status_code=404,
                detail="Knowledge base not found",
            )

    return serialize_knowledge_base(
        knowledge_base
    )


@app.post("/api/knowledge-bases")
def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    background_tasks: BackgroundTasks,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    name = payload.name.strip()
    scope = payload.scope.strip()

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Knowledge base name is required",
        )

    if scope not in {
        "organization",
        "selected_stores",
    }:
        raise HTTPException(
            status_code=400,
            detail="Invalid knowledge base scope",
        )

    if (
        scope == "organization"
        and not membership.all_stores
        and membership.role != "owner"
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Organization-wide knowledge bases "
                "require all-store access"
            ),
        )

    if scope == "organization":
        stores = []
    else:
        stores = resolve_member_stores(
            membership,
            payload.store_ids,
            db,
        )

        if not stores:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Selected-store knowledge bases "
                    "require at least one store"
                ),
            )

    knowledge_base = KnowledgeBase(
        organization_id=
            membership.organization_id,
        name=name,
        scope=scope,
        external_status="pending",
        provisioning_stage="queued",
        provisioning_started_at=datetime.now(timezone.utc),
        provisioning_stage_started_at=datetime.now(timezone.utc),
        active=payload.active,
    )

    knowledge_base.stores = stores

    db.add(
        knowledge_base
    )
    db.commit()
    db.refresh(
        knowledge_base
    )

    background_tasks.add_task(run_knowledge_base_provisioning, knowledge_base.id)

    return serialize_knowledge_base(
        knowledge_base
    )


@app.patch(
    "/api/knowledge-bases/{knowledge_base_id}"
)
def update_knowledge_base(
    knowledge_base_id: int,
    payload: KnowledgeBaseUpdate,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    knowledge_base = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.id
            == knowledge_base_id,
            KnowledgeBase.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not knowledge_base:
        raise HTTPException(
            status_code=404,
            detail="Knowledge base not found",
        )

    if payload.name is not None:
        name = payload.name.strip()

        if not name:
            raise HTTPException(
                status_code=400,
                detail="Knowledge base name is required",
            )

        knowledge_base.name = name

    next_scope = (
        payload.scope.strip()
        if payload.scope is not None
        else knowledge_base.scope
    )

    if next_scope not in {
        "organization",
        "selected_stores",
    }:
        raise HTTPException(
            status_code=400,
            detail="Invalid knowledge base scope",
        )

    if (
        next_scope == "organization"
        and not membership.all_stores
        and membership.role != "owner"
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Organization-wide knowledge bases "
                "require all-store access"
            ),
        )

    knowledge_base.scope = (
        next_scope
    )

    if payload.active is not None:
        knowledge_base.active = (
            payload.active
        )

    if next_scope == "organization":
        knowledge_base.stores = []

    elif payload.store_ids is not None:
        stores = resolve_member_stores(
            membership,
            payload.store_ids,
            db,
        )

        if not stores:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Selected-store knowledge bases "
                    "require at least one store"
                ),
            )

        knowledge_base.stores = stores

    db.commit()
    db.refresh(
        knowledge_base
    )

    return serialize_knowledge_base(
        knowledge_base
    )


@app.post(
    "/api/knowledge-bases/{knowledge_base_id}/retry-provisioning"
)
def retry_knowledge_base_provisioning(
    knowledge_base_id: int,
    background_tasks: BackgroundTasks,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    knowledge_base = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.organization_id == membership.organization_id,
        )
        .first()
    )

    if not knowledge_base:
        raise HTTPException(
            status_code=404,
            detail="Knowledge base not found",
        )

    if knowledge_base.external_status in ("provisioning", "retrying"):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PROVISIONING_IN_PROGRESS",
                "message": "Knowledge Base provisioning is already in progress.",
            },
        )

    if knowledge_base.external_status not in ("pending", "failed"):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_PROVISIONING_STATE",
                "message": f"Cannot retry provisioning for KnowledgeBase with status: {knowledge_base.external_status}",
            },
        )

    previous_status = knowledge_base.external_status
    logger.info(
        "knowledge_base_manual_retry_requested organization_id=%s knowledge_base_id=%s previous_status=%s",
        knowledge_base.organization_id,
        knowledge_base.id,
        previous_status,
    )
    now = datetime.now(timezone.utc)
    updated = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.id == knowledge_base.id,
            KnowledgeBase.organization_id == knowledge_base.organization_id,
            KnowledgeBase.external_status == previous_status,
        )
        .update(
            {
                KnowledgeBase.external_status: "retrying",
                KnowledgeBase.external_last_error: None,
                KnowledgeBase.provisioning_stage: "queued",
                KnowledgeBase.provisioning_started_at: now,
                KnowledgeBase.provisioning_stage_started_at: now,
            },
            synchronize_session=False,
        )
    )
    if updated != 1:
        db.rollback()
        db.refresh(knowledge_base)
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PROVISIONING_STATE_CHANGED",
                "message": "Knowledge Base provisioning state changed. Try again.",
            },
        )
    db.commit()
    db.refresh(knowledge_base)
    background_tasks.add_task(run_knowledge_base_provisioning, knowledge_base.id)
    logger.info(
        "knowledge_base_manual_retry_scheduled organization_id=%s knowledge_base_id=%s previous_status=%s status=%s stage=%s",
        knowledge_base.organization_id,
        knowledge_base.id,
        previous_status,
        knowledge_base.external_status,
        knowledge_base.provisioning_stage,
    )

    return serialize_knowledge_base(knowledge_base)


@app.delete("/api/knowledge-bases/{knowledge_base_id}")
def delete_knowledge_base(
    knowledge_base_id: int,
    membership: OrganizationMembership = Depends(require_permission("knowledge.write")),
    db: Session = Depends(get_db),
):
    knowledge_base = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == knowledge_base_id,
        KnowledgeBase.organization_id == membership.organization_id,
    ).first()
    if not knowledge_base:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    try:
        delete_diaglob_knowledge_base(db, knowledge_base)
    except BedrockProvisioningError as error:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "KNOWLEDGE_BASE_DELETION_FAILED",
                "message": "Knowledge Base deletion could not be completed.",
            },
        ) from error
    logger.info(
        "Knowledge Base deleted: organization_id=%s knowledge_base_id=%s actor_user_id=%s",
        membership.organization_id, knowledge_base_id, membership.user_id,
    )
    return {"id": knowledge_base_id, "deleted": True}


@app.get("/api/conversations")
def list_conversations(
    membership: OrganizationMembership = Depends(
        require_permission("conversations.read")
    ),
    store: Store | None = Depends(
        get_store_scope
    ),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Conversation)
        .filter(
            Conversation.organization_id
            == membership.organization_id
        )
    )

    if store is not None:
        query = query.filter(
            Conversation.store_id == store.id
        )

    else:
        allowed_store_ids = get_allowed_store_ids(
            membership
        )

        if allowed_store_ids is not None:
            if not allowed_store_ids:
                conversations = []
            else:
                query = query.filter(
                    Conversation.store_id.in_(
                        allowed_store_ids
                    )
                )

                conversations = (
                    query
                    .order_by(
                        Conversation.updated_at.desc()
                    )
                    .all()
                )
        else:
            conversations = (
                query
                .order_by(
                    Conversation.updated_at.desc()
                )
                .all()
            )

    if store is not None:
        conversations = (
            query
            .order_by(
                Conversation.updated_at.desc()
            )
            .all()
        )

    return {
        "scope": {
            "organization_id":
                membership.organization_id,

            "store_id":
                store.id
                if store
                else None,

            "aggregate_view":
                store is None,

            "permission_scope":
                "all_stores"
                if membership.all_stores
                else "allowed_stores",
        },

        "items": [
            serialize_conversation(
                conversation
            )
            for conversation in conversations
        ],

        "total":
            len(conversations),
    }


@app.get(
    "/api/conversations/{conversation_id}"
)
def get_conversation(
    conversation_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("conversations.read")
    ),
    store: Store | None = Depends(
        get_store_scope
    ),
    db: Session = Depends(get_db),
):
    conversation = get_scoped_conversation(
        conversation_id,
        membership,
        store,
        db,
    )

    return {
        **serialize_conversation(
            conversation
        ),
        "messages": [
            serialize_message(message)
            for message in conversation.messages
        ],
    }


@app.patch(
    "/api/conversations/{conversation_id}/mode"
)
def update_conversation_mode(
    conversation_id: int,
    mode: str,
    membership: OrganizationMembership = Depends(
        require_permission("conversations.write")
    ),
    store: Store | None = Depends(
        get_store_scope
    ),
    db: Session = Depends(get_db),
):
    if mode not in {"ai", "human"}:
        raise HTTPException(
            status_code=400,
            detail="Mode must be ai or human",
        )

    conversation = get_scoped_conversation(
        conversation_id,
        membership,
        store,
        db,
    )

    conversation.mode = mode
    conversation.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(conversation)

    return {
        "id": conversation.id,
        "mode": conversation.mode,
    }


@app.post(
    "/api/conversations/{conversation_id}/messages"
)
def create_message(
    conversation_id: int,
    payload: MessageCreate,
    membership: OrganizationMembership = Depends(
        require_permission("conversations.write")
    ),
    store: Store | None = Depends(
        get_store_scope
    ),
    db: Session = Depends(get_db),
):
    conversation = get_scoped_conversation(
        conversation_id,
        membership,
        store,
        db,
    )

    text = payload.text.strip()

    if not text:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty",
        )

    if payload.sender not in {
        "human",
        "ai",
        "customer",
    }:
        raise HTTPException(
            status_code=400,
            detail="Invalid sender",
        )

    # ========================================================
    # 1. GUARDAR EL MENSAJE ORIGINAL
    # ========================================================

    message = Message(
        conversation_id=conversation.id,
        sender=payload.sender,
        text=text,
        agent_id=(
            conversation.agent_id
            if payload.sender == "ai"
            else None
        ),
    )

    db.add(message)

    conversation.preview = text
    conversation.updated_at = datetime.utcnow()

    if payload.sender == "customer":
        conversation.unread = (
            conversation.unread or 0
        ) + 1
    else:
        conversation.unread = 0

    # Confirmamos el mensaje antes de llamar a Bedrock.
    # Así nunca se pierde aunque falle la IA.
    db.commit()
    db.refresh(message)

    serialized_message = serialize_message(
        message
    )

    # ========================================================
    # 2. DECIDIR SI DEBE RESPONDER LA IA
    # ========================================================

    should_generate_ai = (
        payload.sender == "customer"
        and conversation.mode == "ai"
        and conversation.agent_id is not None
    )

    print(
        "[DIAGLOB AI]",
        "conversation=",
        conversation.id,
        "sender=",
        payload.sender,
        "mode=",
        conversation.mode,
        "agent_id=",
        conversation.agent_id,
        "should_generate=",
        should_generate_ai,
    )

    if not should_generate_ai:
        return serialized_message

    # ========================================================
    # 3. VALIDAR AGENTE
    # ========================================================

    agent = conversation.assigned_agent

    if (
        not agent
        or not agent.active
        or agent.organization_id
        != conversation.organization_id
    ):
        print(
            "[DIAGLOB AI SKIP]",
            "invalid_agent",
        )

        return serialized_message

    # El agente debe atender esta tienda.
    agent_store_ids = {
        agent_store.id
        for agent_store in agent.stores
        if agent_store.active
    }

    if conversation.store_id not in agent_store_ids:
        print(
            "[DIAGLOB AI SKIP]",
            "agent_not_available_for_store",
            conversation.store_id,
        )

        return serialized_message

    # ========================================================
    # 4. RAG + NOVA
    # ========================================================

    try:
        evidence = retrieve_agent_knowledge(
            agent=agent,
            query=text,
            store_id=conversation.store_id,
            number_of_results=5,
        )

        print(
            "[DIAGLOB AI]",
            "retrieval_results=",
            len(evidence),
        )

        conversation_store = conversation.store

        commerce_results = search_products(
            db=db,
            organization_id=
                conversation.organization_id,
            store_id=
                conversation.store_id,
            query=text,
            limit=5,
        )

        print(
            "[DIAGLOB COMMERCE]",
            "conversation=",
            conversation.id,
            "results=",
            len(commerce_results),
        )

        answer = generate_grounded_answer(
            question=text,
            evidence=evidence,
            agent_name=agent.name,
            agent_role=agent.role,
            store_name=(
                conversation_store.name
                if conversation_store
                else None
            ),
            country_code=(
                conversation_store.country_code
                if conversation_store
                else None
            ),
            currency=(
                conversation_store.currency
                if conversation_store
                else None
            ),
            timezone=(
                conversation_store.timezone
                if conversation_store
                else None
            ),
            language=(
                conversation_store.default_language
                if conversation_store
                else None
            ),
            commerce_results=
                commerce_results,
        )

        if not answer:
            print(
                "[DIAGLOB AI SKIP]",
                "empty_answer",
            )

            return serialized_message

        # ====================================================
        # 5. GUARDAR RESPUESTA IA
        # ====================================================

        ai_message = Message(
            conversation_id=conversation.id,
            agent_id=agent.id,
            sender="ai",
            text=answer,
        )

        db.add(ai_message)

        conversation.preview = answer
        conversation.unread = 0
        conversation.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(ai_message)

        print(
            "[DIAGLOB AI SUCCESS]",
            "conversation=",
            conversation.id,
            "message_id=",
            ai_message.id,
            "agent=",
            agent.name,
        )

    except Exception as exc:
        db.rollback()

        print(
            "[DIAGLOB AI ERROR]",
            "conversation=",
            conversation.id,
            "agent=",
            conversation.agent_id,
            "error=",
            repr(exc),
        )

    # Mantenemos el contrato original:
    # POST /messages devuelve el mensaje enviado.
    return serialized_message


# ============================================================
# COMMERCE
# ============================================================

def serialize_commerce_product(
    product: Product,
):
    return {
        "id": product.id,
        "organization_id": product.organization_id,
        "store_id": product.store_id,
        "shopify_product_id":
            product.shopify_product_id,
        "title": product.title,
        "handle": product.handle,
        "description": product.description,
        "image_url": product.image_url,
        "vendor": product.vendor,
        "product_type": product.product_type,
        "active": product.active,

        "store": {
            "id": product.store.id,
            "name": product.store.name,
            "country_code":
                product.store.country_code,
            "currency":
                product.store.currency,
        }
        if product.store
        else None,

        "variants": [
            {
                "id": variant.id,
                "shopify_variant_id":
                    variant.shopify_variant_id,
                "title": variant.title,
                "sku": variant.sku,
                "barcode": variant.barcode,
                "price":
                    float(variant.price),
                "currency":
                    variant.currency,
                "inventory_quantity":
                    variant.inventory_quantity,
                "available":
                    variant.available,
            }
            for variant in product.variants
        ],
    }


@app.get("/api/commerce/products")
def list_commerce_products(
    q: str | None = None,
    membership: OrganizationMembership = Depends(
        require_permission(
            "commerce.read"
        )
    ),
    store: Store | None = Depends(
        get_store_scope
    ),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Product)
        .filter(
            Product.organization_id
            == membership.organization_id,

            Product.active.is_(True),
        )
    )

    if store is not None:
        query = query.filter(
            Product.store_id == store.id
        )

    else:
        allowed_store_ids = (
            get_allowed_store_ids(
                membership
            )
        )

        if allowed_store_ids is not None:
            if not allowed_store_ids:
                return {
                    "items": [],
                    "total": 0,
                }

            query = query.filter(
                Product.store_id.in_(
                    allowed_store_ids
                )
            )

    if q and q.strip():
        search = (
            f"%{q.strip()}%"
        )

        query = query.filter(
            Product.title.ilike(
                search
            )
        )

    products = (
        query
        .order_by(
            Product.title
        )
        .all()
    )

    return {
        "items": [
            serialize_commerce_product(
                product
            )
            for product in products
        ],
        "total":
            len(products),
    }


@app.post("/api/commerce/products")
def create_commerce_product(
    payload: ProductCreate,
    membership: OrganizationMembership = Depends(
        require_permission(
            "commerce.write"
        )
    ),
    store: Store | None = Depends(
        get_store_scope
    ),
    db: Session = Depends(get_db),
):
    if store is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Select a store before "
                "creating a product"
            ),
        )

    title = (
        payload.title
        .strip()
    )

    if not title:
        raise HTTPException(
            status_code=400,
            detail=(
                "Product title is required"
            ),
        )

    product = Product(
        organization_id=
            membership.organization_id,

        store_id=
            store.id,

        shopify_product_id=
            payload.shopify_product_id,

        title=
            title,

        handle=
            payload.handle,

        description=
            payload.description,

        image_url=
            payload.image_url,

        vendor=
            payload.vendor,

        product_type=
            payload.product_type,

        active=
            payload.active,
    )

    db.add(product)
    db.flush()

    for item in payload.variants:
        currency = (
            item.currency
            or store.currency
        ).upper()

        if (
            currency
            != store.currency.upper()
        ):
            db.rollback()

            raise HTTPException(
                status_code=400,
                detail=(
                    "Variant currency must "
                    "match store currency "
                    f"({store.currency})"
                ),
            )

        if item.price < 0:
            db.rollback()

            raise HTTPException(
                status_code=400,
                detail=(
                    "Variant price cannot "
                    "be negative"
                ),
            )

        if item.inventory_quantity < 0:
            db.rollback()

            raise HTTPException(
                status_code=400,
                detail=(
                    "Inventory quantity cannot "
                    "be negative"
                ),
            )

        variant = ProductVariant(
            product_id=
                product.id,

            shopify_variant_id=
                item.shopify_variant_id,

            title=(
                item.title.strip()
                or "Default"
            ),

            sku=
                item.sku,

            barcode=
                item.barcode,

            price=
                item.price,

            currency=
                currency,

            inventory_quantity=
                item.inventory_quantity,

            available=(
                item.available
                and
                item.inventory_quantity > 0
            ),
        )

        db.add(variant)

    db.commit()
    db.refresh(product)

    return serialize_commerce_product(
        product
    )


@app.get(
    "/api/commerce/products/{product_id}"
)
def get_commerce_product(
    product_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "commerce.read"
        )
    ),
    store: Store | None = Depends(
        get_store_scope
    ),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Product)
        .filter(
            Product.id == product_id,

            Product.organization_id
            == membership.organization_id,
        )
    )

    if store is not None:
        query = query.filter(
            Product.store_id == store.id
        )

    else:
        allowed_store_ids = (
            get_allowed_store_ids(
                membership
            )
        )

        if allowed_store_ids is not None:
            if not allowed_store_ids:
                raise HTTPException(
                    status_code=404,
                    detail="Product not found",
                )

            query = query.filter(
                Product.store_id.in_(
                    allowed_store_ids
                )
            )

    product = query.first()

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found",
        )

    return serialize_commerce_product(
        product
    )


# ============================================================
# MARKETS
# ============================================================

@app.get("/api/markets")
def list_markets(
    membership: OrganizationMembership = Depends(
        require_permission(
            "stores.read"
        )
    ),
):
    return {
        "items":
            AMERICA_MARKETS,

        "total":
            len(
                AMERICA_MARKETS
            ),
    }


@app.get("/api/markets/{country_code}")
def get_market_detail(
    country_code: str,
    membership: OrganizationMembership = Depends(
        require_permission(
            "stores.read"
        )
    ),
):
    market = get_market(
        country_code
    )

    if not market:
        raise HTTPException(
            status_code=404,
            detail=(
                "Market not supported"
            ),
        )

    return market


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



@app.get("/api/stores/{store_id}/commerce")
def get_store_commerce_connection(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "stores.read"
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

    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.store_id
            == store.id,
            CommerceConnection.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not connection:
        return {
            "connected": False,
            "provider": None,
            "external_store_url": None,
            "status": "disconnected",
            "connected_at": None,
            "last_sync_at": None,
            "last_error": None,
        }

    return {
        "connected":
            connection.status
            == "connected",

        "provider":
            connection.provider,

        "external_store_url":
            connection.external_store_url,

        "status":
            connection.status,

        "connected_at":
            (
                connection.connected_at.isoformat()
                + "Z"
                if connection.connected_at
                else None
            ),

        "last_sync_at":
            (
                connection.last_sync_at.isoformat()
                + "Z"
                if connection.last_sync_at
                else None
            ),

        "last_error":
            connection.last_error,
    }


@app.get(
    "/api/stores/{store_id}"
    "/commerce/summary"
)
def get_commerce_summary(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "commerce.read"
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

    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.store_id
            == store.id,
            CommerceConnection.organization_id
            == membership.organization_id,
        )
        .first()
    )

    total_products = (
        db.query(Product)
        .filter(
            Product.store_id == store.id,
            Product.organization_id
            == membership.organization_id,
        )
        .count()
    )

    total_variants = (
        db.query(ProductVariant)
        .join(Product)
        .filter(
            Product.store_id == store.id,
            Product.organization_id
            == membership.organization_id,
        )
        .count()
    )

    orders_query = (
        db.query(Order)
        .filter(
            Order.store_id == store.id,
            Order.organization_id
            == membership.organization_id,
        )
    )

    total_orders = orders_query.count()

    orders_by_status = {}

    for status_val in (
        "pending",
        "created",
        "failed",
        "unknown",
    ):
        orders_by_status[status_val] = (
            orders_query.filter(
                Order.external_creation_status
                == status_val
            )
            .count()
        )

    total_order_value = 0.0

    value_rows = (
        db.query(
            Order.total_amount,
            Order.currency,
        )
        .filter(
            Order.store_id == store.id,
            Order.organization_id
            == membership.organization_id,
            Order.external_creation_status
            .in_(["created", "pending"]),
        )
        .all()
    )

    for amount, _currency in value_rows:
        total_order_value += float(amount)

    recent_orders = (
        db.query(Order)
        .filter(
            Order.store_id == store.id,
            Order.organization_id
            == membership.organization_id,
        )
        .order_by(Order.created_at.desc())
        .limit(5)
        .all()
    )

    recent_products = (
        db.query(Product)
        .filter(
            Product.store_id == store.id,
            Product.organization_id
            == membership.organization_id,
        )
        .order_by(Product.updated_at.desc())
        .limit(5)
        .all()
    )

    return {
        "connected":
            connection is not None
            and connection.status
            == "connected",

        "provider":
            connection.provider
            if connection
            else None,

        "total_products": total_products,
        "total_variants": total_variants,
        "total_orders": total_orders,
        "orders_by_status": orders_by_status,
        "total_order_value": round(
            total_order_value, 2
        ),
        "currency": store.currency,

        "recent_orders": [
            {
                "id": o.id,
                "order_number": o.order_number,
                "total_amount": float(
                    o.total_amount
                ),
                "currency": o.currency,
                "financial_status": (
                    o.financial_status
                ),
                "source": o.source,
                "external_creation_status": (
                    o.external_creation_status
                ),
                "created_at": (
                    o.created_at.isoformat()
                    + "Z"
                    if o.created_at
                    else None
                ),
            }
            for o in recent_orders
        ],

        "recent_products": [
            {
                "id": p.id,
                "title": p.title,
                "image_url": p.image_url,
                "active": p.active,
                "updated_at": (
                    p.updated_at.isoformat()
                    + "Z"
                    if p.updated_at
                    else None
                ),
            }
            for p in recent_products
        ],
    }


@app.get(
    "/api/stores/{store_id}"
    "/commerce/products"
)
def list_store_commerce_products(
    store_id: int,
    q: str | None = None,
    membership: OrganizationMembership = Depends(
        require_permission(
            "commerce.read"
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

    query = (
        db.query(Product)
        .filter(
            Product.store_id == store.id,
            Product.organization_id
            == membership.organization_id,
        )
    )

    if q and q.strip():
        search = f"%{q.strip()}%"

        query = query.filter(
            Product.title.ilike(search)
        )

    products = (
        query
        .order_by(Product.title)
        .all()
    )

    return {
        "items": [
            serialize_commerce_product(p)
            for p in products
        ],
        "total": len(products),
    }


@app.get(
    "/api/stores/{store_id}"
    "/commerce/orders"
)
def list_store_commerce_orders(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "commerce.read"
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

    orders = list_shopify_orders(
        db=db,
        store_id=store.id,
        organization_id=store.organization_id,
    )

    return {
        "items": orders,
        "total": len(orders),
    }


# ============================================================
# AUTOMATIONS ENDPOINTS
# ============================================================


def _campaign_store_or_404(db, organization_id, store_id):
    store = db.query(Store).filter(Store.id == store_id, Store.organization_id == organization_id, Store.deleted.is_(False)).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return store


def _serialize_campaign(campaign):
    return {
        "id": campaign.id, "organization_id": campaign.organization_id,
        "store_id": campaign.store_id, "name": campaign.name,
        "automation_type": campaign.automation_type, "status": campaign.status,
        "audience_type": campaign.audience_type,
        "audience_filters": json_load(campaign.audience_filters),
        "member_count": sum(1 for member in campaign.members if member.included),
        "schedule_type": campaign.schedule_type,
        "schedule_config": json_load(campaign.schedule_config),
        "timezone": campaign.timezone, "send_window_start": campaign.send_window_start,
        "send_window_end": campaign.send_window_end, "cooldown_days": campaign.cooldown_days,
        "channel": campaign.channel, "message_template": campaign.message_template,
        "message_mode": campaign.message_mode, "whatsapp_template_id": campaign.whatsapp_template_id,
        "template_variables": campaign.template_variables,
        "created_at": campaign.created_at.isoformat() + "Z",
        "updated_at": campaign.updated_at.isoformat() + "Z",
    }


def _campaign_or_404(db, organization_id, store_id, campaign_id):
    campaign = db.query(AutomationCampaign).filter(
        AutomationCampaign.id == campaign_id,
        AutomationCampaign.organization_id == organization_id,
        AutomationCampaign.store_id == store_id,
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Automation campaign not found")
    return campaign


def _fixed_audience_ids(db, organization_id, store_id, data):
    mode = data.get("selection_mode", "explicit")
    if mode not in {"explicit", "all_filtered"}:
        raise HTTPException(400, "Invalid selection_mode")
    selected = set(data.get("selected_customer_ids") or data.get("member_ids") or [])
    if mode == "all_filtered":
        selected = {item["id"] for item in audience_metrics(db, organization_id, store_id, "dynamic", data.get("audience_filters", {}))}
        selected -= set(data.get("excluded_customer_ids", []))
    # Fixed audiences are store-scoped. Do not silently accept an org customer
    # that has no profile in the campaign's store.
    available = {item["id"] for item in audience_metrics(db, organization_id, store_id, "dynamic", {})}
    if not selected.issubset(available):
        raise HTTPException(status_code=400, detail="Customer is outside store scope")
    return selected


def _replace_campaign_members(db, campaign, organization_id, store_id, data):
    unique_ids = _fixed_audience_ids(db, organization_id, store_id, data) if campaign.audience_type == "fixed" else set()
    db.query(AutomationAudienceMember).filter(AutomationAudienceMember.automation_id == campaign.id).delete()
    ids = sorted(unique_ids)
    for offset in range(0, len(ids), 1000):
        db.bulk_insert_mappings(AutomationAudienceMember, [{"automation_id": campaign.id, "customer_id": customer_id, "included": True} for customer_id in ids[offset:offset + 1000]])
    return len(unique_ids)


def _validate_campaign_compliance(db, data, organization_id, store_id):
    if data["message_mode"] not in MESSAGE_MODES:
        raise HTTPException(400, "Invalid message_mode")
    mapping = data["template_variables"].get("body", [])
    if not isinstance(mapping, list) or not set(mapping).issubset(TEMPLATE_VARIABLES):
        raise HTTPException(400, "Invalid template variables")
    template = None
    if data["whatsapp_template_id"]:
        template = db.query(WhatsAppMessageTemplate).join(WhatsAppConnection).filter(
            WhatsAppMessageTemplate.id == data["whatsapp_template_id"],
            WhatsAppMessageTemplate.organization_id == organization_id,
            WhatsAppConnection.store_id == store_id,
            WhatsAppConnection.organization_id == organization_id,
        ).first()
        if not template:
            raise HTTPException(400, "Template is outside store scope")
        body_components = [item for item in template.components.get("items", []) if str(item.get("type", "")).lower() == "body"]
        body_text = next((item.get("text") for item in body_components if isinstance(item.get("text"), str)), None)
        if body_text is not None:
            expected_parameters = len(re.findall(r"{{\d+}}", body_text))
            if expected_parameters != len(mapping):
                raise HTTPException(400, "Template body parameter count does not match")
    if data["status"] == "active" and data["message_mode"] in {"template", "auto"}:
        if not template or template.status != "approved":
            raise HTTPException(400, "Active template delivery requires an approved template")
    return template


@app.post("/api/stores/{store_id}/automation-campaigns/audience/preview")
def preview_automation_audience(
    store_id: int,
    payload: AudiencePreviewRequest,
    membership: OrganizationMembership = Depends(require_permission("automations.read")),
    db: Session = Depends(get_db),
):
    _campaign_store_or_404(db, membership.organization_id, store_id)
    if payload.audience_type not in {"dynamic", "fixed"}:
        raise HTTPException(400, "Invalid audience_type")
    data = payload.model_dump()
    member_ids = _fixed_audience_ids(db, membership.organization_id, store_id, data) if payload.audience_type == "fixed" else data["member_ids"]
    metrics = audience_metrics(db, membership.organization_id, store_id, payload.audience_type, payload.audience_filters, list(member_ids))
    segment_distribution, country_distribution = {}, {}
    for item in metrics:
        segment_distribution[item.get("primary_segment") or "unknown"] = segment_distribution.get(item.get("primary_segment") or "unknown", 0) + 1
        country_distribution[item.get("country_code") or "unknown"] = country_distribution.get(item.get("country_code") or "unknown", 0) + 1
    return {"eligible_count": len(metrics), "sample": [explain(item) for item in metrics[:20]], "segment_distribution": segment_distribution, "country_distribution": country_distribution}


@app.get("/api/stores/{store_id}/automation-campaigns/audience/customers")
def list_automation_audience_customers(
    store_id: int,
    search: str | None = None,
    page: int = 1,
    page_size: int = 25,
    segment: str | None = None,
    priority: str | None = None,
    health: str | None = None,
    country: str | None = None,
    needs_attention: bool | None = None,
    has_orders: bool | None = None,
    sort: str = "priority_desc",
    membership: OrganizationMembership = Depends(require_permission("automations.read")),
    db: Session = Depends(get_db),
):
    from .customers.intelligence import get_customer_list
    _campaign_store_or_404(db, membership.organization_id, store_id)
    result = get_customer_list(db, membership.organization_id, store_id, segment=segment, search=search, has_orders=has_orders, page=max(1, page), page_size=min(max(1, page_size), 100), sort=sort, priority=priority, health=health, needs_attention=needs_attention, country=country)
    fields = ("id", "name", "phone", "email", "country_code", "primary_segment", "priority", "customer_score", "customer_health", "last_interaction_at", "successful_order_count", "spend_by_currency", "needs_attention")
    return {**result, "items": [{("customer_id" if key == "id" else key): item.get(key) for key in fields} for item in result["items"]]}


@app.post("/api/stores/{store_id}/automation-campaigns")
def create_automation_campaign(
    store_id: int,
    payload: AutomationCampaignPayload,
    membership: OrganizationMembership = Depends(require_permission("automations.write")),
    db: Session = Depends(get_db),
):
    store = _campaign_store_or_404(db, membership.organization_id, store_id)
    data = payload.model_dump()
    data["timezone"] = data["timezone"] or store.timezone
    validate_campaign(data, store)
    _validate_campaign_compliance(db, data, membership.organization_id, store_id)
    if data["status"] == "active" and not db.query(WhatsAppConnection).filter(WhatsAppConnection.organization_id == membership.organization_id, WhatsAppConnection.store_id == store_id, WhatsAppConnection.status == "connected").first():
        raise HTTPException(400, "WhatsApp channel is not connected")
    if db.query(AutomationCampaign).filter(AutomationCampaign.organization_id == membership.organization_id, AutomationCampaign.store_id == store_id, AutomationCampaign.name == payload.name).first():
        raise HTTPException(409, "Automation campaign name already exists")
    campaign = AutomationCampaign(
        organization_id=membership.organization_id, store_id=store_id, created_by=membership.user_id,
        **{key: data[key] for key in ("name", "automation_type", "status", "audience_type", "schedule_type", "timezone", "send_window_start", "send_window_end", "cooldown_days", "channel", "message_template", "message_mode", "whatsapp_template_id", "template_variables")},
        audience_filters=data["audience_filters"], schedule_config=data["schedule_config"],
    )
    if campaign.status == "active":
        campaign.next_run_at = initial_next_run(campaign)
        campaign.execution_enabled_at = datetime.utcnow()
    db.add(campaign); db.flush()
    member_count = _replace_campaign_members(db, campaign, membership.organization_id, store_id, data)
    if data["status"] == "active" and data["audience_type"] == "fixed" and member_count == 0:
        raise HTTPException(400, "Active fixed campaign requires at least one customer")
    db.commit(); db.refresh(campaign)
    return _serialize_campaign(campaign)


@app.get("/api/stores/{store_id}/automation-campaigns")
def list_automation_campaigns(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("automations.read")),
    db: Session = Depends(get_db),
):
    _campaign_store_or_404(db, membership.organization_id, store_id)
    items = db.query(AutomationCampaign).filter(AutomationCampaign.organization_id == membership.organization_id, AutomationCampaign.store_id == store_id).order_by(AutomationCampaign.updated_at.desc()).all()
    return {"items": [_serialize_campaign(item) for item in items], "total": len(items)}


@app.get("/api/stores/{store_id}/automation-campaigns/{campaign_id}")
def get_automation_campaign(campaign_id: int, store_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    _campaign_store_or_404(db, membership.organization_id, store_id)
    return _serialize_campaign(_campaign_or_404(db, membership.organization_id, store_id, campaign_id))


@app.put("/api/stores/{store_id}/automation-campaigns/{campaign_id}")
def update_automation_campaign(campaign_id: int, store_id: int, payload: AutomationCampaignPayload, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    store = _campaign_store_or_404(db, membership.organization_id, store_id)
    campaign = _campaign_or_404(db, membership.organization_id, store_id, campaign_id)
    previous_status = campaign.status
    data = payload.model_dump(); data["timezone"] = data["timezone"] or store.timezone
    validate_campaign(data, store)
    if previous_status == "active" and (campaign.audience_type != data["audience_type"] or campaign.audience_filters != data["audience_filters"] or data.get("member_ids") or data.get("selected_customer_ids") or data.get("selection_mode") == "all_filtered"):
        raise HTTPException(400, "Pause an active campaign before changing its audience")
    _validate_campaign_compliance(db, data, membership.organization_id, store_id)
    if data["status"] == "active" and not db.query(WhatsAppConnection).filter(WhatsAppConnection.organization_id == membership.organization_id, WhatsAppConnection.store_id == store_id, WhatsAppConnection.status == "connected").first():
        raise HTTPException(400, "WhatsApp channel is not connected")
    for key in ("name", "automation_type", "status", "audience_type", "schedule_type", "timezone", "send_window_start", "send_window_end", "cooldown_days", "channel", "message_template", "message_mode", "whatsapp_template_id", "template_variables"):
        setattr(campaign, key, data[key])
    campaign.audience_filters = data["audience_filters"]; campaign.schedule_config = data["schedule_config"]
    if campaign.status == "active":
        if campaign.execution_enabled_at is None:
            campaign.execution_enabled_at = datetime.utcnow()
        if campaign.schedule_type == "once" and campaign.last_run_at is not None:
            campaign.next_run_at = None
        elif previous_status != "active" or campaign.next_run_at is None:
            campaign.next_run_at = initial_next_run(campaign)
    elif campaign.status in {"paused", "archived"}:
        campaign.next_run_at = None
    member_count = _replace_campaign_members(db, campaign, membership.organization_id, store_id, data)
    if data["status"] == "active" and data["audience_type"] == "fixed" and member_count == 0:
        raise HTTPException(400, "Active fixed campaign requires at least one customer")
    db.commit(); db.refresh(campaign)
    return _serialize_campaign(campaign)


@app.post("/api/stores/{store_id}/automation-campaigns/{campaign_id}/simulate")
def simulate_automation_campaign(campaign_id: int, store_id: int, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    store = _campaign_store_or_404(db, membership.organization_id, store_id)
    campaign = _campaign_or_404(db, membership.organization_id, store_id, campaign_id)
    return simulate_campaign(db, campaign, store)


@app.post("/api/stores/{store_id}/automation-campaigns/{campaign_id}/duplicate")
def duplicate_automation_campaign(campaign_id: int, store_id: int, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    _campaign_store_or_404(db, membership.organization_id, store_id)
    source = _campaign_or_404(db, membership.organization_id, store_id, campaign_id)
    copy = AutomationCampaign(organization_id=source.organization_id, store_id=source.store_id, name=f"{source.name} (copy)", automation_type=source.automation_type, status="draft", audience_type=source.audience_type, audience_filters=source.audience_filters, schedule_type=source.schedule_type, schedule_config=source.schedule_config, timezone=source.timezone, send_window_start=source.send_window_start, send_window_end=source.send_window_end, cooldown_days=source.cooldown_days, channel=source.channel, message_template=source.message_template, message_mode=source.message_mode, whatsapp_template_id=source.whatsapp_template_id, template_variables=source.template_variables, created_by=membership.user_id)
    db.add(copy); db.flush()
    _replace_campaign_members(db, copy, membership.organization_id, [member.customer_id for member in source.members if member.included])
    db.commit(); db.refresh(copy)
    return _serialize_campaign(copy)


def _serialize_run(run, campaign_name=None):
    return {
        "id": run.id, "automation_id": run.automation_id,
        "campaign_name": campaign_name, "status": run.status,
        "matched_count": run.matched_count, "eligible_count": run.eligible_count,
        "sent_count": run.sent_count, "failed_count": run.failed_count,
        "excluded_count": run.excluded_count,
        "started_at": run.started_at.isoformat() + "Z" if run.started_at else None,
        "completed_at": run.completed_at.isoformat() + "Z" if run.completed_at else None,
        "scheduled_for": run.scheduled_for.isoformat() + "Z" if run.scheduled_for else None,
    }


RECOVERABLE_SKIP_REASONS = {"template_required", "template_not_approved", "connection_inactive", "invalid_phone"}


@app.get("/api/stores/{store_id}/automation-campaigns/{campaign_id}/runs")
def list_automation_campaign_runs(campaign_id: int, store_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    _campaign_store_or_404(db, membership.organization_id, store_id)
    campaign = _campaign_or_404(db, membership.organization_id, store_id, campaign_id)
    runs = db.query(AutomationRun).filter(AutomationRun.automation_id == campaign.id).order_by(AutomationRun.id.desc()).all()
    return {"items": [_serialize_run(run, campaign.name) for run in runs]}


@app.get("/api/stores/{store_id}/automation-campaigns/{campaign_id}/runs/{run_id}")
def get_automation_run(run_id: int, campaign_id: int, store_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    _campaign_store_or_404(db, membership.organization_id, store_id)
    campaign = _campaign_or_404(db, membership.organization_id, store_id, campaign_id)
    run = db.query(AutomationRun).filter(AutomationRun.id == run_id, AutomationRun.automation_id == campaign.id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    terminal = {"sent", "failed", "skipped", "ambiguous"}
    total = db.query(AutomationRecipientExecution).filter(AutomationRecipientExecution.run_id == run.id).count()
    terminal_count = db.query(AutomationRecipientExecution).filter(AutomationRecipientExecution.run_id == run.id, AutomationRecipientExecution.status.in_(terminal)).count()
    pending = total - terminal_count
    return {**_serialize_run(run, campaign.name), "total_recipients": total, "pending_count": pending}


@app.get("/api/stores/{store_id}/automation-campaigns/{campaign_id}/runs/{run_id}/recipients")
def list_run_recipients(run_id: int, campaign_id: int, store_id: int, status: str | None = None, reason: str | None = None, search: str | None = None, page: int = 1, page_size: int = 25, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    _campaign_store_or_404(db, membership.organization_id, store_id)
    campaign = _campaign_or_404(db, membership.organization_id, store_id, campaign_id)
    run = db.query(AutomationRun).filter(AutomationRun.id == run_id, AutomationRun.automation_id == campaign.id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    from .models import Customer
    query = db.query(AutomationRecipientExecution, Customer).join(Customer, AutomationRecipientExecution.customer_id == Customer.id).filter(AutomationRecipientExecution.run_id == run.id)
    if status:
        query = query.filter(AutomationRecipientExecution.status == status)
    if reason:
        query = query.filter(AutomationRecipientExecution.exclusion_reason == reason)
    if search:
        term = f"%{search.lower()}%"
        query = query.filter((Customer.name.ilike(term)) | (Customer.phone.ilike(term)) | (Customer.email.ilike(term)))
    total = query.count()
    page_size = min(max(1, page_size), 100)
    page = max(1, page)
    total_pages = max(1, (total + page_size - 1) // page_size)
    rows = query.order_by(AutomationRecipientExecution.id).offset((page - 1) * page_size).limit(page_size).all()
    items = []
    for recipient, customer in rows:
        items.append({
            "id": recipient.id, "customer_id": recipient.customer_id,
            "customer_name": customer.name, "customer_phone": customer.phone,
            "status": recipient.status, "exclusion_reason": recipient.exclusion_reason,
            "attempt_count": recipient.attempt_count,
            "next_attempt_at": recipient.next_attempt_at.isoformat() + "Z" if recipient.next_attempt_at else None,
            "sent_at": recipient.sent_at.isoformat() + "Z" if recipient.sent_at else None,
            "provider_message_id": recipient.provider_message_id,
            "error_code": recipient.error_code, "error_message": recipient.error_message,
        })
    return {"items": items, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}


@app.get("/api/stores/{store_id}/automation-campaigns/{campaign_id}/runs/{run_id}/recipients/{recipient_id}")
def get_run_recipient(recipient_id: int, run_id: int, campaign_id: int, store_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    _campaign_store_or_404(db, membership.organization_id, store_id)
    campaign = _campaign_or_404(db, membership.organization_id, store_id, campaign_id)
    run = db.query(AutomationRun).filter(AutomationRun.id == run_id, AutomationRun.automation_id == campaign.id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    from .models import Customer, AutomationDeliveryAttempt
    recipient = db.query(AutomationRecipientExecution).filter(AutomationRecipientExecution.id == recipient_id, AutomationRecipientExecution.run_id == run.id).first()
    if not recipient:
        raise HTTPException(404, "Recipient not found")
    customer = db.get(Customer, recipient.customer_id)
    attempts = db.query(AutomationDeliveryAttempt).filter(AutomationDeliveryAttempt.recipient_execution_id == recipient.id).order_by(AutomationDeliveryAttempt.attempt_number).all()
    return {
        "id": recipient.id, "run_id": recipient.run_id, "customer_id": recipient.customer_id,
        "customer_name": customer.name if customer else None, "customer_phone": customer.phone if customer else None,
        "status": recipient.status, "exclusion_reason": recipient.exclusion_reason,
        "rendered_message": recipient.rendered_message,
        "attempt_count": recipient.attempt_count,
        "next_attempt_at": recipient.next_attempt_at.isoformat() + "Z" if recipient.next_attempt_at else None,
        "sent_at": recipient.sent_at.isoformat() + "Z" if recipient.sent_at else None,
        "provider_message_id": recipient.provider_message_id,
        "error_code": recipient.error_code, "error_message": recipient.error_message,
        "template_data": recipient.template_data,
        "attempts": [{"id": a.id, "attempt_number": a.attempt_number, "status": a.status, "provider_message_id": a.provider_message_id, "error_code": a.error_code, "error_message": a.error_message, "started_at": a.started_at.isoformat() + "Z" if a.started_at else None, "finished_at": a.finished_at.isoformat() + "Z" if a.finished_at else None} for a in attempts],
    }


@app.post("/api/stores/{store_id}/automation-campaigns/{campaign_id}/runs/{run_id}/recipients/{recipient_id}/retry")
def retry_run_recipient(recipient_id: int, run_id: int, campaign_id: int, store_id: int, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    from .automation_execution_engine import utcnow
    from .models import Customer, WhatsAppConnection
    _campaign_store_or_404(db, membership.organization_id, store_id)
    campaign = _campaign_or_404(db, membership.organization_id, store_id, campaign_id)
    run = db.query(AutomationRun).filter(AutomationRun.id == run_id, AutomationRun.automation_id == campaign.id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    recipient = db.query(AutomationRecipientExecution).filter(AutomationRecipientExecution.id == recipient_id, AutomationRecipientExecution.run_id == run.id).first()
    if not recipient:
        raise HTTPException(404, "Recipient not found")
    if recipient.status in {"queued", "processing", "sending", "retry_wait"}:
        raise HTTPException(400, "Recipient is already active")
    if recipient.status == "ambiguous":
        raise HTTPException(400, "Ambiguous recipients cannot be retried to prevent duplicates")
    if recipient.status == "sent":
        raise HTTPException(400, "Sent recipients do not need retry")
    if recipient.status == "skipped" and recipient.exclusion_reason not in RECOVERABLE_SKIP_REASONS:
        raise HTTPException(400, "This skip reason is not recoverable")
    customer = db.get(Customer, recipient.customer_id)
    if not customer or not customer.phone:
        raise HTTPException(400, "Customer phone is unavailable")
    connection = db.query(WhatsAppConnection).filter(WhatsAppConnection.store_id == campaign.store_id, WhatsAppConnection.organization_id == campaign.organization_id, WhatsAppConnection.status == "connected").first()
    if not connection:
        raise HTTPException(400, "WhatsApp connection is inactive")
    from .whatsapp_compliance import evaluate_whatsapp_delivery_eligibility
    now = utcnow()
    compliance = evaluate_whatsapp_delivery_eligibility(db, campaign, connection, recipient.customer_id, now)
    if not compliance["allowed"]:
        raise HTTPException(400, f"Compliance check failed: {compliance['reason']}")
    recipient.status = "queued"
    recipient.error_code = None
    recipient.error_message = None
    recipient.next_attempt_at = now
    recipient.claimed_at = None
    recipient.lease_expires_at = None
    if run.status in {"completed", "partial", "failed"}:
        run.status = "pending"
        run.completed_at = None
        states = [r[0] for r in db.query(AutomationRecipientExecution.status).filter(AutomationRecipientExecution.run_id == run.id).all()]
        run.sent_count = states.count("sent")
        run.failed_count = states.count("failed") + states.count("ambiguous")
        run.excluded_count = states.count("skipped")
    db.commit()
    return {"ok": True, "recipient_id": recipient.id, "status": recipient.status}


# ============================================================
# AUTOMATION FLOWS V2.2 — ENDPOINTS
# ============================================================

from pydantic import BaseModel as _PydanticBaseModel
from .automation_flow_graph import validate_graph
from .automation_flow_engine import (
    materialize_flow_trigger as _materialize_flow_trigger,
    utcnow as _utcnow,
)
from .automation_flow_helpers import (
    serialize_flow as _sf, serialize_version as _sv,
    serialize_run as _sr, serialize_recipient as _srec,
)


class _FlowCreate(_PydanticBaseModel):
    name: str
    description: str | None = None
    graph: dict = {}


class _FlowUpdate(_PydanticBaseModel):
    name: str | None = None
    description: str | None = None
    graph: dict | None = None


class _FlowVersionPublish(_PydanticBaseModel):
    graph: dict


class _FlowRunCreate(_PydanticBaseModel):
    customer_ids: list[int]
    trigger_key: str | None = None


@app.post("/api/stores/{store_id}/automation-flows")
def create_flow(store_id: int, payload: _FlowCreate, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    _campaign_store_or_404(db, membership.organization_id, store_id)
    if payload.graph:
        errors = validate_graph(payload.graph)
        if errors:
            raise HTTPException(422, detail={"errors": errors})
    flow = AutomationFlow(
        organization_id=membership.organization_id, store_id=store_id,
        name=payload.name, description=payload.description,
        status="draft", created_by=membership.user_id,
    )
    db.add(flow)
    db.flush()
    if payload.graph:
        ver = AutomationFlowVersion(
            flow_id=flow.id, organization_id=membership.organization_id,
            version_number=1, graph=payload.graph,
        )
        db.add(ver)
        db.flush()
        flow.current_version_id = ver.id
    db.commit()
    return _sf(flow)


@app.get("/api/stores/{store_id}/automation-flows")
def list_flows(store_id: int, status: str | None = None, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    q = db.query(AutomationFlow).filter(
        AutomationFlow.organization_id == membership.organization_id,
        AutomationFlow.store_id == store_id,
    )
    if status:
        q = q.filter(AutomationFlow.status == status)
    return [_sf(f) for f in q.order_by(AutomationFlow.updated_at.desc()).all()]


@app.get("/api/stores/{store_id}/automation-flows/{flow_id}")
def get_flow(store_id: int, flow_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != membership.organization_id or flow.store_id != store_id:
        raise HTTPException(404, detail="Flow not found")
    result = _sf(flow)
    if flow.current_version_id:
        ver = db.get(AutomationFlowVersion, flow.current_version_id)
        if ver:
            result["current_version"] = _sv(ver)
    return result


@app.put("/api/stores/{store_id}/automation-flows/{flow_id}")
def update_flow(store_id: int, flow_id: int, payload: _FlowUpdate, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != membership.organization_id or flow.store_id != store_id:
        raise HTTPException(404, detail="Flow not found")
    if flow.status == "active":
        raise HTTPException(409, detail="Cannot edit active flow; duplicate or archive first")
    if payload.name is not None:
        flow.name = payload.name
    if payload.description is not None:
        flow.description = payload.description
    if payload.graph is not None:
        errors = validate_graph(payload.graph)
        if errors:
            raise HTTPException(422, detail={"errors": errors})
        max_ver = db.query(AutomationFlowVersion.version_number).filter(
            AutomationFlowVersion.flow_id == flow.id
        ).order_by(AutomationFlowVersion.version_number.desc()).first()
        next_num = (max_ver[0] if max_ver else 0) + 1
        ver = AutomationFlowVersion(
            flow_id=flow.id, organization_id=membership.organization_id,
            version_number=next_num, graph=payload.graph,
        )
        db.add(ver)
        db.flush()
        flow.current_version_id = ver.id
    flow.updated_at = _utcnow()
    db.commit()
    return _sf(flow)


@app.delete("/api/stores/{store_id}/automation-flows/{flow_id}")
def archive_flow(store_id: int, flow_id: int, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != membership.organization_id or flow.store_id != store_id:
        raise HTTPException(404, detail="Flow not found")
    flow.status = "archived"
    flow.updated_at = _utcnow()
    db.commit()
    return {"status": "archived", "id": flow.id}


@app.get("/api/stores/{store_id}/automation-flows/{flow_id}/versions")
def list_versions(store_id: int, flow_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != membership.organization_id or flow.store_id != store_id:
        raise HTTPException(404, detail="Flow not found")
    versions = db.query(AutomationFlowVersion).filter(
        AutomationFlowVersion.flow_id == flow_id
    ).order_by(AutomationFlowVersion.version_number.desc()).all()
    return [_sv(v) for v in versions]


@app.post("/api/stores/{store_id}/automation-flows/{flow_id}/versions")
def create_version(store_id: int, flow_id: int, payload: _FlowVersionPublish, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != membership.organization_id or flow.store_id != store_id:
        raise HTTPException(404, detail="Flow not found")
    errors = validate_graph(payload.graph)
    if errors:
        raise HTTPException(422, detail={"errors": errors})
    max_ver = db.query(AutomationFlowVersion.version_number).filter(
        AutomationFlowVersion.flow_id == flow_id
    ).order_by(AutomationFlowVersion.version_number.desc()).first()
    next_num = (max_ver[0] if max_ver else 0) + 1
    ver = AutomationFlowVersion(
        flow_id=flow_id, organization_id=membership.organization_id,
        version_number=next_num, graph=payload.graph,
    )
    db.add(ver)
    db.flush()
    flow.current_version_id = ver.id
    flow.updated_at = _utcnow()
    db.commit()
    return _sv(ver)


@app.post("/api/stores/{store_id}/automation-flows/{flow_id}/versions/{version_id}/publish")
def publish_version(store_id: int, flow_id: int, version_id: int, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != membership.organization_id or flow.store_id != store_id:
        raise HTTPException(404, detail="Flow not found")
    ver = db.get(AutomationFlowVersion, version_id)
    if not ver or ver.flow_id != flow_id:
        raise HTTPException(404, detail="Version not found")
    if ver.published_at:
        raise HTTPException(409, detail="Version already published")
    ver.published_at = _utcnow()
    flow.updated_at = _utcnow()
    db.commit()
    return _sv(ver)


@app.post("/api/stores/{store_id}/automation-flows/{flow_id}/activate")
def activate_flow(store_id: int, flow_id: int, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != membership.organization_id or flow.store_id != store_id:
        raise HTTPException(404, detail="Flow not found")
    if not flow.current_version_id:
        raise HTTPException(409, detail="No version to activate")
    ver = db.get(AutomationFlowVersion, flow.current_version_id)
    if not ver:
        raise HTTPException(404, detail="Current version not found")
    if not ver.published_at:
        raise HTTPException(409, detail="Version must be published before activation")
    ver.activated_at = _utcnow()
    flow.active_version_id = ver.id
    flow.status = "active"
    flow.updated_at = _utcnow()
    db.commit()
    return _sf(flow)


@app.post("/api/stores/{store_id}/automation-flows/{flow_id}/deactivate")
def deactivate_flow(store_id: int, flow_id: int, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != membership.organization_id or flow.store_id != store_id:
        raise HTTPException(404, detail="Flow not found")
    flow.status = "draft"
    flow.updated_at = _utcnow()
    db.commit()
    return _sf(flow)


@app.post("/api/stores/{store_id}/automation-flows/{flow_id}/runs")
def trigger_flow_run(store_id: int, flow_id: int, payload: _FlowRunCreate, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != membership.organization_id or flow.store_id != store_id:
        raise HTTPException(404, detail="Flow not found")
    if flow.status != "active" or not flow.active_version_id:
        raise HTTPException(409, detail="Flow must be active to trigger")
    customers = db.query(Customer).join(
        CustomerStoreProfile,
        CustomerStoreProfile.customer_id == Customer.id,
    ).filter(
        Customer.id.in_(payload.customer_ids),
        Customer.organization_id == membership.organization_id,
        CustomerStoreProfile.store_id == store_id,
    ).all()
    found_ids = {c.id for c in customers}
    missing = set(payload.customer_ids) - found_ids
    if missing:
        raise HTTPException(422, detail={"errors": [f"Customer {cid} not found" for cid in sorted(missing)]})
    run = _materialize_flow_trigger(db, flow, payload.customer_ids, payload.trigger_key)
    if not run:
        raise HTTPException(409, detail="Trigger key already used or flow not materializable")
    return _sr(run)


@app.get("/api/stores/{store_id}/automation-flows/{flow_id}/runs")
def list_flow_runs(store_id: int, flow_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != membership.organization_id or flow.store_id != store_id:
        raise HTTPException(404, detail="Flow not found")
    runs = db.query(AutomationFlowRun).filter(
        AutomationFlowRun.flow_id == flow_id
    ).order_by(AutomationFlowRun.created_at.desc()).all()
    return [_sr(r) for r in runs]


@app.get("/api/stores/{store_id}/automation-flows/{flow_id}/runs/{run_id}")
def get_flow_run(store_id: int, flow_id: int, run_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != membership.organization_id or flow.store_id != store_id:
        raise HTTPException(404, detail="Flow not found")
    run = db.get(AutomationFlowRun, run_id)
    if not run or run.flow_id != flow_id:
        raise HTTPException(404, detail="Run not found")
    recipients = db.query(AutomationFlowRecipientExecution).filter(
        AutomationFlowRecipientExecution.flow_run_id == run_id
    ).all()
    result = _sr(run)
    result["recipients"] = [_srec(r) for r in recipients]
    return result


@app.get("/api/stores/{store_id}/automation-flows/{flow_id}/runs/{run_id}/recipients")
def list_flow_run_recipients(store_id: int,
    flow_id: int, run_id: int,
    status: str | None = None, search: str | None = None,
    page: int = 1, size: int = 50,
    membership: OrganizationMembership = Depends(require_permission("automations.read")),
    db: Session = Depends(get_db),
):
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != membership.organization_id or flow.store_id != store_id:
        raise HTTPException(404, detail="Flow not found")
    run = db.get(AutomationFlowRun, run_id)
    if not run or run.flow_id != flow_id:
        raise HTTPException(404, detail="Run not found")
    q = db.query(AutomationFlowRecipientExecution).filter(
        AutomationFlowRecipientExecution.flow_run_id == run_id,
    )
    if status:
        q = q.filter(AutomationFlowRecipientExecution.status == status)
    if search:
        q = q.join(Customer).filter(
            (Customer.name.ilike(f"%{search}%")) | (Customer.phone.ilike(f"%{search}%"))
        )
    total = q.count()
    items = q.order_by(AutomationFlowRecipientExecution.id).offset((page - 1) * size).limit(size).all()
    return {"items": [_srec(r) for r in items], "total": total, "page": page, "size": size, "pages": max(1, -(-total // size))}


@app.get("/api/stores/{store_id}/automation-flows/{flow_id}/runs/{run_id}/recipients/{recipient_id}")
def get_flow_recipient_detail(store_id: int, flow_id: int, run_id: int, recipient_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != membership.organization_id or flow.store_id != store_id:
        raise HTTPException(404, detail="Flow not found")
    recipient = db.get(AutomationFlowRecipientExecution, recipient_id)
    if not recipient or recipient.flow_run_id != run_id:
        raise HTTPException(404, detail="Recipient not found")
    node_execs = db.query(AutomationNodeExecution).filter(
        AutomationNodeExecution.flow_recipient_execution_id == recipient_id
    ).order_by(AutomationNodeExecution.started_at).all()
    result = _srec(recipient)
    result["node_executions"] = [
        {"id": ne.id, "node_id": ne.node_id, "node_type": ne.node_type,
         "status": ne.status, "outcome": ne.outcome,
         "provider_message_id": ne.provider_message_id,
         "error_code": ne.error_code, "error_message": ne.error_message,
         "metadata": ne.extra_data,
         "started_at": ne.started_at.isoformat() if ne.started_at else None,
         "completed_at": ne.completed_at.isoformat() if ne.completed_at else None}
        for ne in node_execs
    ]
    return result


@app.post("/api/stores/{store_id}/automation-flows/{flow_id}/runs/{run_id}/recipients/{recipient_id}/retry")
def retry_flow_recipient(store_id: int, flow_id: int, run_id: int, recipient_id: int, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != membership.organization_id or flow.store_id != store_id:
        raise HTTPException(404, detail="Flow not found")
    recipient = db.get(AutomationFlowRecipientExecution, recipient_id)
    if not recipient or recipient.flow_run_id != run_id:
        raise HTTPException(404, detail="Recipient not found")
    if recipient.status not in ("failed", "ambiguous", "completed"):
        raise HTTPException(409, detail=f"Cannot retry recipient in '{recipient.status}' status")
    now = _utcnow()
    recipient.status = "active"
    recipient.error_code = None
    recipient.error_message = None
    recipient.claim_token = None
    recipient.claim_expires_at = None
    recipient.next_action_at = now
    recipient.started_at = now
    recipient.completed_at = None
    run = db.get(AutomationFlowRun, run_id)
    statuses = [r[0] for r in db.query(AutomationFlowRecipientExecution.status).filter(
        AutomationFlowRecipientExecution.flow_run_id == run_id,
    ).all()]
    run.failed_recipients = sum(1 for s in statuses if s in ("failed", "ambiguous"))
    run.completed_recipients = sum(1 for s in statuses if s == "completed")
    if run.status == "completed":
        run.status = "pending"
        run.completed_at = None
    db.commit()
    return _srec(recipient)


@app.post("/api/stores/{store_id}/automation-flows/simulate")
def simulate_flow(store_id: int, payload: _FlowCreate, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    graph = payload.graph
    if not graph:
        raise HTTPException(422, detail={"errors": ["Graph is required for simulation"]})
    errors = validate_graph(graph)
    if errors:
        return {"valid": False, "errors": errors, "warnings": []}
    warnings: list[str] = []
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    message_nodes = [n for n in nodes if n.get("type") == "message"]
    wait_nodes = [n for n in nodes if n.get("type") == "wait"]
    condition_nodes = [n for n in nodes if n.get("type") == "condition"]
    end_nodes = [n for n in nodes if n.get("type") == "end"]
    if len(message_nodes) == 0:
        warnings.append("Flow has no message nodes")
    if len(wait_nodes) > 5:
        warnings.append(f"Flow has {len(wait_nodes)} wait nodes")
    return {
        "valid": True, "errors": [], "warnings": warnings,
        "summary": {
            "total_nodes": len(nodes), "message_nodes": len(message_nodes),
            "wait_nodes": len(wait_nodes), "condition_nodes": len(condition_nodes),
            "end_nodes": len(end_nodes),
        },
    }


@app.get(
    "/api/stores/{store_id}/automations"
)
def list_automations(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "automations.read"
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

    automations = (
        db.query(Automation)
        .filter(
            Automation.organization_id
            == membership.organization_id,
            (Automation.store_id == store_id)
            | (Automation.store_id.is_(None)),
        )
        .order_by(Automation.updated_at.desc())
        .all()
    )

    items = []

    for a in automations:
        last_exec = (
            db.query(AutomationExecution)
            .filter(
                AutomationExecution.automation_id
                == a.id,
            )
            .order_by(
                AutomationExecution.id.desc()
            )
            .first()
        )

        items.append(
            {
                "id": a.id,
                "organization_id": (
                    a.organization_id
                ),
                "store_id": a.store_id,
                "name": a.name,
                "description": a.description,
                "active": a.active,
                "trigger_type": a.trigger_type,
                "conditions_json": json.loads(
                    a.conditions_json
                )
                if a.conditions_json
                else [],
                "actions_json": json.loads(
                    a.actions_json
                )
                if a.actions_json
                else [],
                "created_by": a.created_by,
                "created_at": (
                    a.created_at.isoformat()
                    + "Z"
                    if a.created_at
                    else None
                ),
                "updated_at": (
                    a.updated_at.isoformat()
                    + "Z"
                    if a.updated_at
                    else None
                ),
                "last_execution": (
                    {
                        "id": last_exec.id,
                        "status": (
                            last_exec.status
                        ),
                        "started_at": (
                            last_exec.started_at.isoformat()
                            + "Z"
                            if last_exec.started_at
                            else None
                        ),
                        "completed_at": (
                            last_exec.completed_at.isoformat()
                            + "Z"
                            if last_exec.completed_at
                            else None
                        ),
                    }
                    if last_exec
                    else None
                ),
            }
        )

    return {
        "items": items,
        "total": len(items),
    }


@app.post(
    "/api/stores/{store_id}/automations"
)
def create_automation(
    store_id: int,
    payload: AutomationCreate,
    membership: OrganizationMembership = Depends(
        require_permission(
            "automations.write"
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

    if (
        payload.trigger_type
        not in VALID_TRIGGER_TYPES
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid trigger_type",
        )

    existing = (
        db.query(Automation)
        .filter(
            Automation.organization_id
            == membership.organization_id,
            Automation.store_id == store_id,
            Automation.name == payload.name,
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Automation with this name "
            "already exists in this store",
        )

    automation = Automation(
        organization_id=(
            membership.organization_id
        ),
        store_id=store_id,
        name=payload.name,
        description=payload.description,
        active=payload.active,
        trigger_type=payload.trigger_type,
        conditions_json=json.dumps(
            payload.conditions_json
        ),
        actions_json=json.dumps(
            payload.actions_json
        ),
        created_by=membership.user_id,
    )

    db.add(automation)
    db.commit()
    db.refresh(automation)

    return {
        "id": automation.id,
        "organization_id": (
            automation.organization_id
        ),
        "store_id": automation.store_id,
        "name": automation.name,
        "description": automation.description,
        "active": automation.active,
        "trigger_type": automation.trigger_type,
        "conditions_json": json.loads(
            automation.conditions_json
        ),
        "actions_json": json.loads(
            automation.actions_json
        ),
        "created_by": automation.created_by,
        "created_at": (
            automation.created_at.isoformat()
            + "Z"
            if automation.created_at
            else None
        ),
        "updated_at": (
            automation.updated_at.isoformat()
            + "Z"
            if automation.updated_at
            else None
        ),
    }


@app.get(
    "/api/stores/{store_id}"
    "/automations/{automation_id}"
)
def get_automation(
    store_id: int,
    automation_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "automations.read"
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

    automation = (
        db.query(Automation)
        .filter(
            Automation.id == automation_id,
            Automation.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not automation:
        raise HTTPException(
            status_code=404,
            detail="Automation not found",
        )

    return {
        "id": automation.id,
        "organization_id": (
            automation.organization_id
        ),
        "store_id": automation.store_id,
        "name": automation.name,
        "description": automation.description,
        "active": automation.active,
        "trigger_type": automation.trigger_type,
        "conditions_json": json.loads(
            automation.conditions_json
        ),
        "actions_json": json.loads(
            automation.actions_json
        ),
        "created_by": automation.created_by,
        "created_at": (
            automation.created_at.isoformat()
            + "Z"
            if automation.created_at
            else None
        ),
        "updated_at": (
            automation.updated_at.isoformat()
            + "Z"
            if automation.updated_at
            else None
        ),
    }


@app.put(
    "/api/stores/{store_id}"
    "/automations/{automation_id}"
)
def update_automation(
    store_id: int,
    automation_id: int,
    payload: AutomationUpdate,
    membership: OrganizationMembership = Depends(
        require_permission(
            "automations.write"
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

    automation = (
        db.query(Automation)
        .filter(
            Automation.id == automation_id,
            Automation.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not automation:
        raise HTTPException(
            status_code=404,
            detail="Automation not found",
        )

    if (
        payload.trigger_type is not None
        and payload.trigger_type
        not in VALID_TRIGGER_TYPES
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid trigger_type",
        )

    if payload.name is not None:
        automation.name = payload.name

    if payload.description is not None:
        automation.description = (
            payload.description
        )

    if payload.store_id is not None:
        automation.store_id = (
            payload.store_id
        )

    if payload.active is not None:
        automation.active = payload.active

    if payload.trigger_type is not None:
        automation.trigger_type = (
            payload.trigger_type
        )

    if payload.conditions_json is not None:
        automation.conditions_json = json.dumps(
            payload.conditions_json
        )

    if payload.actions_json is not None:
        automation.actions_json = json.dumps(
            payload.actions_json
        )

    automation.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(automation)

    return {
        "id": automation.id,
        "organization_id": (
            automation.organization_id
        ),
        "store_id": automation.store_id,
        "name": automation.name,
        "description": automation.description,
        "active": automation.active,
        "trigger_type": automation.trigger_type,
        "conditions_json": json.loads(
            automation.conditions_json
        ),
        "actions_json": json.loads(
            automation.actions_json
        ),
        "created_by": automation.created_by,
        "created_at": (
            automation.created_at.isoformat()
            + "Z"
            if automation.created_at
            else None
        ),
        "updated_at": (
            automation.updated_at.isoformat()
            + "Z"
            if automation.updated_at
            else None
        ),
    }


@app.delete(
    "/api/stores/{store_id}"
    "/automations/{automation_id}"
)
def delete_automation(
    store_id: int,
    automation_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "automations.write"
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

    automation = (
        db.query(Automation)
        .filter(
            Automation.id == automation_id,
            Automation.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not automation:
        raise HTTPException(
            status_code=404,
            detail="Automation not found",
        )

    db.delete(automation)
    db.commit()

    return {"ok": True}


@app.post(
    "/api/stores/{store_id}"
    "/automations/{automation_id}/toggle"
)
def toggle_automation(
    store_id: int,
    automation_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "automations.write"
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

    automation = (
        db.query(Automation)
        .filter(
            Automation.id == automation_id,
            Automation.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not automation:
        raise HTTPException(
            status_code=404,
            detail="Automation not found",
        )

    automation.active = not automation.active
    automation.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(automation)

    return {
        "id": automation.id,
        "active": automation.active,
        "updated_at": (
            automation.updated_at.isoformat()
            + "Z"
            if automation.updated_at
            else None
        ),
    }


@app.post(
    "/api/stores/{store_id}"
    "/automations/{automation_id}/run"
)
def run_automation(
    store_id: int,
    automation_id: int,
    payload: AutomationRunRequest,
    membership: OrganizationMembership = Depends(
        require_permission(
            "automations.write"
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

    automation = (
        db.query(Automation)
        .filter(
            Automation.id == automation_id,
            Automation.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not automation:
        raise HTTPException(
            status_code=404,
            detail="Automation not found",
        )

    execution = execute_automation(
        db=db,
        automation=automation,
        event_type=payload.event_type,
        payload=payload.payload,
    )

    return {
        "id": execution.id,
        "automation_id": (
            execution.automation_id
        ),
        "status": execution.status,
        "event_type": execution.event_type,
        "input_json": json.loads(
            execution.input_json
        ),
        "result_json": json.loads(
            execution.result_json
        ),
        "error_message": (
            execution.error_message
        ),
        "started_at": (
            execution.started_at.isoformat()
            + "Z"
            if execution.started_at
            else None
        ),
        "completed_at": (
            execution.completed_at.isoformat()
            + "Z"
            if execution.completed_at
            else None
        ),
    }


@app.get(
    "/api/stores/{store_id}"
    "/automations/{automation_id}"
    "/executions"
)
def list_automation_executions(
    store_id: int,
    automation_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "automations.read"
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

    automation = (
        db.query(Automation)
        .filter(
            Automation.id == automation_id,
            Automation.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not automation:
        raise HTTPException(
            status_code=404,
            detail="Automation not found",
        )

    executions = (
        db.query(AutomationExecution)
        .filter(
            AutomationExecution.automation_id
            == automation_id,
            AutomationExecution.organization_id
            == membership.organization_id,
        )
        .order_by(
            AutomationExecution.id.desc()
        )
        .all()
    )

    items = []

    for e in executions:
        items.append(
            {
                "id": e.id,
                "automation_id": (
                    e.automation_id
                ),
                "automation_name": (
                    automation.name
                ),
                "status": e.status,
                "event_type": e.event_type,
                "event_id": e.event_id,
                "input_json": json.loads(
                    e.input_json
                ),
                "result_json": json.loads(
                    e.result_json
                ),
                "error_message": (
                    e.error_message
                ),
                "started_at": (
                    e.started_at.isoformat()
                    + "Z"
                    if e.started_at
                    else None
                ),
                "completed_at": (
                    e.completed_at.isoformat()
                    + "Z"
                    if e.completed_at
                    else None
                ),
            }
        )

    return {
        "items": items,
        "total": len(items),
    }


@app.get(
    "/api/stores/{store_id}"
    "/automation-executions"
)
def list_all_automation_executions(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "automations.read"
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

    executions = (
        db.query(AutomationExecution)
        .filter(
            AutomationExecution.organization_id
            == membership.organization_id,
            AutomationExecution.store_id
            == store_id,
        )
        .order_by(
            AutomationExecution.id.desc()
        )
        .limit(100)
        .all()
    )

    items = []

    for e in executions:
        auto = (
            db.query(Automation)
            .filter(
                Automation.id
                == e.automation_id,
            )
            .first()
        )

        items.append(
            {
                "id": e.id,
                "automation_id": (
                    e.automation_id
                ),
                "automation_name": (
                    auto.name
                    if auto
                    else "Deleted"
                ),
                "status": e.status,
                "event_type": e.event_type,
                "event_id": e.event_id,
                "input_json": json.loads(
                    e.input_json
                ),
                "result_json": json.loads(
                    e.result_json
                ),
                "error_message": (
                    e.error_message
                ),
                "started_at": (
                    e.started_at.isoformat()
                    + "Z"
                    if e.started_at
                    else None
                ),
                "completed_at": (
                    e.completed_at.isoformat()
                    + "Z"
                    if e.completed_at
                    else None
                ),
            }
        )

    return {
        "items": items,
        "total": len(items),
    }


# ============================================================
# ANALYTICS ENDPOINTS
# ============================================================


@app.get(
    "/api/stores/{store_id}"
    "/analytics/summary"
)
def get_analytics_summary(
    store_id: int,
    date_from: str | None = None,
    date_to: str | None = None,
    membership: OrganizationMembership = Depends(
        require_permission(
            "analytics.read"
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

    d_from, d_to = get_date_range(
        date_from, date_to
    )

    return get_summary(
        db=db,
        organization_id=membership.organization_id,
        store_id=store_id,
        date_from=d_from,
        date_to=d_to,
    )


@app.get(
    "/api/stores/{store_id}"
    "/analytics/timeseries"
)
def get_analytics_timeseries(
    store_id: int,
    date_from: str | None = None,
    date_to: str | None = None,
    membership: OrganizationMembership = Depends(
        require_permission(
            "analytics.read"
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

    d_from, d_to = get_date_range(
        date_from, date_to
    )

    return get_timeseries(
        db=db,
        organization_id=membership.organization_id,
        store_id=store_id,
        date_from=d_from,
        date_to=d_to,
    )


@app.get(
    "/api/stores/{store_id}"
    "/analytics/conversations"
)
def get_analytics_conversations(
    store_id: int,
    date_from: str | None = None,
    date_to: str | None = None,
    membership: OrganizationMembership = Depends(
        require_permission(
            "analytics.read"
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

    d_from, d_to = get_date_range(
        date_from, date_to
    )

    return get_conversations_analytics(
        db=db,
        organization_id=membership.organization_id,
        store_id=store_id,
        date_from=d_from,
        date_to=d_to,
    )


@app.get(
    "/api/stores/{store_id}"
    "/analytics/commerce"
)
def get_analytics_commerce(
    store_id: int,
    date_from: str | None = None,
    date_to: str | None = None,
    membership: OrganizationMembership = Depends(
        require_permission(
            "analytics.read"
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

    d_from, d_to = get_date_range(
        date_from, date_to
    )

    return get_commerce_analytics(
        db=db,
        organization_id=membership.organization_id,
        store_id=store_id,
        date_from=d_from,
        date_to=d_to,
    )


@app.get(
    "/api/stores/{store_id}"
    "/analytics/automations"
)
def get_analytics_automations(
    store_id: int,
    date_from: str | None = None,
    date_to: str | None = None,
    membership: OrganizationMembership = Depends(
        require_permission(
            "analytics.read"
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

    d_from, d_to = get_date_range(
        date_from, date_to
    )

    return get_automations_analytics(
        db=db,
        organization_id=membership.organization_id,
        store_id=store_id,
        date_from=d_from,
        date_to=d_to,
    )


@app.get(
    "/api/stores/{store_id}/operations/summary"
)
def get_operations_center_summary(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "analytics.read"
        )
    ),
    db: Session = Depends(get_db),
):
    from .operations import get_operations_summary

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

    return get_operations_summary(
        db=db,
        organization_id=membership.organization_id,
        store_id=store_id,
    )


# ============================================================
# CUSTOMER INTELLIGENCE
# ============================================================


@app.get("/api/customers/summary")
def get_customers_summary(
    store_id: int | None = None,
    membership: OrganizationMembership = Depends(
        require_permission("customers.read")
    ),
    db: Session = Depends(get_db),
):
    from .customers.intelligence import get_summary

    if store_id is not None:
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

    return get_summary(
        db=db,
        organization_id=membership.organization_id,
        store_id=store_id,
    )


@app.get("/api/customers")
def list_customers(
    store_id: int | None = None,
    segment: str | None = None,
    flag: str | None = None,
    search: str | None = None,
    has_orders: bool | None = None,
    page: int = 1,
    page_size: int = 25,
    sort: str = "last_interaction_desc",
    # Phase 2 filters
    priority: str | None = None,
    health: str | None = None,
    needs_attention: bool | None = None,
    membership: OrganizationMembership = Depends(
        require_permission("customers.read")
    ),
    db: Session = Depends(get_db),
):
    from .customers.intelligence import get_customer_list

    if store_id is not None:
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


@app.get("/api/customers/{customer_id}")
def get_customer_detail(
    customer_id: int,
    store_id: int | None = None,
    membership: OrganizationMembership = Depends(
        require_permission("customers.read")
    ),
    db: Session = Depends(get_db),
):
    from .customers.intelligence import (
        get_customer_detail,
    )

    if store_id is not None:
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


@app.get("/api/stores/{store_id}/dropi")
def get_dropi_connection(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "stores.read"
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

    connection = (
        db.query(DropiConnection)
        .filter(
            DropiConnection.store_id
            == store.id,
            DropiConnection.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not connection:
        return {
            "connected": False,
            "status": "disconnected",
            "external_store_id": None,
            "api_url": None,
            "webhook_url": None,
            "connected_at": None,
            "last_sync_at": None,
            "last_error": None,
        }

    return {
        "connected":
            connection.status
            == "connected",

        "status":
            connection.status,

        "external_store_id":
            connection.external_store_id,

        "api_url":
            connection.api_url,

        "webhook_url":
            (
                "https://api.diaglob.tech"
                "/api/webhooks/dropi/"
                f"{connection.webhook_token}"
            ),

        "connected_at":
            (
                connection.connected_at.isoformat()
                + "Z"
                if connection.connected_at
                else None
            ),

        "last_sync_at":
            (
                connection.last_sync_at.isoformat()
                + "Z"
                if connection.last_sync_at
                else None
            ),

        "last_error":
            connection.last_error,
    }


@app.post("/api/stores/{store_id}/dropi/connect")
def connect_dropi(
    store_id: int,
    payload: DropiConnectRequest,
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

    if not store.active:
        raise HTTPException(
            status_code=409,
            detail={
                "code":
                    "STORE_NOT_ACTIVE",

                "message":
                    (
                        "La tienda debe estar activa "
                        "para conectar Dropi."
                    ),
            },
        )

    existing_connection = (
        db.query(DropiConnection)
        .filter(
            DropiConnection.store_id
            == store.id,
        )
        .first()
    )

    if existing_connection:
        raise HTTPException(
            status_code=409,
            detail={
                "code":
                    "DROPPI_ALREADY_CONNECTED",

                "message":
                    (
                        "Esta tienda ya tiene "
                        "una conexión con Dropi."
                    ),
            },
        )

    api_token = (
        payload.api_token
        or ""
    ).strip()

    if not api_token:
        raise HTTPException(
            status_code=400,
            detail={
                "code":
                    "DROPPI_TOKEN_REQUIRED",

                "message":
                    "El token de Dropi es obligatorio.",
            },
        )

    try:
        encrypted_token = (
            encrypt_dropi_secret(
                api_token
            )
        )

    except (
        RuntimeError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code":
                    "DROPPI_ENCRYPTION_NOT_CONFIGURED",

                "message":
                    (
                        "No fue posible almacenar "
                        "las credenciales de Dropi."
                    ),
            },
        ) from exc

    now = datetime.utcnow()

    connection = DropiConnection(
        organization_id=
            membership.organization_id,

        store_id=
            store.id,

        api_token_encrypted=
            encrypted_token,

        webhook_token=
            secrets.token_urlsafe(32),

        status=
            "connected",

        connected_at=
            now,

        last_sync_at=
            None,

        last_error=
            None,

        created_at=
            now,

        updated_at=
            now,
    )

    db.add(connection)

    try:
        db.commit()
        db.refresh(connection)

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail={
                "code":
                    "DROPPI_CONNECTION_SAVE_FAILED",

                "message":
                    (
                        "No fue posible guardar "
                        "la conexión con Dropi."
                    ),
            },
        )

    return {
        "ok": True,
        "connected": True,
        "store_id": store.id,
        "status": connection.status,

        "webhook_url":
            (
                "https://api.diaglob.tech"
                "/api/webhooks/dropi/"
                f"{connection.webhook_token}"
            ),
    }


@app.delete("/api/stores/{store_id}/dropi/disconnect")
def disconnect_dropi(
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
            Store.deleted.is_(False),
        )
        .first()
    )

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found",
        )

    connection = (
        db.query(DropiConnection)
        .filter(
            DropiConnection.store_id
            == store.id,
            DropiConnection.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=404,
            detail={
                "code":
                    "DROPPI_NOT_CONNECTED",

                "message":
                    (
                        "Esta tienda no tiene "
                        "Dropi conectado."
                    ),
            },
        )

    db.delete(connection)
    db.commit()

    return {
        "ok": True,
        "connected": False,
        "store_id": store.id,
    }


@app.post("/api/webhooks/dropi/{webhook_token}")
async def dropi_webhook(
    webhook_token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    connection = (
        db.query(DropiConnection)
        .filter(
            DropiConnection.webhook_token
            == webhook_token,
        )
        .first()
    )

    if (
        not connection
        or connection.status
        != "connected"
    ):
        raise HTTPException(
            status_code=404,
            detail="Webhook not found",
        )

    #
    # TODO: mapear eventos de Dropi cuando
    # la API oficial esté documentada.
    #
    # Por ahora solo se confirma recepción;
    # no se asume esquema ni se modifican
    # pedidos. El cuerpo se lee y se ignora.
    #
    await request.body()

    return {
        "ok": True,
    }


# ============================================================
# WHATSAPP
# ============================================================


def _serialize_whatsapp_template(template):
    return {"id": template.id, "provider_template_name": template.provider_template_name, "language_code": template.language_code, "category": template.category, "status": template.status, "components": template.components, "updated_at": template.updated_at.isoformat() + "Z" if template.updated_at else None}


@app.get("/api/stores/{store_id}/whatsapp/templates")
def list_store_whatsapp_templates(store_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    connection = db.query(WhatsAppConnection).filter(WhatsAppConnection.store_id == store_id, WhatsAppConnection.organization_id == membership.organization_id).first()
    if not connection:
        return {"items": []}
    templates = db.query(WhatsAppMessageTemplate).filter(WhatsAppMessageTemplate.organization_id == membership.organization_id, WhatsAppMessageTemplate.whatsapp_connection_id == connection.id).order_by(WhatsAppMessageTemplate.provider_template_name).all()
    return {"items": [_serialize_whatsapp_template(item) for item in templates]}


@app.post("/api/stores/{store_id}/whatsapp/templates/sync")
def sync_store_whatsapp_templates(store_id: int, membership: OrganizationMembership = Depends(require_permission("stores.write")), db: Session = Depends(get_db)):
    connection = db.query(WhatsAppConnection).filter(WhatsAppConnection.store_id == store_id, WhatsAppConnection.organization_id == membership.organization_id, WhatsAppConnection.status == "connected").first()
    if not connection:
        raise HTTPException(400, "WhatsApp connection is not connected")
    try:
        provider_templates = list_whatsapp_templates(connection.business_account_id, decrypt_whatsapp_secret(connection.access_token_encrypted))
    except Exception as exc:
        raise HTTPException(502, "Unable to sync WhatsApp templates") from exc
    for item in provider_templates:
        name, language = item.get("name"), item.get("language")
        if not name or not language:
            continue
        template = db.query(WhatsAppMessageTemplate).filter(WhatsAppMessageTemplate.whatsapp_connection_id == connection.id, WhatsAppMessageTemplate.provider_template_name == name, WhatsAppMessageTemplate.language_code == language).first()
        values = {"provider_template_id": item.get("id"), "category": item.get("category"), "status": str(item.get("status", "pending")).lower(), "components": {"items": item.get("components") or []}}
        if template:
            for key, value in values.items():
                setattr(template, key, value)
        else:
            db.add(WhatsAppMessageTemplate(organization_id=membership.organization_id, whatsapp_connection_id=connection.id, provider_template_name=name, language_code=language, **values))
    db.commit()
    return list_store_whatsapp_templates(store_id, membership, db)


@app.get(
    "/api/stores/{store_id}/whatsapp"
)
def get_whatsapp_connection(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "stores.read"
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

    connection = (
        db.query(WhatsAppConnection)
        .filter(
            WhatsAppConnection.store_id
            == store.id,
            WhatsAppConnection.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not connection:
        return {
            "connected": False,
            "status": "disconnected",
            "phone_number_id": None,
            "business_account_id": None,
            "connected_at": None,
            "last_error": None,
        }

    result = {
        "connected":
            connection.status
            == "connected",
        "status":
            connection.status,
        "phone_number_id":
            connection.phone_number_id,
        "business_account_id":
            connection.business_account_id,
        "verify_token":
            None,
        "connected_at":
            (
                connection.connected_at.isoformat()
                + "Z"
                if connection.connected_at
                else None
            ),
        "last_error":
            connection.last_error,
    }

    if has_permission(
        membership.role,
        "stores.write",
    ):
        result["verify_token"] = (
            connection.verify_token
        )

    return result


@app.post(
    "/api/stores/{store_id}/whatsapp/connect"
)
def connect_whatsapp(
    store_id: int,
    payload: WhatsAppConnectRequest,
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

    if not store.active:
        raise HTTPException(
            status_code=409,
            detail={
                "code":
                    "STORE_NOT_ACTIVE",
                "message":
                    (
                        "La tienda debe estar "
                        "activa para conectar "
                        "WhatsApp."
                    ),
            },
        )

    existing = (
        db.query(WhatsAppConnection)
        .filter(
            WhatsAppConnection.store_id
            == store.id,
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail={
                "code":
                    "WHATSAPP_ALREADY_CONNECTED",
                "message":
                    (
                        "Esta tienda ya tiene "
                        "WhatsApp conectado."
                    ),
            },
        )

    phone_id = (
        payload.phone_number_id
        or ""
    ).strip()

    biz_id = (
        payload.business_account_id
        or ""
    ).strip()

    token = (
        payload.access_token
        or ""
    ).strip()

    if not (phone_id and biz_id and token):
        raise HTTPException(
            status_code=400,
            detail={
                "code":
                    "WHATSAPP_FIELDS_REQUIRED",
                "message":
                    (
                        "phone_number_id, "
                        "business_account_id "
                        "y access_token son "
                        "obligatorios."
                    ),
            },
        )

    conflicting = (
        db.query(WhatsAppConnection)
        .filter(
            WhatsAppConnection.phone_number_id
            == phone_id,
        )
        .first()
    )

    if conflicting:
        raise HTTPException(
            status_code=409,
            detail={
                "code":
                    "WHATSAPP_PHONE_IN_USE",
                "message":
                    (
                        "Este número de teléfono "
                        "ya está conectado."
                    ),
            },
        )

    try:
        encrypted_token = (
            encrypt_whatsapp_secret(
                token
            )
        )

    except (
        RuntimeError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code":
                    "WHATSAPP_ENCRYPTION_FAILED",
                "message":
                    (
                        "No fue posible cifrar "
                        "el token de WhatsApp."
                    ),
            },
        ) from exc

    now = datetime.utcnow()
    verify_token = secrets.token_urlsafe(48)

    connection = WhatsAppConnection(
        organization_id=
            membership.organization_id,
        store_id=
            store.id,
        phone_number_id=
            phone_id,
        business_account_id=
            biz_id,
        access_token_encrypted=
            encrypted_token,
        verify_token=
            verify_token,
        status=
            "connected",
        connected_at=
            now,
        last_error=
            None,
        created_at=
            now,
        updated_at=
            now,
    )

    db.add(connection)

    try:
        db.commit()
        db.refresh(connection)

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail={
                "code":
                    "WHATSAPP_SAVE_FAILED",
                "message":
                    (
                        "No fue posible guardar "
                        "la conexión con WhatsApp."
                    ),
            },
        )

    return {
        "ok": True,
        "connected": True,
        "store_id": store.id,
        "status":
            connection.status,
        "phone_number_id":
            connection.phone_number_id,
        "verify_token":
            connection.verify_token,
    }


@app.delete(
    "/api/stores/{store_id}/whatsapp/disconnect"
)
def disconnect_whatsapp(
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
            Store.deleted.is_(False),
        )
        .first()
    )

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found",
        )

    connection = (
        db.query(WhatsAppConnection)
        .filter(
            WhatsAppConnection.store_id
            == store.id,
            WhatsAppConnection.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=404,
            detail={
                "code":
                    "WHATSAPP_NOT_CONNECTED",
                "message":
                    (
                        "Esta tienda no tiene "
                        "WhatsApp conectado."
                    ),
            },
        )

    db.delete(connection)
    db.commit()

    return {
        "ok": True,
        "connected": False,
        "store_id": store.id,
    }


def _verify_whatsapp_signature(
    raw_body: bytes,
    signature_header: str | None,
) -> bool:
    app_secret = os.getenv(
        "WHATSAPP_APP_SECRET",
    )

    if not app_secret:
        return False

    if not signature_header:
        return False

    expected_prefix = "sha256="

    if not signature_header.startswith(
        expected_prefix
    ):
        return False

    expected_hex = signature_header[
        len(expected_prefix):
    ]

    computed = hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(
        computed,
        expected_hex,
    )


@app.get("/api/webhooks/whatsapp")
def whatsapp_verify_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    mode = request.query_params.get(
        "hub.mode"
    )
    token = request.query_params.get(
        "hub.verify_token"
    )
    challenge = request.query_params.get(
        "hub.challenge"
    )

    if (
        mode != "subscribe"
        or not token
        or not challenge
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid verification request",
        )

    connection = (
        db.query(WhatsAppConnection)
        .filter(
            WhatsAppConnection.verify_token
            == token,
            WhatsAppConnection.status
            == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=403,
            detail="Invalid verify token",
        )

    return PlainTextResponse(
        content=challenge
    )


@app.post("/api/webhooks/whatsapp")
async def whatsapp_receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    raw_body = await request.body()

    signature = (
        request.headers.get(
            "X-Hub-Signature-256"
        )
    )

    if not _verify_whatsapp_signature(
        raw_body,
        signature,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid signature",
        )

    try:
        payload = json.loads(raw_body)
    except (
        json.JSONDecodeError,
        ValueError,
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON",
        )

    entries = (
        payload.get("entry")
        or []
    )

    inbound_conversation_ids = []
    new_conversations = []  # track (conversation, connection)
    new_messages = []  # track (message, conversation, connection)

    for entry in entries:
        changes = (
            entry.get("changes")
            or []
        )

        for change in changes:
            if (
                change.get("field")
                != "messages"
            ):
                continue

            value = (
                change.get("value")
                or {}
            )

            phone_number_id = (
                value.get(
                    "metadata", {}
                ).get(
                    "phone_number_id"
                )
                or ""
            )

            if not phone_number_id:
                continue

            connection = (
                db.query(
                    WhatsAppConnection,
                )
                .filter(
                    WhatsAppConnection.phone_number_id
                    == phone_number_id,
                    WhatsAppConnection.status
                    == "connected",
                )
                .first()
            )

            if not connection:
                continue

            messages = (
                value.get("messages")
                or []
            )

            statuses = (
                value.get("statuses")
                or []
            )

            contacts = (
                value.get("contacts")
                or []
            )

            contact_map = {
                c.get("wa_id"): c
                for c in contacts
                if c.get("wa_id")
            }

            for msg in messages:
                wa_id = (
                    msg.get("from")
                    or ""
                )

                msg_id = (
                    msg.get("id")
                    or ""
                )

                msg_type = (
                    msg.get("type")
                    or ""
                )

                if (
                    not wa_id
                    or not msg_id
                ):
                    continue

                if (
                    msg_type != "text"
                ):
                    continue

                text_body = (
                    msg.get("text", {})
                    .get("body")
                    or ""
                )

                if not text_body:
                    continue

                customer = (
                    db.query(Customer)
                    .filter(
                        Customer.organization_id
                        == connection.organization_id,
                        Customer.phone
                        == wa_id,
                    )
                    .first()
                )

                if not customer:
                    contact = (
                        contact_map.get(
                            wa_id
                        )
                        or {}
                    )

                    profile = (
                        contact.get(
                            "profile"
                        )
                        or {}
                    )

                    name = (
                        profile.get("name")
                        or wa_id
                    )

                    customer = Customer(
                        organization_id=
                            connection.organization_id,
                        name=
                            name,
                        phone=
                            wa_id,
                    )

                    db.add(customer)
                    db.flush()

                conversation = (
                    db.query(Conversation)
                    .filter(
                        Conversation.organization_id
                        == connection.organization_id,
                        Conversation.store_id
                        == connection.store_id,
                        Conversation.customer_id
                        == customer.id,
                        Conversation.channel
                        == "WhatsApp",
                    )
                    .first()
                )

                if not conversation:
                    conversation = Conversation(
                        organization_id=
                            connection.organization_id,
                        store_id=
                            connection.store_id,
                        customer_id=
                            customer.id,
                        channel=
                            "WhatsApp",
                        preview=
                            text_body,
                        unread=
                            1,
                        mode=
                            "ai",
                        created_at=
                            datetime.utcnow(),
                        updated_at=
                            datetime.utcnow(),
                    )

                    db.add(conversation)
                    db.flush()

                    # Track new conversation for event emission
                    new_conversations.append((conversation, connection))

                existing_msg = (
                    db.query(Message)
                    .filter(
                        Message.conversation_id
                        == conversation.id,
                        Message.provider
                        == "whatsapp",
                        Message.external_message_id
                        == msg_id,
                    )
                    .first()
                )

                if not existing_msg:
                    message = Message(
                        conversation_id=
                            conversation.id,
                        sender=
                            "customer",
                        text=
                            text_body,
                        provider=
                            "whatsapp",
                        external_message_id=
                            msg_id,
                        delivery_status=
                            "delivered",
                        created_at=
                            datetime.utcnow(),
                    )

                    db.add(message)

                    # Track new message for event emission
                    new_messages.append((message, conversation, connection))

                    conversation.preview = (
                        text_body
                    )

                    conversation.unread += 1

                    conversation.updated_at = (
                        datetime.utcnow()
                    )

                    if (
                        conversation.id
                        not in inbound_conversation_ids
                    ):
                        inbound_conversation_ids.append(
                            conversation.id
                        )

            for status_event in statuses:
                ext_msg_id = (
                    status_event.get("id")
                    or ""
                )

                new_status = (
                    status_event.get("status")
                    or ""
                )

                if (
                    not ext_msg_id
                    or not new_status
                ):
                    continue

                valid_statuses = {
                    "sent",
                    "delivered",
                    "read",
                    "failed",
                }

                if (
                    new_status
                    not in valid_statuses
                ):
                    continue

                existing = (
                    db.query(Message)
                    .filter(
                        Message.provider
                        == "whatsapp",
                        Message.external_message_id
                        == ext_msg_id,
                    )
                    .first()
                )

                if existing:
                    existing.delivery_status = (
                        new_status
                    )

                    conversation = (
                        db.query(Conversation)
                        .filter(
                            Conversation.id
                            == existing.conversation_id,
                        )
                        .first()
                    )

                    if conversation:
                        conversation.updated_at = (
                            datetime.utcnow()
                        )

    db.commit()

    # Emit conversation.created events
    for conversation, connection in new_conversations:
        safe_emit_event(
            db=db,
            organization_id=conversation.organization_id,
            store_id=conversation.store_id,
            event_type="conversation.created",
            payload={
                "conversation": {
                    "id": conversation.id,
                    "store_id": conversation.store_id,
                    "organization_id": conversation.organization_id,
                    "channel": conversation.channel,
                    "mode": conversation.mode,
                }
            },
            event_id=f"conversation:{conversation.id}:created",
        )

    # Emit message.received events
    for message, conversation, connection in new_messages:
        safe_emit_event(
            db=db,
            organization_id=conversation.organization_id,
            store_id=conversation.store_id,
            event_type="message.received",
            payload={
                "message": {
                    "id": message.id,
                    "conversation_id": conversation.id,
                    "sender": message.sender,
                    "channel": "whatsapp",
                    "text": message.text,
                },
                "conversation": {
                    "id": conversation.id,
                    "store_id": conversation.store_id,
                    "organization_id": conversation.organization_id,
                },
            },
            event_id=f"whatsapp-message:{message.external_message_id}",
        )

    for cid in inbound_conversation_ids:
        conv = (
            db.query(Conversation)
            .filter(Conversation.id == cid)
            .first()
        )

        if not conv:
            continue

        if conv.mode != "ai":
            continue

        last_msg = (
            db.query(Message)
            .filter(
                Message.conversation_id == cid,
            )
            .order_by(Message.id.desc())
            .first()
        )

        if not last_msg:
            continue

        if _detect_handoff(last_msg.text):
            conv.mode = "human"
            conv.updated_at = datetime.utcnow()
            db.commit()
            continue

        background_tasks.add_task(
            generate_auto_reply,
            conversation_id=cid,
        )

    return {"ok": True}


@app.post(
    "/api/conversations/{conversation_id}"
    "/whatsapp/send"
)
def send_whatsapp_message(
    conversation_id: int,
    payload: MessageCreate,
    membership: OrganizationMembership = Depends(
        require_permission(
            "conversations.write"
        )
    ),
    db: Session = Depends(get_db),
):
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id
            == conversation_id,
            Conversation.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    connection = (
        db.query(WhatsAppConnection)
        .filter(
            WhatsAppConnection.store_id
            == conversation.store_id,
            WhatsAppConnection.organization_id
            == membership.organization_id,
            WhatsAppConnection.status
            == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=409,
            detail={
                "code":
                    "WHATSAPP_NOT_CONNECTED",
                "message":
                    (
                        "WhatsApp no está "
                        "conectado para esta "
                        "tienda."
                    ),
            },
        )

    customer = (
        db.query(Customer)
        .filter(
            Customer.id
            == conversation.customer_id,
        )
        .first()
    )

    if not customer:
        raise HTTPException(
            status_code=404,
            detail="Customer not found",
        )

    text = (
        payload.text
        or ""
    ).strip()

    if not text:
        raise HTTPException(
            status_code=400,
            detail="Message text is required",
        )

    try:
        token = (
            decrypt_whatsapp_secret(
                connection.access_token_encrypted
            )
        )

        result = (
            send_whatsapp_text_message(
                phone_number_id=
                    connection.phone_number_id,
                access_token=
                    token,
                to=
                    customer.phone,
                text=
                    text,
            )
        )

    except RuntimeError as exc:
        connection.last_error = (
            str(exc)
        )

        db.commit()

        raise HTTPException(
            status_code=502,
            detail={
                "code":
                    "WHATSAPP_SEND_FAILED",
                "message":
                    (
                        "No fue posible enviar "
                        "el mensaje por WhatsApp."
                    ),
            },
        ) from exc

    external_id = (
        result.get("message_id")
    )

    message = Message(
        conversation_id=
            conversation.id,
        sender=
            "human",
        text=
            text,
        provider=
            "whatsapp",
        external_message_id=
            external_id,
        delivery_status=
            "sent",
        created_at=
            datetime.utcnow(),
    )

    db.add(message)

    conversation.preview = text
    conversation.updated_at = (
        datetime.utcnow()
    )

    db.commit()

    return {
        "ok": True,
        "message_id":
            message.id,
    }


@app.post("/api/stores/{store_id}/shopify/connect")
def start_shopify_connection(
    store_id: int,
    payload: ShopifyConnectRequest,
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

    if not store.active:
        raise HTTPException(
            status_code=409,
            detail=(
                "La tienda debe estar activa "
                "para conectar Shopify."
            ),
        )

    existing_connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.store_id
            == store.id,
        )
        .first()
    )

    if existing_connection:
        raise HTTPException(
            status_code=409,
            detail={
                "code":
                    "COMMERCE_ALREADY_CONNECTED",

                "message":
                    (
                        "Esta tienda ya tiene una "
                        "integración de comercio."
                    ),

                "provider":
                    existing_connection.provider,
            },
        )

    try:
        shop_domain = (
            normalize_shop_domain(
                payload.shop_domain
            )
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code":
                    "INVALID_SHOPIFY_DOMAIN",

                "message":
                    "Dominio Shopify inválido.",
            },
        ) from exc

    conflicting_connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.provider
            == "shopify",
            CommerceConnection.external_store_url
            == shop_domain,
        )
        .first()
    )

    if conflicting_connection:
        raise HTTPException(
            status_code=409,
            detail={
                "code":
                    "SHOPIFY_STORE_ALREADY_CONNECTED",

                "message":
                    (
                        "Esta tienda Shopify ya "
                        "está conectada a DIAGLOB."
                    ),
            },
        )

    state = generate_oauth_state()

    now = datetime.utcnow()

    oauth_state = ShopifyOAuthState(
        state=state,

        organization_id=
            membership.organization_id,

        store_id=
            store.id,

        user_id=
            membership.user_id,

        shop_domain=
            shop_domain,

        expires_at=
            now + timedelta(
                minutes=10
            ),

        used=False,

        created_at=now,
    )

    db.add(oauth_state)

    # Limpiamos estados antiguos del mismo
    # usuario/tienda para evitar acumulación.
    (
        db.query(ShopifyOAuthState)
        .filter(
            ShopifyOAuthState.store_id
            == store.id,

            ShopifyOAuthState.user_id
            == membership.user_id,

            ShopifyOAuthState.state
            != state,

            ShopifyOAuthState.used
            .is_(False),
        )
        .update(
            {
                ShopifyOAuthState.used:
                    True,
            },
            synchronize_session=False,
        )
    )

    try:
        authorization_url = (
            build_authorization_url(
                shop_domain,
                state,
            )
        )

    except RuntimeError as exc:
        db.rollback()

        raise HTTPException(
            status_code=503,
            detail={
                "code":
                    "SHOPIFY_NOT_CONFIGURED",

                "message":
                    str(exc),
            },
        ) from exc

    db.commit()

    return {
        "ok": True,
        "provider": "shopify",
        "store_id": store.id,
        "shop_domain": shop_domain,
        "expires_in_seconds": 600,
        "authorization_url":
            authorization_url,
    }


def _shopify_connect_frontend_url(
    connected: bool,
) -> str:
    base_url = os.getenv(
        "FRONTEND_URL",
        "https://diaglob.tech",
    ).strip().rstrip("/")

    status = (
        "connected"
        if connected
        else "already-connected"
    )

    return (
        f"{base_url}"
        f"?shopify={status}"
    )


@app.get("/api/shopify/callback")
def shopify_oauth_callback(
    request: Request,
    db: Session = Depends(get_db),
):
    query_params = dict(
        request.query_params
    )

    if not verify_shopify_hmac(
        query_params
    ):
        raise HTTPException(
            status_code=403,
            detail="Invalid Shopify HMAC",
        )

    code = query_params.get(
        "code",
        "",
    )

    state = query_params.get(
        "state",
        "",
    )

    shop = query_params.get(
        "shop",
        "",
    )

    if not (code and state and shop):
        raise HTTPException(
            status_code=400,
            detail=(
                "Missing required Shopify "
                "OAuth parameters"
            ),
        )

    oauth_state = (
        db.query(ShopifyOAuthState)
        .filter(
            ShopifyOAuthState.state
            == state,
            ShopifyOAuthState.used
            .is_(False),
        )
        .first()
    )

    if not oauth_state:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid or already used "
                "OAuth state"
            ),
        )

    if (
        oauth_state.expires_at
        < datetime.utcnow()
    ):
        raise HTTPException(
            status_code=400,
            detail="OAuth state expired",
        )

    try:
        normalized_shop = (
            normalize_shop_domain(
                shop
            )
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid shop domain",
        ) from exc

    if (
        oauth_state.shop_domain
        != normalized_shop
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "OAuth state does not match "
                "the shop domain"
            ),
        )

    try:
        access_token = (
            exchange_access_token(
                normalized_shop,
                code,
            )
        )

    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    encrypted_token = (
        encrypt_shopify_secret(
            access_token
        )
    )

    existing_connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.store_id
            == oauth_state.store_id,
        )
        .first()
    )

    if existing_connection:
        (
            db.query(ShopifyOAuthState)
            .filter(
                ShopifyOAuthState.id
                == oauth_state.id,
            )
            .update(
                {
                    ShopifyOAuthState.used:
                        True,
                },
                synchronize_session=False,
            )
        )

        db.commit()

        return RedirectResponse(
            _shopify_connect_frontend_url(
                connected=False
            )
        )

    now = datetime.utcnow()

    connection = CommerceConnection(
        organization_id=
            oauth_state.organization_id,

        store_id=
            oauth_state.store_id,

        provider="shopify",

        external_store_url=
            normalized_shop,

        access_token_encrypted=
            encrypted_token,

        scopes=SHOPIFY_SCOPES,

        status="connected",

        connected_at=now,
    )

    db.add(connection)

    (
        db.query(ShopifyOAuthState)
        .filter(
            ShopifyOAuthState.id
            == oauth_state.id,
        )
        .update(
            {
                ShopifyOAuthState.used:
                    True,
            },
            synchronize_session=False,
        )
    )

    db.commit()

    return RedirectResponse(
        _shopify_connect_frontend_url(
            connected=True
        )
    )


@app.delete("/api/stores/{store_id}/shopify/disconnect")
def disconnect_shopify(
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
            Store.deleted.is_(False),
        )
        .first()
    )

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found",
        )

    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.store_id
            == store.id,
            CommerceConnection.organization_id
            == membership.organization_id,
            CommerceConnection.provider
            == "shopify",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=404,
            detail={
                "code":
                    "SHOPIFY_NOT_CONNECTED",

                "message":
                    (
                        "Esta tienda no tiene "
                        "Shopify conectado."
                    ),
            },
        )

    db.delete(connection)
    db.commit()

    return {
        "ok": True,
        "connected": False,
        "store_id": store.id,
    }


@app.post(
    "/api/stores/{store_id}"
    "/shopify/test"
)
def shopify_test_connection(
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
            Store.deleted.is_(False),
        )
        .first()
    )

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found",
        )

    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.store_id
            == store.id,
            CommerceConnection.organization_id
            == membership.organization_id,
            CommerceConnection.provider
            == "shopify",
            CommerceConnection.status
            == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=404,
            detail={
                "code":
                    "SHOPIFY_NOT_CONNECTED",
                "message":
                    (
                        "Shopify no está "
                        "conectado."
                    ),
            },
        )

    try:
        result = (
            test_shopify_connection(
                connection
            )
        )

    except ShopifyAuthError as exc:
        connection.status = "error"
        connection.last_error = str(exc)
        db.commit()

        raise HTTPException(
            status_code=401,
            detail={
                "connected": False,
                "error": str(exc),
            },
        ) from exc

    except (
        ShopifyAPIError,
        ShopifyGraphQLError,
    ) as exc:
        connection.status = "error"
        connection.last_error = str(exc)
        db.commit()

        raise HTTPException(
            status_code=502,
            detail={
                "connected": False,
                "error": str(exc),
            },
        ) from exc

    connection.status = "connected"
    connection.last_error = None
    db.commit()

    return result


@app.post(
    "/api/stores/{store_id}"
    "/shopify/sync/products"
)
def shopify_sync_products(
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
            Store.deleted.is_(False),
        )
        .first()
    )

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found",
        )

    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.store_id
            == store.id,
            CommerceConnection.organization_id
            == membership.organization_id,
            CommerceConnection.provider
            == "shopify",
            CommerceConnection.status
            == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=404,
            detail={
                "code":
                    "SHOPIFY_NOT_CONNECTED",
                "message":
                    (
                        "Shopify no está "
                        "conectado."
                    ),
            },
        )

    try:
        result = sync_shopify_products(
            db, connection
        )

    except ShopifyAuthError as exc:
        connection.status = "error"
        connection.last_error = str(exc)
        db.commit()

        raise HTTPException(
            status_code=401,
            detail={
                "ok": False,
                "error": str(exc),
            },
        ) from exc

    except (
        ShopifyAPIError,
        ShopifyGraphQLError,
    ) as exc:
        connection.last_error = str(exc)
        db.commit()

        raise HTTPException(
            status_code=502,
            detail={
                "ok": False,
                "error": str(exc),
            },
        ) from exc

    return result


class ShopifyOrderItemRequest(BaseModel):
    variant_local_id: int
    quantity: int


class ShopifyOrderCreateRequest(BaseModel):
    items: list[ShopifyOrderItemRequest]
    customer_email: str | None = None
    customer_name: str | None = None
    note: str | None = None
    idempotency_key: str | None = None


@app.post(
    "/api/stores/{store_id}"
    "/shopify/orders"
)
def create_shopify_order(
    store_id: int,
    payload: ShopifyOrderCreateRequest,
    membership: OrganizationMembership = Depends(
        require_permission(
            "commerce.write"
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

    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.store_id
            == store.id,
            CommerceConnection.organization_id
            == membership.organization_id,
            CommerceConnection.provider
            == "shopify",
            CommerceConnection.status
            == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=404,
            detail={
                "code":
                    "SHOPIFY_NOT_CONNECTED",
                "message":
                    (
                        "Shopify no está "
                        "conectado."
                    ),
            },
        )

    if not payload.items:
        raise HTTPException(
            status_code=400,
            detail=(
                "At least one item is required"
            ),
        )

    for item in payload.items:
        if item.quantity <= 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Quantity must be > 0 for "
                    f"variant "
                    f"{item.variant_local_id}"
                ),
            )

    try:
        result = create_shopify_draft_order(
            db=db,
            store=store,
            connection=connection,
            items_payload=[
                {
                    "variant_local_id":
                        item.variant_local_id,
                    "quantity": item.quantity,
                }
                for item in payload.items
            ],
            customer_email=(
                payload.customer_email
            ),
            customer_name=(
                payload.customer_name
            ),
            note=payload.note,
            idempotency_key=(
                payload.idempotency_key
            ),
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except ShopifyAuthError as exc:
        connection.status = "error"
        connection.last_error = str(exc)
        db.commit()

        raise HTTPException(
            status_code=401,
            detail={
                "ok": False,
                "error": str(exc),
            },
        ) from exc

    except ShopifyUserError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "ok": False,
                "error": str(exc),
            },
        ) from exc

    except (
        ShopifyAPIError,
        ShopifyGraphQLError,
    ) as exc:
        connection.last_error = str(exc)
        db.commit()

        raise HTTPException(
            status_code=502,
            detail={
                "ok": False,
                "error": str(exc),
            },
        ) from exc

    return result


@app.get(
    "/api/stores/{store_id}"
    "/shopify/orders"
)
def list_orders(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "commerce.read"
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

    orders = list_shopify_orders(
        db=db,
        store_id=store.id,
        organization_id=store.organization_id,
    )

    return {
        "items": orders,
        "total": len(orders),
    }


@app.get(
    "/api/stores/{store_id}"
    "/shopify/orders/{order_id}"
)
def get_order(
    store_id: int,
    order_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "commerce.read"
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

    order = get_shopify_order(
        db=db,
        order_id=order_id,
        store_id=store.id,
        organization_id=store.organization_id,
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found",
        )

    return order


@app.post("/api/stores")
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

    # Necesitamos el ID antes de crear
    # la relación membership <-> store.
    db.flush()

    # Los owners con all_stores=True ya ven
    # automáticamente todas las tiendas.
    #
    # Un manager con all_stores=False debe
    # recibir explícitamente la tienda que creó.
    if not membership.all_stores:
        membership.stores.append(store)

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


@app.patch("/api/stores/{store_id}")
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


@app.delete("/api/stores/{store_id}")
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


# ============================================================
# GOOGLE SHEETS INTEGRATION
# ============================================================

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]

# Requested only from the incremental authorization flow. Google classifies
# drive.readonly as restricted because Diaglob lists and downloads user files.
GOOGLE_DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"


def _get_google_client_id() -> str:
    val = os.getenv("GOOGLE_CLIENT_ID", "")
    if not val:
        raise RuntimeError(
            "GOOGLE_CLIENT_ID is not configured"
        )
    return val


def _get_google_client_secret() -> str:
    val = os.getenv("GOOGLE_CLIENT_SECRET", "")
    if not val:
        raise RuntimeError(
            "GOOGLE_CLIENT_SECRET is not configured"
        )
    return val


def _get_google_redirect_uri() -> str:
    return os.getenv(
        "GOOGLE_REDIRECT_URI",
        "https://api.diaglob.tech"
        "/api/integrations/google/oauth/callback",
    )


def _google_connect_frontend_url(
    status: str,
) -> str:
    base_url = os.getenv(
        "FRONTEND_URL",
        "https://diaglob.tech",
    ).strip().rstrip("/")
    return f"{base_url}?google={status}"


# --- Google OAuth: State model ---

class GoogleOAuthStartResponse(BaseModel):
    authorization_url: str


class GoogleSheetSourceRequest(BaseModel):
    spreadsheet_id: str
    spreadsheet_name: str = ""
    sheet_name: str | None = None
    import_mode: Literal["sheet", "workbook"] = "sheet"


class GoogleSyncResponse(BaseModel):
    source_id: int
    sync_status: str
    ingestion_job_id: str | None = None
    message: str = ""


def _google_source_import_mode(source: KnowledgeSource) -> str:
    """Treat sources created before workbook support as single-sheet imports."""
    try:
        metadata = json.loads(source.metadata_json or "{}")
    except json.JSONDecodeError:
        return "sheet"
    return metadata.get("import_mode", "sheet")


async def _fetch_google_workbook_content(
    access_token: str,
    spreadsheet_id: str,
    spreadsheet_title: str,
) -> tuple[str, str]:
    metadata = await get_spreadsheet_metadata(
        access_token, spreadsheet_id
    )
    spreadsheet_title = metadata.get("title", spreadsheet_title)
    sections = []
    for tab in metadata.get("sheets", []):
        if tab.get("hidden", False):
            continue
        tab_name = tab.get("title", "")
        values = await fetch_sheet_values(
            access_token, spreadsheet_id, tab_name
        )
        csv_content = normalize_to_csv(
            values, spreadsheet_title, tab_name
        )
        if csv_content.strip():
            sections.append(f"## Sheet: {tab_name}\n{csv_content.strip()}")

    if not sections:
        raise ValueError("Workbook has no non-empty visible sheets")

    return spreadsheet_title, (
        f"# Spreadsheet: {spreadsheet_title}\n\n"
        + "\n\n".join(sections)
        + "\n"
    )


# --- Google Status ---

@app.get("/api/integrations/google/status")
def get_google_status(
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.read")
    ),
    db: Session = Depends(get_db),
):
    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id
            == membership.organization_id,
            GoogleConnection.status
            != "revoked",
        )
        .first()
    )

    if not connection:
        return {
            "connected": False,
            "email": None,
            "status": None,
        }

    return {
        "connected": connection.status == "connected",
        "email": connection.email,
        "status": connection.status,
        "connected_at": (
            connection.connected_at.isoformat()
            if connection.connected_at
            else None
        ),
    }


# --- Google OAuth: Start ---

@app.get(
    "/api/integrations/google/oauth/start"
)
def start_google_oauth(
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    try:
        client_id = _get_google_client_id()
        redirect_uri = _get_google_redirect_uri()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "GOOGLE_NOT_CONFIGURED",
                "message": str(exc),
            },
        ) from exc

    # Clean up old unused states for this org
    (
        db.query(GoogleOAuthState)
        .filter(
            GoogleOAuthState.organization_id
            == membership.organization_id,
            GoogleOAuthState.used.is_(False),
        )
        .update({"used": True})
    )

    state_token = secrets.token_urlsafe(32)
    scopes_str = " ".join(GOOGLE_SCOPES)

    oauth_state = GoogleOAuthState(
        state_token=state_token,
        organization_id=membership.organization_id,
        user_id=membership.user_id,
        scopes=scopes_str,
        expires_at=datetime.utcnow()
        + timedelta(minutes=10),
        used=False,
    )
    db.add(oauth_state)
    db.commit()

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scopes_str,
        "state": state_token,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }

    query_string = "&".join(
        f"{k}={v}" for k, v in params.items()
    )
    auth_url = (
        f"{GOOGLE_AUTH_URL}?{query_string}"
    )

    return {
        "authorization_url": auth_url,
    }


# --- Google OAuth: Callback ---

@app.get(
    "/api/integrations/google/oauth/callback"
)
def google_oauth_callback(
    request: Request,
    db: Session = Depends(get_db),
):
    params = dict(request.query_params)

    code = params.get("code", "")
    state_token = params.get("state", "")
    error = params.get("error", "")

    if error:
        frontend_url = (
            _google_connect_frontend_url("error")
        )
        return RedirectResponse(
            url=frontend_url, status_code=302
        )

    if not code or not state_token:
        raise HTTPException(
            status_code=400,
            detail="Missing code or state",
        )

    oauth_state = (
        db.query(GoogleOAuthState)
        .filter(
            GoogleOAuthState.state_token
            == state_token,
            GoogleOAuthState.used.is_(False),
        )
        .first()
    )

    if not oauth_state:
        raise HTTPException(
            status_code=400,
            detail="Invalid or used OAuth state",
        )

    if (
        oauth_state.expires_at
        < datetime.utcnow()
    ):
        raise HTTPException(
            status_code=400,
            detail="OAuth state expired",
        )

    # Consume the state before the external exchange so a failed exchange
    # cannot make the state reusable through a transaction rollback.
    oauth_state.used = True
    db.commit()

    # Exchange code for tokens
    try:
        client_id = _get_google_client_id()
        client_secret = _get_google_client_secret()
        redirect_uri = _get_google_redirect_uri()

        token_response = httpx.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=30,
        )
        token_response.raise_for_status()
        token_data = token_response.json()

    except Exception as exc:
        frontend_url = (
            _google_connect_frontend_url("error")
        )
        return RedirectResponse(
            url=frontend_url, status_code=302
        )

    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")
    expires_in = token_data.get("expires_in", 3600)
    granted_scopes = token_data.get("scope", "")

    if not access_token:
        frontend_url = (
            _google_connect_frontend_url("error")
        )
        return RedirectResponse(
            url=frontend_url, status_code=302
        )

    # Get user email (best effort, not critical)
    user_email = None
    try:
        user_info_resp = httpx.get(
            "https://www.googleapis.com/"
            "oauth2/v3/userinfo",
            headers={
                "Authorization": (
                    f"Bearer {access_token}"
                ),
            },
            timeout=10,
        )
        if user_info_resp.status_code == 200:
            user_info = user_info_resp.json()
            user_email = user_info.get("email")
    except Exception:
        pass

    # Encrypt tokens
    encrypted_access = encrypt_google_secret(
        access_token
    )
    encrypted_refresh = (
        encrypt_google_secret(refresh_token)
        if refresh_token
        else None
    )

    # Upsert GoogleConnection
    existing = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id
            == oauth_state.organization_id,
        )
        .first()
    )

    token_expiry = (
        datetime.utcnow()
        + timedelta(seconds=expires_in)
    )

    if existing:
        existing.access_token_encrypted = (
            encrypted_access
        )
        # Only overwrite refresh token if Google
        # returned a new one
        if refresh_token:
            existing.refresh_token_encrypted = (
                encrypted_refresh
            )
        existing.token_expiry = token_expiry
        existing.scopes = " ".join(sorted(
            set((existing.scopes or "").split())
            | set(granted_scopes.split())
        ))
        existing.email = (
            user_email or existing.email
        )
        existing.status = "connected"
        existing.connected_at = datetime.utcnow()
        existing.revoked_at = None
        existing.updated_at = datetime.utcnow()
    else:
        connection = GoogleConnection(
            organization_id=(
                oauth_state.organization_id
            ),
            user_id=oauth_state.user_id,
            email=user_email,
            access_token_encrypted=encrypted_access,
            refresh_token_encrypted=encrypted_refresh,
            token_expiry=token_expiry,
            scopes=granted_scopes,
            status="connected",
            connected_at=datetime.utcnow(),
        )
        db.add(connection)

    db.commit()

    frontend_url = (
        _google_connect_frontend_url("connected")
    )
    return RedirectResponse(
        url=frontend_url, status_code=302
    )


# --- Google Disconnect ---

@app.delete("/api/integrations/google")
def disconnect_google(
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id
            == membership.organization_id,
            GoogleConnection.status
            != "revoked",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=404,
            detail="No Google connection found",
        )

    # Try to revoke at Google (best effort)
    try:
        access_token = decrypt_google_secret(
            connection.access_token_encrypted
        )
        httpx.post(
            GOOGLE_REVOKE_URL,
            params={"token": access_token},
            timeout=10,
        )
    except Exception:
        pass

    connection.status = "revoked"
    connection.revoked_at = datetime.utcnow()
    connection.updated_at = datetime.utcnow()
    db.commit()

    return {"ok": True, "status": "revoked"}


# --- Google: Refresh token helper ---

def _refresh_google_token(
    connection: GoogleConnection,
    db: Session,
) -> bool:
    """Attempt to refresh an expired Google token.

    Returns True if refresh succeeded.
    Updates connection in-place.
    """
    if not connection.refresh_token_encrypted:
        return False

    try:
        refresh_token = decrypt_google_secret(
            connection.refresh_token_encrypted
        )
        client_id = _get_google_client_id()
        client_secret = _get_google_client_secret()

        resp = httpx.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        new_access = data.get("access_token", "")
        expires_in = data.get("expires_in", 3600)
        new_refresh = data.get("refresh_token")

        if not new_access:
            return False

        connection.access_token_encrypted = (
            encrypt_google_secret(new_access)
        )
        connection.token_expiry = (
            datetime.utcnow()
            + timedelta(seconds=expires_in)
        )
        # Only overwrite if Google returned a new
        # refresh token
        if new_refresh:
            connection.refresh_token_encrypted = (
                encrypt_google_secret(new_refresh)
            )
        connection.status = "connected"
        connection.updated_at = datetime.utcnow()
        db.commit()
        return True

    except Exception:
        connection.status = "token_expired"
        connection.updated_at = datetime.utcnow()
        db.commit()
        return False


def _get_valid_google_token(
    connection: GoogleConnection,
    db: Session,
) -> str | None:
    """Get a valid access token, refreshing if needed.

    Returns decrypted access token or None.
    """
    if not connection.access_token_encrypted:
        return None

    # Check if token is still valid (with 5min buffer)
    if (
        connection.token_expiry
        and connection.token_expiry
        > datetime.utcnow()
        + timedelta(minutes=5)
    ):
        return decrypt_google_secret(
            connection.access_token_encrypted
        )

    # Try refresh
    refreshed = _refresh_google_token(
        connection, db
    )
    if refreshed:
        return decrypt_google_secret(
            connection.access_token_encrypted
        )

    return None


# --- Google: List Sheets ---

@app.get("/api/integrations/google/sheets")
async def list_google_sheets(
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.read")
    ),
    db: Session = Depends(get_db),
):
    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id
            == membership.organization_id,
            GoogleConnection.status
            == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=404,
            detail="Google not connected",
        )

    access_token = _get_valid_google_token(
        connection, db
    )
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "GOOGLE_TOKEN_EXPIRED",
                "message": (
                    "Google connection expired. "
                    "Please reconnect."
                ),
            },
        )

    try:
        async with httpx.AsyncClient(
            timeout=30
        ) as client:
            resp = await client.get(
                "https://www.googleapis.com/"
                "drive/v3/files",
                headers={
                    "Authorization": (
                        f"Bearer {access_token}"
                    ),
                },
                params={
                    "q": (
                        "mimeType="
                        "'application/"
                        "vnd.google-apps.spreadsheet'"
                    ),
                    "fields": (
                        "files(id,name,"
                        "modifiedTime)"
                    ),
                    "pageSize": "100",
                    "orderBy": "modifiedTime desc",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        sheets = [
            {
                "spreadsheet_id": f["id"],
                "name": f.get("name", "Untitled"),
                "modified_time": f.get(
                    "modifiedTime"
                ),
            }
            for f in data.get("files", [])
        ]

        return {"sheets": sheets}

    except httpx.HTTPStatusError as exc:
        code, msg = map_google_api_error(
            exc.response.status_code
        )
        if code == "reconnect_required":
            connection.status = "token_expired"
            db.commit()
        raise HTTPException(
            status_code=exc.response.status_code,
            detail={"code": code, "message": msg},
        ) from exc


# --- Google: List Tabs ---

@app.get(
    "/api/integrations/google/sheets/"
    "{spreadsheet_id}/tabs"
)
async def list_google_sheet_tabs(
    spreadsheet_id: str,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.read")
    ),
    db: Session = Depends(get_db),
):
    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id
            == membership.organization_id,
            GoogleConnection.status
            == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=404,
            detail="Google not connected",
        )

    access_token = _get_valid_google_token(
        connection, db
    )
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "GOOGLE_TOKEN_EXPIRED",
                "message": (
                    "Google connection expired. "
                    "Please reconnect."
                ),
            },
        )

    try:
        metadata = await get_spreadsheet_metadata(
            access_token, spreadsheet_id
        )
        return {
            "title": metadata["title"],
            "tabs": metadata["sheets"],
        }

    except httpx.HTTPStatusError as exc:
        code, msg = map_google_api_error(
            exc.response.status_code
        )
        if code == "reconnect_required":
            connection.status = "token_expired"
            db.commit()
        raise HTTPException(
            status_code=exc.response.status_code,
            detail={"code": code, "message": msg},
        ) from exc


# --- Google: Add Sheet Source to KB ---

@app.post(
    "/api/knowledge-bases/"
    "{knowledge_base_id}/sources/google-sheet"
)
async def add_google_sheet_source(
    knowledge_base_id: int,
    payload: GoogleSheetSourceRequest,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    org_id = membership.organization_id

    kb = _require_knowledge_base_ready(
        db, org_id, knowledge_base_id
    )

    # Validate spreadsheet ID
    sheet_id = extract_spreadsheet_id(
        payload.spreadsheet_id
    )
    if not sheet_id:
        raise HTTPException(
            status_code=400,
            detail="Invalid spreadsheet ID or URL",
        )
    if payload.import_mode == "sheet" and not payload.sheet_name:
        raise HTTPException(
            status_code=400,
            detail="Sheet name is required for sheet imports",
        )
    source_sheet_name = (
        payload.sheet_name if payload.import_mode == "sheet" else None
    )

    # Check for duplicate source in same KB
    candidates = (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.knowledge_base_id
            == knowledge_base_id,
            KnowledgeSource.external_id == sheet_id,
            KnowledgeSource.source_type == "google_sheet",
            KnowledgeSource.active.is_(True),
        )
        .all()
    )
    existing = next(
        (
            source for source in candidates
            if _google_source_import_mode(source) == payload.import_mode
            and source.sheet_name == source_sheet_name
        ),
        None,
    )

    if existing:
        return {
            "source_id": existing.id,
            "sync_status": existing.sync_status
            or "synced",
            "message": "Source already exists",
        }

    # Get Google connection
    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id
            == org_id,
            GoogleConnection.status
            == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=400,
            detail="Google not connected",
        )

    access_token = _get_valid_google_token(
        connection, db
    )
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "GOOGLE_TOKEN_EXPIRED",
                "message": (
                    "Google connection expired. "
                    "Please reconnect."
                ),
            },
        )

    spreadsheet_title = (
        payload.spreadsheet_name or sheet_id
    )
    try:
        if payload.import_mode == "workbook":
            spreadsheet_title, csv_content = (
                await _fetch_google_workbook_content(
                    access_token, sheet_id, spreadsheet_title
                )
            )
        else:
            try:
                metadata = await get_spreadsheet_metadata(
                    access_token, sheet_id
                )
                spreadsheet_title = metadata.get(
                    "title", spreadsheet_title
                )
            except Exception:
                pass
            values = await fetch_sheet_values(
                access_token, sheet_id, source_sheet_name
            )
            csv_content = normalize_to_csv(
                values, spreadsheet_title, source_sheet_name
            )
    except httpx.HTTPStatusError as exc:
        code, msg = map_google_api_error(
            exc.response.status_code
        )
        raise HTTPException(
            status_code=exc.response.status_code,
            detail={"code": code, "message": msg},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    if not csv_content.strip():
        raise HTTPException(
            status_code=400,
            detail=(
                "Workbook has no non-empty visible sheets"
                if payload.import_mode == "workbook"
                else "Sheet is empty"
            ),
        )

    # Upload to S3
    filename = (
        f"{sheet_id}_{source_sheet_name or 'workbook'}.csv"
    )
    try:
        s3_result = upload_knowledge_file(
            organization_id=org_id,
            knowledge_base_id=knowledge_base_id,
            filename=filename,
            content=csv_content.encode("utf-8"),
            content_type="text/csv",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"S3 upload failed: {exc}",
        ) from exc

    # Create KnowledgeSource
    source = KnowledgeSource(
        organization_id=org_id,
        knowledge_base_id=knowledge_base_id,
        name=(
            spreadsheet_title
            if payload.import_mode == "workbook"
            else f"{spreadsheet_title} — {source_sheet_name}"
        ),
        source_type="google_sheet",
        content_type="text/csv",
        s3_bucket=s3_result["bucket"],
        s3_key=s3_result["key"],
        size_bytes=len(csv_content.encode("utf-8")),
        status="uploaded",
        external_id=sheet_id,
        external_name=spreadsheet_title,
        sheet_name=source_sheet_name,
        sync_status="uploaded",
        metadata_json=json.dumps({"import_mode": payload.import_mode}),
    )
    db.add(source)
    db.flush()

    # Start Bedrock ingestion
    ingestion_job_id = None
    sync_status = "uploaded"

    ingestion_job_id = start_ingestion_job(
        kb.external_id,
        kb.external_data_source_id,
    )
    if ingestion_job_id:
        sync_status = "indexing"
        source.ingestion_job_id = (
            ingestion_job_id
        )
        source.sync_status = "indexing"
    else:
        sync_status = "uploaded"
        source.sync_status = "uploaded"

    db.commit()
    db.refresh(source)

    return {
        "source_id": source.id,
        "sync_status": sync_status,
        "ingestion_job_id": ingestion_job_id,
        "name": source.name,
    }


# --- Google: Sync Sheet Source ---

@app.post(
    "/api/knowledge-bases/"
    "{knowledge_base_id}/sources/"
    "{source_id}/sync"
)
async def sync_google_sheet_source(
    knowledge_base_id: int,
    source_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    org_id = membership.organization_id

    kb = _require_knowledge_base_ready(
        db, org_id, knowledge_base_id
    )

    source = (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.id == source_id,
            KnowledgeSource.knowledge_base_id
            == knowledge_base_id,
            KnowledgeSource.organization_id
            == org_id,
            KnowledgeSource.source_type
            == "google_sheet",
        )
        .first()
    )

    if not source:
        raise HTTPException(
            status_code=404,
            detail="Google Sheet source not found",
        )

    # Idempotency: don't re-sync if already syncing
    if source.sync_status in ("syncing", "indexing"):
        return {
            "source_id": source.id,
            "sync_status": source.sync_status,
            "ingestion_job_id": (
                source.ingestion_job_id
            ),
            "message": "Sync already in progress",
        }

    # Get Google connection
    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id
            == org_id,
            GoogleConnection.status
            == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "GOOGLE_DISCONNECTED",
                "message": (
                    "Google not connected. "
                    "Please reconnect."
                ),
            },
        )

    access_token = _get_valid_google_token(
        connection, db
    )
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "GOOGLE_TOKEN_EXPIRED",
                "message": (
                    "Google connection expired. "
                    "Please reconnect."
                ),
            },
        )

    # Mark as syncing
    source.sync_status = "syncing"
    source.sync_error = None
    db.flush()

    import_mode = _google_source_import_mode(source)

    # Fetch the selected tab or every visible workbook tab.
    try:
        if import_mode == "workbook":
            spreadsheet_title, csv_content = (
                await _fetch_google_workbook_content(
                    access_token,
                    source.external_id,
                    source.external_name or source.external_id,
                )
            )
            source.external_name = spreadsheet_title
        else:
            values = await fetch_sheet_values(
                access_token,
                source.external_id,
                source.sheet_name,
            )
            csv_content = normalize_to_csv(
                values,
                source.external_name or "",
                source.sheet_name or "",
            )
    except httpx.HTTPStatusError as exc:
        code, msg = map_google_api_error(
            exc.response.status_code
        )
        source.sync_status = "failed"
        source.sync_error = msg
        db.commit()
        raise HTTPException(
            status_code=exc.response.status_code,
            detail={"code": code, "message": msg},
        ) from exc
    except ValueError as exc:
        source.sync_status = "failed"
        source.sync_error = str(exc)
        db.commit()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    if not csv_content.strip():
        source.sync_status = "failed"
        source.sync_error = (
            "Workbook has no non-empty visible sheets"
            if import_mode == "workbook" else "Sheet is empty"
        )
        db.commit()
        raise HTTPException(
            status_code=400,
            detail=source.sync_error,
        )

    # Upload to S3
    filename = (
        f"{source.external_id}"
        f"_{source.sheet_name or 'workbook'}.csv"
    )
    try:
        s3_result = upload_knowledge_file(
            organization_id=org_id,
            knowledge_base_id=knowledge_base_id,
            filename=filename,
            content=csv_content.encode("utf-8"),
            content_type="text/csv",
        )
    except Exception as exc:
        source.sync_status = "failed"
        source.sync_error = f"S3 upload failed: {exc}"
        db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"S3 upload failed: {exc}",
        ) from exc

    # Update source
    source.s3_bucket = s3_result["bucket"]
    source.s3_key = s3_result["key"]
    source.size_bytes = len(
        csv_content.encode("utf-8")
    )
    source.status = "uploaded"
    source.last_synced_at = datetime.utcnow()

    # Start Bedrock ingestion
    ingestion_job_id = None
    sync_status = "uploaded"

    ingestion_job_id = start_ingestion_job(
        kb.external_id,
        kb.external_data_source_id,
    )
    if ingestion_job_id:
        sync_status = "indexing"
        source.ingestion_job_id = (
            ingestion_job_id
        )
        source.sync_status = "indexing"
    else:
        sync_status = "uploaded"
        source.sync_status = "uploaded"

    db.commit()
    db.refresh(source)

    return {
        "source_id": source.id,
        "sync_status": sync_status,
        "ingestion_job_id": ingestion_job_id,
    }


# --- Google: Check ingestion status ---

@app.get(
    "/api/knowledge-bases/"
    "{knowledge_base_id}/sources/"
    "{source_id}/ingestion-status"
)
def check_ingestion_status(
    knowledge_base_id: int,
    source_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.read")
    ),
    db: Session = Depends(get_db),
):
    org_id = membership.organization_id

    kb = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.id
            == knowledge_base_id,
            KnowledgeBase.organization_id
            == org_id,
        )
        .first()
    )

    if not kb:
        raise HTTPException(
            status_code=404,
            detail="Knowledge Base not found",
        )

    source = (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.id == source_id,
            KnowledgeSource.knowledge_base_id
            == knowledge_base_id,
            KnowledgeSource.organization_id
            == org_id,
        )
        .first()
    )

    if not source:
        raise HTTPException(
            status_code=404,
            detail="Source not found",
        )

    # If not in indexing state, return current status
    if source.sync_status != "indexing":
        return {
            "source_id": source.id,
            "sync_status": source.sync_status,
            "last_synced_at": (
                source.last_synced_at.isoformat()
                if source.last_synced_at
                else None
            ),
            "sync_error": source.sync_error,
        }

    # Guard: do not call Bedrock if KB is not ready. This prevents
    # mutating DB state from a GET when provisioning has not completed
    # or has failed.  (R2 readiness gate — tech-debt note: this GET
    # has side effects; the read+persist pattern is kept for
    # compatibility in this phase.)
    if kb.external_status != "ready":
        return {
            "source_id": source.id,
            "sync_status": source.sync_status,
            "last_synced_at": (
                source.last_synced_at.isoformat()
                if source.last_synced_at
                else None
            ),
            "sync_error": source.sync_error,
        }

    # Check Bedrock ingestion status
    if (
        not source.ingestion_job_id
        or not kb.external_id
        or not kb.external_data_source_id
    ):
        return {
            "source_id": source.id,
            "sync_status": source.sync_status,
            "last_synced_at": (
                source.last_synced_at.isoformat()
                if source.last_synced_at
                else None
            ),
        }

    new_status = get_ingestion_status(
        kb.external_id,
        kb.external_data_source_id,
        source.ingestion_job_id,
    )

    if new_status != source.sync_status:
        source.sync_status = new_status
        if new_status == STATUS_SYNCED:
            source.last_synced_at = (
                datetime.utcnow()
            )
        elif new_status == STATUS_FAILED:
            source.sync_error = (
                "Bedrock ingestion failed"
            )
        db.commit()

    return {
        "source_id": source.id,
        "sync_status": source.sync_status,
        "last_synced_at": (
            source.last_synced_at.isoformat()
            if source.last_synced_at
            else None
        ),
        "sync_error": source.sync_error,
    }


# ============================================================
# GOOGLE DRIVE / DOCS INTEGRATION — PHASE 2
# ============================================================


# --- Pydantic models ---


class GoogleDriveFileRequest(BaseModel):
    file_id: str
    file_name: str
    mime_type: str


class GoogleDriveFolderRequest(BaseModel):
    folder_id: str
    folder_name: str


DRIVE_SOURCE_TYPES = (
    "google_doc",
    "google_drive_file",
    "google_drive_folder",
)


def _find_active_drive_source(
    db: Session,
    organization_id: int,
    knowledge_base_id: int,
    external_id: str,
) -> KnowledgeSource | None:
    return (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.organization_id
            == organization_id,
            KnowledgeSource.knowledge_base_id
            == knowledge_base_id,
            KnowledgeSource.external_id == external_id,
            KnowledgeSource.source_type.in_(
                DRIVE_SOURCE_TYPES
            ),
            KnowledgeSource.active.is_(True),
        )
        .first()
    )


def _standalone_drive_duplicate_response(
    existing: KnowledgeSource,
) -> dict:
    if (
        existing.parent_source_id is not None
        or existing.source_type == "google_drive_folder"
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DRIVE_SOURCE_CONFLICT",
                "message": (
                    "Drive object already exists in this "
                    "knowledge base with a conflicting "
                    "folder relationship."
                ),
                "source_id": existing.id,
            },
        )
    return {
        "source_id": existing.id,
        "name": existing.name,
        "sync_status": existing.sync_status or "synced",
        "message": "Source already exists",
    }


def _drive_conflict_reason(
    existing: KnowledgeSource,
) -> str:
    if existing.source_type == "google_drive_folder":
        return "Drive object already exists as a folder source"
    if existing.parent_source_id is not None:
        return "File already belongs to another folder source"
    return "File already exists as a standalone Drive source"


def _delete_artifact_best_effort(
    bucket: str | None,
    key: str | None,
    context: str,
) -> str | None:
    if not bucket or not key:
        return None
    try:
        delete_knowledge_file(bucket, key)
    except Exception as exc:
        warning = f"{context}: {exc}"
        logger.warning("%s", warning, exc_info=True)
        return warning
    return None


def _persist_new_drive_source(
    db: Session,
    source: KnowledgeSource,
    uploaded: dict,
) -> None:
    """Persist a new source or remove its just-uploaded artifact."""
    try:
        db.add(source)
        db.commit()
        db.refresh(source)
    except Exception:
        db.rollback()
        _delete_artifact_best_effort(
            uploaded.get("bucket"),
            uploaded.get("key"),
            "Failed to clean artifact after DB persistence failure",
        )
        raise


async def _download_drive_child(
    access_token: str,
    file_id: str,
    mime_type: str,
) -> tuple[bytes, str, str]:
    if is_google_doc(mime_type):
        return (
            await export_google_doc(
                access_token,
                file_id,
                "text/plain",
            ),
            "text/plain",
            "google_doc",
        )
    return (
        await download_drive_file(access_token, file_id),
        mime_type,
        "google_drive_file",
    )


def _folder_file_record(file_meta: dict) -> dict:
    return {
        "id": file_meta["id"],
        "name": file_meta.get("name", ""),
        "modifiedTime": file_meta.get(
            "modifiedTime", ""
        ),
        "size": file_meta.get("size", "0"),
    }


def _folder_summary() -> dict:
    return {
        "new": 0,
        "modified": 0,
        "removed": 0,
        "unchanged": 0,
        "failed": [],
        "ignored": [],
        "successful_delta": False,
    }


def _folder_sync_error(
    summary: dict,
    warnings: list[dict],
    ingestion_error: str | None = None,
) -> str | None:
    errors = [
        (
            f"{item['action']} {item.get('name') or item['id']}: "
            f"{item['error']}"
        )
        for item in summary["failed"]
    ]
    errors.extend(
        f"{item['action']} {item.get('name') or item['id']}: "
        f"{item['warning']}"
        for item in warnings
    )
    if ingestion_error:
        errors.append(ingestion_error)
    return "; ".join(errors) or None


def _finish_folder_operation(
    db: Session,
    source: KnowledgeSource,
    kb: KnowledgeBase,
    remote_files: list[dict],
    summary: dict,
    warnings: list[dict],
) -> tuple[str, str | None]:
    summary["successful_delta"] = bool(
        summary["new"]
        + summary["modified"]
        + summary["removed"]
    )

    if summary["failed"] and not summary["successful_delta"]:
        sync_status = "failed"
    elif summary["failed"]:
        sync_status = "partial_failed"
    elif summary["successful_delta"]:
        sync_status = "uploaded"
    else:
        sync_status = "synced"

    source.sync_status = sync_status
    source.sync_error = _folder_sync_error(summary, warnings)
    source.ingestion_job_id = None
    source.sync_generation = (source.sync_generation or 0) + 1
    source.last_synced_at = datetime.utcnow()
    source.metadata_json = json.dumps({
        "file_count": len(remote_files),
        "new": summary["new"],
        "modified": summary["modified"],
        "removed": summary["removed"],
        "unchanged": summary["unchanged"],
        "last_synced_files": [
            _folder_file_record(file_meta)
            for file_meta in remote_files
        ],
        "summary": summary,
        "warnings": warnings,
    })
    db.commit()

    ingestion_job_id = None
    ingestion_error = None
    if (
        summary["successful_delta"]
        and kb.external_id
        and kb.external_data_source_id
    ):
        try:
            ingestion_job_id = start_ingestion_job(
                kb.external_id,
                kb.external_data_source_id,
            )
            if not ingestion_job_id:
                ingestion_error = (
                    "Bedrock ingestion failed to start"
                )
        except Exception as exc:
            ingestion_error = (
                f"Bedrock ingestion failed to start: {exc}"
            )
            logger.exception(
                "Failed to start folder ingestion for source %s",
                source.id,
            )

        if ingestion_job_id:
            source.ingestion_job_id = ingestion_job_id
            if not summary["failed"]:
                sync_status = "indexing"
        else:
            ingestion_job_id = None
            if not summary["failed"]:
                sync_status = "uploaded"

        source.sync_status = sync_status
        source.sync_error = _folder_sync_error(
            summary,
            warnings,
            ingestion_error,
        )
        db.commit()

    return sync_status, ingestion_job_id


def _start_drive_source_ingestion(
    db: Session,
    source: KnowledgeSource,
    kb: KnowledgeBase,
    prior_warning: str | None = None,
) -> tuple[str, str | None]:
    sync_status = "uploaded"
    ingestion_job_id = None
    ingestion_error = None

    if kb.external_id and kb.external_data_source_id:
        try:
            ingestion_job_id = start_ingestion_job(
                kb.external_id,
                kb.external_data_source_id,
            )
            if ingestion_job_id:
                sync_status = "indexing"
            else:
                ingestion_error = (
                    "Bedrock ingestion failed to start"
                )
        except Exception as exc:
            ingestion_error = (
                f"Bedrock ingestion failed to start: {exc}"
            )
            logger.exception(
                "Failed to start Drive ingestion for source %s",
                source.id,
            )

    source.sync_status = sync_status
    source.ingestion_job_id = ingestion_job_id
    source.sync_error = "; ".join(
        message
        for message in (prior_warning, ingestion_error)
        if message
    ) or None
    db.commit()
    return sync_status, ingestion_job_id


def _mark_drive_source_failed(
    db: Session,
    source: KnowledgeSource,
    error: str,
) -> None:
    source.sync_status = "failed"
    source.sync_error = error
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to persist Drive source failure for %s",
            source.id,
        )


# --- Scope helpers ---


def _connection_has_drive_scope(
    connection: GoogleConnection,
) -> bool:
    """Check if connection has drive.readonly scope."""
    if not connection.scopes:
        return False
    return "drive.readonly" in connection.scopes


def _require_drive_scope(
    connection: GoogleConnection,
) -> None:
    """Raise 403 if connection lacks drive scope."""
    if not _connection_has_drive_scope(connection):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "INSUFFICIENT_SCOPES",
                "message": (
                    "Additional Google permissions "
                    "required for Drive access."
                ),
                "required_scope": "drive.readonly",
            },
        )


def _parse_google_modified_at(
    value: str | None,
) -> datetime | None:
    """Convert Drive's RFC 3339 value to a UTC-naive DB timestamp."""
    if not value:
        return None

    try:
        timestamp = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
        if timestamp.tzinfo:
            timestamp = timestamp.astimezone(
                timezone.utc
            ).replace(tzinfo=None)
        return timestamp
    except ValueError:
        return None


def _is_remote_file_modified(
    source: KnowledgeSource,
    remote_modified_at: str | None,
) -> bool:
    """Compare normalized timestamps without lexical/RFC3339 ambiguity."""
    remote = _parse_google_modified_at(
        remote_modified_at
    )
    if not remote:
        return False

    local = source.external_modified_at
    if not local:
        return True
    if local.tzinfo:
        local = local.astimezone(timezone.utc).replace(
            tzinfo=None
        )
    return remote > local


def _derive_freshness(
    source: KnowledgeSource,
    connection: GoogleConnection | None,
) -> str:
    """Derive freshness status for a knowledge source.

    Returns one of:
    - fresh
    - changed
    - syncing
    - failed
    - disconnected
    - static
    """
    source_type = source.source_type or ""

    if (
        source_type.startswith("google_")
        and (
            not connection
            or connection.status != "connected"
        )
    ):
        return "disconnected"

    if source.sync_status == "failed":
        return "failed"

    if source.sync_status in ("syncing", "indexing"):
        return "syncing"

    if source_type.startswith("google_"):
        if (
            source.external_modified_at
            and source.last_synced_at
            and source.external_modified_at
            > source.last_synced_at
        ):
            return "changed"
        if source.sync_status == "synced":
            return "fresh"

    return "static"


# --- Scope check endpoint ---


@app.get(
    "/api/integrations/google/drive/scopes"
)
def check_google_drive_scopes(
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.read")
    ),
    db: Session = Depends(get_db),
):
    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id
            == membership.organization_id,
            GoogleConnection.status
            != "revoked",
        )
        .first()
    )

    if not connection:
        return {
            "connected": False,
            "has_drive_scope": False,
            "scopes": [],
        }

    has_drive = _connection_has_drive_scope(
        connection
    )

    return {
        "connected": True,
        "has_drive_scope": has_drive,
        "scopes": (
            connection.scopes.split()
            if connection.scopes
            else []
        ),
    }


# --- Expand scopes (re-authorize with drive.readonly) ---


@app.get(
    "/api/integrations/google/oauth/expand-scopes"
)
def expand_google_scopes(
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    client_id = _get_google_client_id()
    redirect_uri = _get_google_redirect_uri()

    # Clean old states for this org
    (
        db.query(GoogleOAuthState)
        .filter(
            GoogleOAuthState.organization_id
            == membership.organization_id,
            GoogleOAuthState.used.is_(False),
        )
        .update({"used": True})
    )
    db.flush()

    state_token = secrets.token_urlsafe(32)
    scopes_str = " ".join(GOOGLE_DRIVE_SCOPES)

    oauth_state = GoogleOAuthState(
        state_token=state_token,
        organization_id=membership.organization_id,
        user_id=membership.user_id,
        scopes=scopes_str,
        expires_at=datetime.utcnow()
        + timedelta(minutes=10),
        used=False,
    )
    db.add(oauth_state)
    db.commit()

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scopes_str,
        "state": state_token,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }

    query_string = "&".join(
        f"{k}={v}" for k, v in params.items()
    )
    auth_url = (
        f"{GOOGLE_AUTH_URL}?{query_string}"
    )

    return {
        "authorization_url": auth_url,
    }


# --- Drive: list files (file picker) ---


@app.get(
    "/api/integrations/google/drive/files"
)
async def list_drive_files_endpoint(
    query: str = "",
    page_token: str | None = None,
    mime_type: str | None = None,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.read")
    ),
    db: Session = Depends(get_db),
):
    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id
            == membership.organization_id,
            GoogleConnection.status
            == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=404,
            detail="Google not connected",
        )

    _require_drive_scope(connection)

    access_token = _get_valid_google_token(
        connection, db
    )
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "GOOGLE_TOKEN_EXPIRED",
                "message": (
                    "Google connection expired. "
                    "Please reconnect."
                ),
            },
        )

    try:
        result = await list_drive_files(
            access_token,
            search=query,
            page_token=page_token,
            mime_types={mime_type} if mime_type else None,
        )

        files = []
        for f in result.get("files", []):
            files.append({
                "id": f["id"],
                "name": f.get("name", "Untitled"),
                "mime_type": f.get("mimeType", ""),
                "modified_time": f.get(
                    "modifiedTime"
                ),
                "size": f.get("size"),
                "parents": f.get("parents", []),
            })

        return {
            "files": files,
            "next_page_token": result.get(
                "nextPageToken"
            ),
        }

    except httpx.HTTPStatusError as exc:
        code, msg = map_google_api_error(
            exc.response.status_code
        )
        if code == "reconnect_required":
            connection.status = "token_expired"
            db.commit()
        raise HTTPException(
            status_code=exc.response.status_code,
            detail={"code": code, "message": msg},
        ) from exc


# --- Drive: list folders (folder picker) ---


@app.get(
    "/api/integrations/google/drive/folders"
)
async def list_drive_folders_endpoint(
    query: str = "",
    page_token: str | None = None,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.read")
    ),
    db: Session = Depends(get_db),
):
    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id
            == membership.organization_id,
            GoogleConnection.status
            == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=404,
            detail="Google not connected",
        )

    _require_drive_scope(connection)

    access_token = _get_valid_google_token(
        connection, db
    )
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "GOOGLE_TOKEN_EXPIRED",
                "message": (
                    "Google connection expired. "
                    "Please reconnect."
                ),
            },
        )

    try:
        result = await list_drive_folders(
            access_token,
            search=query,
            page_token=page_token,
        )

        folders = []
        for f in result.get("folders", []):
            folders.append({
                "id": f["id"],
                "name": f.get("name", "Untitled"),
                "modified_time": f.get(
                    "modifiedTime"
                ),
            })

        return {
            "folders": folders,
            "next_page_token": result.get(
                "nextPageToken"
            ),
        }

    except httpx.HTTPStatusError as exc:
        code, msg = map_google_api_error(
            exc.response.status_code
        )
        if code == "reconnect_required":
            connection.status = "token_expired"
            db.commit()
        raise HTTPException(
            status_code=exc.response.status_code,
            detail={"code": code, "message": msg},
        ) from exc


# --- Add Google Doc source ---


@app.post(
    "/api/knowledge-bases/"
    "{knowledge_base_id}/sources/google-doc"
)
async def add_google_doc_source(
    knowledge_base_id: int,
    request: GoogleDriveFileRequest,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    org_id = membership.organization_id

    kb = _require_knowledge_base_ready(
        db, org_id, knowledge_base_id
    )

    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id
            == org_id,
            GoogleConnection.status
            == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "GOOGLE_DISCONNECTED",
                "message": (
                    "Google not connected. "
                    "Please connect Google first."
                ),
            },
        )

    _require_drive_scope(connection)

    existing = _find_active_drive_source(
        db,
        org_id,
        knowledge_base_id,
        request.file_id,
    )

    if existing:
        return _standalone_drive_duplicate_response(
            existing
        )

    access_token = _get_valid_google_token(
        connection, db
    )
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "GOOGLE_TOKEN_EXPIRED",
                "message": (
                    "Google connection expired."
                ),
            },
        )

    # Export Google Doc to text/plain
    try:
        content = await export_google_doc(
            access_token,
            request.file_id,
            "text/plain",
        )
    except httpx.HTTPStatusError as exc:
        code, msg = map_google_api_error(
            exc.response.status_code
        )
        raise HTTPException(
            status_code=exc.response.status_code,
            detail={"code": code, "message": msg},
        ) from exc
    except (GoogleDriveFileTooLarge, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "FILE_TOO_LARGE",
                "message": str(exc),
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "GOOGLE_DOWNLOAD_FAILED",
                "message": str(exc),
            },
        ) from exc

    if not content:
        raise HTTPException(
            status_code=400,
            detail="Document is empty",
        )

    # Upload to S3
    filename = f"{request.file_name}.txt"
    try:
        s3_result = upload_knowledge_file(
            organization_id=org_id,
            knowledge_base_id=knowledge_base_id,
            filename=filename,
            content=content,
            content_type="text/plain",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"S3 upload failed: {exc}",
        ) from exc

    # Get remote modified time
    remote_meta = None
    try:
        remote_meta = await get_file_metadata(
            access_token, request.file_id
        )
    except Exception:
        pass

    modified_at = _parse_google_modified_at(
        remote_meta.get("modifiedTime")
        if remote_meta
        else None
    )

    source = KnowledgeSource(
        knowledge_base_id=knowledge_base_id,
        organization_id=org_id,
        name=request.file_name,
        source_type="google_doc",
        s3_bucket=s3_result["bucket"],
        s3_key=s3_result["key"],
        size_bytes=len(content),
        status="uploaded",
        external_id=request.file_id,
        external_name=request.file_name,
        external_mime_type=(
            "application/vnd.google-apps.document"
        ),
        external_modified_at=modified_at,
        last_synced_at=datetime.utcnow(),
        sync_status="uploaded",
    )
    try:
        _persist_new_drive_source(
            db, source, s3_result
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "SOURCE_PERSISTENCE_FAILED",
                "message": str(exc),
            },
        ) from exc

    sync_status, ingestion_job_id = (
        _start_drive_source_ingestion(
            db, source, kb
        )
    )

    return {
        "source_id": source.id,
        "name": source.name,
        "sync_status": sync_status,
        "ingestion_job_id": ingestion_job_id,
    }


# --- Add Drive file source (PDF, DOCX, etc.) ---


@app.post(
    "/api/knowledge-bases/"
    "{knowledge_base_id}/sources/"
    "google-drive-file"
)
async def add_google_drive_file_source(
    knowledge_base_id: int,
    request: GoogleDriveFileRequest,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    org_id = membership.organization_id

    kb = _require_knowledge_base_ready(
        db, org_id, knowledge_base_id
    )

    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id
            == org_id,
            GoogleConnection.status
            == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "GOOGLE_DISCONNECTED",
                "message": (
                    "Google not connected."
                ),
            },
        )

    _require_drive_scope(connection)

    if not is_supported_mime_type(
        request.mime_type
    ):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "UNSUPPORTED_FILE_TYPE",
                "message": (
                    f"File type "
                    f"'{request.mime_type}' "
                    f"is not supported."
                ),
            },
        )

    existing = _find_active_drive_source(
        db,
        org_id,
        knowledge_base_id,
        request.file_id,
    )

    if existing:
        return _standalone_drive_duplicate_response(
            existing
        )

    access_token = _get_valid_google_token(
        connection, db
    )
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "GOOGLE_TOKEN_EXPIRED",
                "message": (
                    "Google connection expired."
                ),
            },
        )

    # Download file from Drive
    try:
        content = await download_drive_file(
            access_token, request.file_id
        )
    except (GoogleDriveFileTooLarge, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "FILE_TOO_LARGE",
                "message": str(exc),
            },
        ) from exc
    except httpx.HTTPStatusError as exc:
        code, msg = map_google_api_error(
            exc.response.status_code
        )
        raise HTTPException(
            status_code=exc.response.status_code,
            detail={"code": code, "message": msg},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "GOOGLE_DOWNLOAD_FAILED",
                "message": str(exc),
            },
        ) from exc

    if not content:
        raise HTTPException(
            status_code=400,
            detail="File is empty",
        )

    # Upload to S3
    safe_name = re.sub(
        r"[^A-Za-z0-9._-]+",
        "-",
        request.file_name,
    )
    filename = f"{safe_name}"
    try:
        s3_result = upload_knowledge_file(
            organization_id=org_id,
            knowledge_base_id=knowledge_base_id,
            filename=filename,
            content=content,
            content_type=request.mime_type,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"S3 upload failed: {exc}",
        ) from exc

    # Get remote metadata
    remote_meta = None
    try:
        remote_meta = await get_file_metadata(
            access_token, request.file_id
        )
    except Exception:
        pass

    modified_at = _parse_google_modified_at(
        remote_meta.get("modifiedTime")
        if remote_meta
        else None
    )
    ext_size = None
    if remote_meta:
        if remote_meta.get("size"):
            try:
                ext_size = int(remote_meta["size"])
            except (TypeError, ValueError):
                pass

    source = KnowledgeSource(
        knowledge_base_id=knowledge_base_id,
        organization_id=org_id,
        name=request.file_name,
        source_type="google_drive_file",
        content_type=request.mime_type,
        s3_bucket=s3_result["bucket"],
        s3_key=s3_result["key"],
        size_bytes=len(content),
        status="uploaded",
        external_id=request.file_id,
        external_name=request.file_name,
        external_mime_type=request.mime_type,
        external_modified_at=modified_at,
        external_size=ext_size,
        last_synced_at=datetime.utcnow(),
        sync_status="uploaded",
    )
    try:
        _persist_new_drive_source(
            db, source, s3_result
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "SOURCE_PERSISTENCE_FAILED",
                "message": str(exc),
            },
        ) from exc

    sync_status, ingestion_job_id = (
        _start_drive_source_ingestion(
            db, source, kb
        )
    )

    return {
        "source_id": source.id,
        "name": source.name,
        "sync_status": sync_status,
        "ingestion_job_id": ingestion_job_id,
    }


# --- Add Drive folder source ---


@app.post(
    "/api/knowledge-bases/"
    "{knowledge_base_id}/sources/"
    "google-drive-folder"
)
async def add_google_drive_folder_source(
    knowledge_base_id: int,
    request: GoogleDriveFolderRequest,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    org_id = membership.organization_id

    kb = _require_knowledge_base_ready(
        db, org_id, knowledge_base_id
    )

    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id
            == org_id,
            GoogleConnection.status
            == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "GOOGLE_DISCONNECTED",
                "message": (
                    "Google not connected."
                ),
            },
        )

    _require_drive_scope(connection)

    existing = _find_active_drive_source(
        db,
        org_id,
        knowledge_base_id,
        request.folder_id,
    )

    if existing:
        if existing.source_type != "google_drive_folder":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "DRIVE_SOURCE_CONFLICT",
                    "message": _drive_conflict_reason(
                        existing
                    ),
                    "source_id": existing.id,
                },
            )
        return {
            "source_id": existing.id,
            "name": existing.name,
            "sync_status": existing.sync_status
            or "synced",
            "message": "Folder source already exists",
        }

    # List folder children to validate
    access_token = _get_valid_google_token(
        connection, db
    )
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "GOOGLE_TOKEN_EXPIRED",
                "message": (
                    "Google connection expired."
                ),
            },
        )

    try:
        result = await list_folder_children(
            access_token, request.folder_id
        )
    except httpx.HTTPStatusError as exc:
        code, msg = map_google_api_error(
            exc.response.status_code
        )
        raise HTTPException(
            status_code=exc.response.status_code,
            detail={"code": code, "message": msg},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "GOOGLE_FOLDER_LIST_FAILED",
                "message": str(exc),
            },
        ) from exc

    files = result.get("files", [])

    if result.get("limit_exceeded"):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "SYNC_LIMIT_EXCEEDED",
                "message": (
                    "Folder exceeds the configured "
                    "maximum file count."
                ),
            },
        )

    # Validate limits
    limit_error = validate_folder_sync_limits(
        files
    )
    if limit_error:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "SYNC_LIMIT_EXCEEDED",
                "message": limit_error,
            },
        )

    summary = _folder_summary()
    warnings = []

    # Persist the metadata-only parent before creating child artifacts.
    source = KnowledgeSource(
        knowledge_base_id=knowledge_base_id,
        organization_id=org_id,
        name=request.folder_name,
        source_type="google_drive_folder",
        s3_bucket="",
        s3_key="",
        status="uploaded",
        external_id=request.folder_id,
        external_name=request.folder_name,
        sync_status="uploaded",
        metadata_json=json.dumps(
            {
                "file_count": len(files),
                "last_synced_files": [
                    _folder_file_record(f)
                    for f in files
                ],
                "summary": summary,
            }
        ),
    )
    try:
        db.add(source)
        db.commit()
        db.refresh(source)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail={
                "code": "SOURCE_PERSISTENCE_FAILED",
                "message": str(exc),
            },
        ) from exc

    downloaded_bytes = 0
    for f in files:
        file_id = f["id"]
        file_name = f.get("name", "Untitled")
        mime_type = f.get("mimeType", "")

        child_existing = _find_active_drive_source(
            db,
            org_id,
            knowledge_base_id,
            file_id,
        )

        if child_existing:
            summary["ignored"].append({
                "id": file_id,
                "name": file_name,
                "reason": _drive_conflict_reason(
                    child_existing
                ),
            })
            continue

        try:
            content, child_mime, child_type = (
                await _download_drive_child(
                    access_token,
                    file_id,
                    mime_type,
                )
            )
        except Exception as exc:
            summary["failed"].append({
                "id": file_id,
                "name": file_name,
                "action": "new",
                "error": str(exc),
            })
            continue

        if not content:
            summary["failed"].append({
                "id": file_id,
                "name": file_name,
                "action": "new",
                "error": "File is empty",
            })
            continue

        downloaded_bytes += len(content)
        if downloaded_bytes > MAX_TOTAL_SYNC_BYTES:
            summary["failed"].append({
                "id": file_id,
                "name": file_name,
                "action": "new",
                "error": (
                    "Actual downloaded content exceeds "
                    f"the {MAX_TOTAL_SYNC_BYTES} byte "
                    "folder sync limit"
                ),
            })
            continue

        safe_name = re.sub(
            r"[^A-Za-z0-9._-]+",
            "-",
            file_name,
        )
        child_filename = f"{safe_name}"

        try:
            s3_result = upload_knowledge_file(
                organization_id=org_id,
                knowledge_base_id=knowledge_base_id,
                filename=child_filename,
                content=content,
                content_type=child_mime,
            )
        except Exception as exc:
            summary["failed"].append({
                "id": file_id,
                "name": file_name,
                "action": "new",
                "error": f"S3 upload failed: {exc}",
            })
            continue

        modified_at = _parse_google_modified_at(
            f.get("modifiedTime")
        )
        ext_size = None
        if f.get("size"):
            try:
                ext_size = int(f["size"])
            except (TypeError, ValueError):
                pass

        child_source = KnowledgeSource(
            knowledge_base_id=knowledge_base_id,
            organization_id=org_id,
            name=file_name,
            source_type=child_type,
            content_type=child_mime,
            s3_bucket=s3_result["bucket"],
            s3_key=s3_result["key"],
            size_bytes=len(content),
            status="uploaded",
            external_id=file_id,
            external_name=file_name,
            external_mime_type=child_mime,
            external_modified_at=modified_at,
            external_size=ext_size,
            parent_source_id=source.id,
            last_synced_at=datetime.utcnow(),
            sync_status="uploaded",
        )
        try:
            _persist_new_drive_source(
                db, child_source, s3_result
            )
        except Exception as exc:
            summary["failed"].append({
                "id": file_id,
                "name": file_name,
                "action": "new",
                "error": (
                    f"DB persistence failed: {exc}"
                ),
            })
            continue
        summary["new"] += 1

    try:
        sync_status, ingestion_job_id = (
            _finish_folder_operation(
                db,
                source,
                kb,
                files,
                summary,
                warnings,
            )
        )
        db.refresh(source)
    except Exception as exc:
        db.rollback()
        persisted_source = (
            db.query(KnowledgeSource)
            .filter(
                KnowledgeSource.id == source.id,
                KnowledgeSource.organization_id == org_id,
                KnowledgeSource.knowledge_base_id
                == knowledge_base_id,
            )
            .first()
        )
        if persisted_source:
            _mark_drive_source_failed(
                db,
                persisted_source,
                f"Folder finalization failed: {exc}",
            )
        raise HTTPException(
            status_code=500,
            detail={
                "code": "FOLDER_FINALIZATION_FAILED",
                "message": str(exc),
            },
        ) from exc

    return {
        "source_id": source.id,
        "name": source.name,
        "sync_status": sync_status,
        "ingestion_job_id": ingestion_job_id,
        "child_count": summary["new"],
        "new_files": summary["new"],
        "modified_files": summary["modified"],
        "removed_files": summary["removed"],
        "summary": summary,
        "warnings": warnings,
    }


# --- Sync Drive folder ---


@app.post(
    "/api/knowledge-bases/"
    "{knowledge_base_id}/sources/"
    "{source_id}/sync-folder"
)
async def sync_drive_folder(
    knowledge_base_id: int,
    source_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    org_id = membership.organization_id

    kb = _require_knowledge_base_ready(
        db, org_id, knowledge_base_id
    )

    source = (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.id == source_id,
            KnowledgeSource.knowledge_base_id
            == knowledge_base_id,
            KnowledgeSource.organization_id
            == org_id,
            KnowledgeSource.source_type
            == "google_drive_folder",
            KnowledgeSource.active.is_(True),
        )
        .first()
    )

    if not source:
        raise HTTPException(
            status_code=404,
            detail="Folder source not found",
        )

    # Idempotency
    if source.sync_status in ("syncing", "indexing"):
        return {
            "source_id": source.id,
            "sync_status": source.sync_status,
            "message": "Sync already in progress",
        }

    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id
            == org_id,
            GoogleConnection.status
            == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "GOOGLE_DISCONNECTED",
                "message": (
                    "Google not connected."
                ),
            },
        )

    _require_drive_scope(connection)

    access_token = _get_valid_google_token(
        connection, db
    )
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "GOOGLE_TOKEN_EXPIRED",
                "message": (
                    "Google connection expired."
                ),
            },
        )

    source.sync_status = "syncing"
    source.sync_error = None
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail={
                "code": "SYNC_STATE_PERSISTENCE_FAILED",
                "message": str(exc),
            },
        ) from exc

    # List current folder children
    try:
        result = await list_folder_children(
            access_token, source.external_id
        )
    except httpx.HTTPStatusError as exc:
        code, msg = map_google_api_error(
            exc.response.status_code
        )
        _mark_drive_source_failed(db, source, msg)
        raise HTTPException(
            status_code=exc.response.status_code,
            detail={"code": code, "message": msg},
        ) from exc
    except Exception as exc:
        error = f"Unable to list Google Drive folder: {exc}"
        _mark_drive_source_failed(db, source, error)
        raise HTTPException(
            status_code=502,
            detail={
                "code": "GOOGLE_FOLDER_LIST_FAILED",
                "message": error,
            },
        ) from exc

    remote_files = result.get("files", [])

    if result.get("limit_exceeded"):
        source.sync_status = "failed"
        source.sync_error = (
            "Folder exceeds the configured "
            "maximum file count"
        )
        db.commit()
        raise HTTPException(
            status_code=400,
            detail={
                "code": "SYNC_LIMIT_EXCEEDED",
                "message": source.sync_error,
            },
        )

    limit_error = validate_folder_sync_limits(
        remote_files
    )
    if limit_error:
        source.sync_status = "failed"
        source.sync_error = limit_error
        db.commit()
        raise HTTPException(
            status_code=400,
            detail={
                "code": "SYNC_LIMIT_EXCEEDED",
                "message": limit_error,
            },
        )

    # Load existing children from DB
    existing_children = (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.parent_source_id
            == source.id,
            KnowledgeSource.organization_id == org_id,
            KnowledgeSource.knowledge_base_id
            == knowledge_base_id,
            KnowledgeSource.source_type.in_(
                DRIVE_SOURCE_TYPES
            ),
            KnowledgeSource.active.is_(True),
        )
        .all()
    )

    remote_by_id = {
        f["id"]: f for f in remote_files
    }
    local_by_ext_id = {
        c.external_id: c
        for c in existing_children
        if c.external_id
    }

    summary = _folder_summary()
    warnings = []
    new_files = []
    modified_files = []
    removed_children = []

    for fid, fmeta in remote_by_id.items():
        if fid not in local_by_ext_id:
            conflict = _find_active_drive_source(
                db,
                org_id,
                knowledge_base_id,
                fid,
            )
            if conflict:
                summary["ignored"].append({
                    "id": fid,
                    "name": fmeta.get("name", "Untitled"),
                    "reason": _drive_conflict_reason(
                        conflict
                    ),
                })
                continue
            new_files.append(fmeta)
        else:
            child = local_by_ext_id[fid]
            if _is_remote_file_modified(
                child,
                fmeta.get("modifiedTime"),
            ):
                modified_files.append(fmeta)
            else:
                summary["unchanged"] += 1

    # Detect removed
    for fid, child in local_by_ext_id.items():
        if fid not in remote_by_id:
            removed_children.append(child)

    downloaded_bytes = 0

    for fmeta in new_files:
        fid = fmeta["id"]
        fname = fmeta.get("name", "Untitled")
        fmime = fmeta.get("mimeType", "")

        try:
            content, child_mime, child_type = (
                await _download_drive_child(
                    access_token,
                    fid,
                    fmime,
                )
            )
        except Exception as exc:
            summary["failed"].append({
                "id": fid,
                "name": fname,
                "action": "new",
                "error": str(exc),
            })
            continue

        if not content:
            summary["failed"].append({
                "id": fid,
                "name": fname,
                "action": "new",
                "error": "File is empty",
            })
            continue

        downloaded_bytes += len(content)
        if downloaded_bytes > MAX_TOTAL_SYNC_BYTES:
            summary["failed"].append({
                "id": fid,
                "name": fname,
                "action": "new",
                "error": (
                    "Actual downloaded content exceeds "
                    f"the {MAX_TOTAL_SYNC_BYTES} byte "
                    "folder sync limit"
                ),
            })
            continue

        safe_name = re.sub(
            r"[^A-Za-z0-9._-]+", "-", fname
        )
        try:
            s3_result = upload_knowledge_file(
                organization_id=org_id,
                knowledge_base_id=knowledge_base_id,
                filename=safe_name,
                content=content,
                content_type=child_mime,
            )
        except Exception as exc:
            summary["failed"].append({
                "id": fid,
                "name": fname,
                "action": "new",
                "error": f"S3 upload failed: {exc}",
            })
            continue

        modified_at = _parse_google_modified_at(
            fmeta.get("modifiedTime")
        )
        ext_size = None
        if fmeta.get("size"):
            try:
                ext_size = int(fmeta["size"])
            except (TypeError, ValueError):
                pass

        child_source = KnowledgeSource(
            knowledge_base_id=knowledge_base_id,
            organization_id=org_id,
            name=fname,
            source_type=child_type,
            content_type=child_mime,
            s3_bucket=s3_result["bucket"],
            s3_key=s3_result["key"],
            size_bytes=len(content),
            status="uploaded",
            external_id=fid,
            external_name=fname,
            external_mime_type=child_mime,
            external_modified_at=modified_at,
            external_size=ext_size,
            parent_source_id=source.id,
            last_synced_at=datetime.utcnow(),
            sync_status="uploaded",
        )
        try:
            _persist_new_drive_source(
                db, child_source, s3_result
            )
        except Exception as exc:
            summary["failed"].append({
                "id": fid,
                "name": fname,
                "action": "new",
                "error": f"DB persistence failed: {exc}",
            })
            continue
        summary["new"] += 1

    for fmeta in modified_files:
        fid = fmeta["id"]
        fname = fmeta.get("name", "Untitled")
        fmime = fmeta.get("mimeType", "")
        child = local_by_ext_id[fid]

        try:
            content, child_mime, child_type = (
                await _download_drive_child(
                    access_token,
                    fid,
                    fmime,
                )
            )
        except Exception as exc:
            summary["failed"].append({
                "id": fid,
                "name": fname,
                "action": "modified",
                "error": str(exc),
            })
            continue

        if not content:
            summary["failed"].append({
                "id": fid,
                "name": fname,
                "action": "modified",
                "error": "File is empty",
            })
            continue

        downloaded_bytes += len(content)
        if downloaded_bytes > MAX_TOTAL_SYNC_BYTES:
            summary["failed"].append({
                "id": fid,
                "name": fname,
                "action": "modified",
                "error": (
                    "Actual downloaded content exceeds "
                    f"the {MAX_TOTAL_SYNC_BYTES} byte "
                    "folder sync limit"
                ),
            })
            continue

        safe_name = re.sub(
            r"[^A-Za-z0-9._-]+", "-", fname
        )
        try:
            s3_result = upload_knowledge_file(
                organization_id=org_id,
                knowledge_base_id=knowledge_base_id,
                filename=safe_name,
                content=content,
                content_type=child_mime,
            )
        except Exception as exc:
            summary["failed"].append({
                "id": fid,
                "name": fname,
                "action": "modified",
                "error": f"S3 upload failed: {exc}",
            })
            continue

        modified_at = _parse_google_modified_at(
            fmeta.get("modifiedTime")
        )
        ext_size = None
        if fmeta.get("size"):
            try:
                ext_size = int(fmeta["size"])
            except (TypeError, ValueError):
                pass

        old_bucket = child.s3_bucket
        old_key = child.s3_key
        child.name = fname
        child.source_type = child_type
        child.content_type = child_mime
        child.s3_bucket = s3_result["bucket"]
        child.s3_key = s3_result["key"]
        child.size_bytes = len(content)
        child.status = "uploaded"
        child.external_name = fname
        child.external_mime_type = fmime
        child.external_modified_at = modified_at
        child.external_size = ext_size
        child.last_synced_at = datetime.utcnow()
        child.sync_status = "uploaded"
        child.sync_error = None
        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            _delete_artifact_best_effort(
                s3_result.get("bucket"),
                s3_result.get("key"),
                "Failed to clean new modified artifact",
            )
            summary["failed"].append({
                "id": fid,
                "name": fname,
                "action": "modified",
                "error": f"DB persistence failed: {exc}",
            })
            continue

        summary["modified"] += 1
        if (
            old_bucket,
            old_key,
        ) != (
            s3_result.get("bucket"),
            s3_result.get("key"),
        ):
            cleanup_warning = _delete_artifact_best_effort(
                old_bucket,
                old_key,
                "Failed to delete replaced artifact",
            )
            if cleanup_warning:
                warnings.append({
                    "id": fid,
                    "name": fname,
                    "action": "modified_cleanup",
                    "warning": cleanup_warning,
                })

    for child in removed_children:
        try:
            if child.s3_bucket and child.s3_key:
                delete_knowledge_file(
                    child.s3_bucket, child.s3_key
                )
        except Exception as exc:
            error = f"S3 delete failed: {exc}"
            child.sync_status = "failed"
            child.sync_error = error
            try:
                db.commit()
            except Exception:
                db.rollback()
                logger.exception(
                    "Failed to persist removal failure for %s",
                    child.id,
                )
            summary["failed"].append({
                "id": child.external_id or str(child.id),
                "name": child.name,
                "action": "removed",
                "error": error,
            })
            continue

        child.active = False
        child.status = "deleted"
        child.sync_status = "synced"
        child.sync_error = None
        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            summary["failed"].append({
                "id": child.external_id or str(child.id),
                "name": child.name,
                "action": "removed",
                "error": f"DB persistence failed: {exc}",
            })
            continue
        summary["removed"] += 1

    try:
        sync_status, ingestion_job_id = (
            _finish_folder_operation(
                db,
                source,
                kb,
                remote_files,
                summary,
                warnings,
            )
        )
        db.refresh(source)
    except Exception as exc:
        db.rollback()
        persisted_source = (
            db.query(KnowledgeSource)
            .filter(
                KnowledgeSource.id == source_id,
                KnowledgeSource.organization_id == org_id,
                KnowledgeSource.knowledge_base_id
                == knowledge_base_id,
                KnowledgeSource.source_type
                == "google_drive_folder",
            )
            .first()
        )
        if persisted_source:
            _mark_drive_source_failed(
                db,
                persisted_source,
                f"Folder finalization failed: {exc}",
            )
        raise HTTPException(
            status_code=500,
            detail={
                "code": "FOLDER_FINALIZATION_FAILED",
                "message": str(exc),
            },
        ) from exc

    return {
        "source_id": source.id,
        "sync_status": sync_status,
        "ingestion_job_id": ingestion_job_id,
        "new_files": summary["new"],
        "modified_files": summary["modified"],
        "removed_files": summary["removed"],
        "summary": summary,
        "warnings": warnings,
    }


# --- Sync single Drive file or Doc ---


@app.post(
    "/api/knowledge-bases/"
    "{knowledge_base_id}/sources/"
    "{source_id}/sync-drive-file"
)
async def sync_drive_file_source(
    knowledge_base_id: int,
    source_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    org_id = membership.organization_id

    kb = _require_knowledge_base_ready(
        db, org_id, knowledge_base_id
    )

    source = (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.id == source_id,
            KnowledgeSource.knowledge_base_id
            == knowledge_base_id,
            KnowledgeSource.organization_id
            == org_id,
            KnowledgeSource.source_type.in_(
                [
                    "google_doc",
                    "google_drive_file",
                ]
            ),
            KnowledgeSource.active.is_(True),
        )
        .first()
    )

    if not source:
        raise HTTPException(
            status_code=404,
            detail="Drive source not found",
        )

    if source.parent_source_id is not None:
        parent = (
            db.query(KnowledgeSource)
            .filter(
                KnowledgeSource.id
                == source.parent_source_id,
                KnowledgeSource.organization_id == org_id,
                KnowledgeSource.knowledge_base_id
                == knowledge_base_id,
                KnowledgeSource.source_type
                == "google_drive_folder",
                KnowledgeSource.active.is_(True),
            )
            .first()
        )
        if not parent:
            raise HTTPException(
                status_code=404,
                detail="Drive source parent not found",
            )

    # Idempotency
    if source.sync_status in ("syncing", "indexing"):
        return {
            "source_id": source.id,
            "sync_status": source.sync_status,
            "message": "Sync already in progress",
        }

    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id
            == org_id,
            GoogleConnection.status
            == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "GOOGLE_DISCONNECTED",
                "message": "Google not connected.",
            },
        )

    _require_drive_scope(connection)

    access_token = _get_valid_google_token(
        connection, db
    )
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "GOOGLE_TOKEN_EXPIRED",
                "message": "Google connection expired.",
            },
        )

    source.sync_status = "syncing"
    source.sync_error = None
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail={
                "code": "SYNC_STATE_PERSISTENCE_FAILED",
                "message": str(exc),
            },
        ) from exc

    # Re-download content
    try:
        if source.source_type == "google_doc":
            content = await export_google_doc(
                access_token,
                source.external_id,
                "text/plain",
            )
            new_mime = "text/plain"
        else:
            content = await download_drive_file(
                access_token, source.external_id
            )
            new_mime = (
                source.external_mime_type
                or source.content_type
                or "application/octet-stream"
            )
    except httpx.HTTPStatusError as exc:
        code, msg = map_google_api_error(
            exc.response.status_code
        )
        _mark_drive_source_failed(db, source, msg)
        raise HTTPException(
            status_code=exc.response.status_code,
            detail={"code": code, "message": msg},
        ) from exc
    except (GoogleDriveFileTooLarge, ValueError) as exc:
        error = str(exc)
        _mark_drive_source_failed(db, source, error)
        raise HTTPException(
            status_code=400,
            detail={
                "code": "FILE_TOO_LARGE",
                "message": error,
            },
        ) from exc
    except Exception as exc:
        error = f"Google Drive download failed: {exc}"
        _mark_drive_source_failed(db, source, error)
        raise HTTPException(
            status_code=502,
            detail={
                "code": "GOOGLE_DOWNLOAD_FAILED",
                "message": error,
            },
        ) from exc

    if not content:
        _mark_drive_source_failed(
            db, source, "File is empty"
        )
        raise HTTPException(
            status_code=400,
            detail="File is empty",
        )

    # Upload and durably repoint before deleting the old artifact.
    old_bucket = source.s3_bucket
    old_key = source.s3_key
    safe_name = re.sub(
        r"[^A-Za-z0-9._-]+",
        "-",
        source.external_name or source.name,
    )
    try:
        s3_result = upload_knowledge_file(
            organization_id=org_id,
            knowledge_base_id=knowledge_base_id,
            filename=safe_name,
            content=content,
            content_type=new_mime,
        )
    except Exception as exc:
        error = f"S3 upload failed: {exc}"
        _mark_drive_source_failed(db, source, error)
        raise HTTPException(
            status_code=500,
            detail=error,
        ) from exc

    # Get remote metadata
    remote_meta = None
    try:
        remote_meta = await get_file_metadata(
            access_token, source.external_id
        )
    except Exception:
        pass

    if remote_meta:
        source.external_modified_at = (
            _parse_google_modified_at(
                remote_meta.get("modifiedTime")
            )
            or source.external_modified_at
        )

    source.s3_bucket = s3_result["bucket"]
    source.s3_key = s3_result["key"]
    source.size_bytes = len(content)
    source.content_type = new_mime
    source.status = "uploaded"
    source.last_synced_at = datetime.utcnow()
    source.sync_status = "uploaded"
    source.sync_error = None
    source.ingestion_job_id = None
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        _delete_artifact_best_effort(
            s3_result.get("bucket"),
            s3_result.get("key"),
            "Failed to clean new Drive sync artifact",
        )
        persisted_source = (
            db.query(KnowledgeSource)
            .filter(
                KnowledgeSource.id == source_id,
                KnowledgeSource.organization_id == org_id,
                KnowledgeSource.knowledge_base_id
                == knowledge_base_id,
            )
            .first()
        )
        if persisted_source:
            _mark_drive_source_failed(
                db,
                persisted_source,
                f"DB persistence failed: {exc}",
            )
        raise HTTPException(
            status_code=500,
            detail={
                "code": "SOURCE_PERSISTENCE_FAILED",
                "message": str(exc),
            },
        ) from exc

    cleanup_warning = None
    if (
        old_bucket,
        old_key,
    ) != (
        s3_result.get("bucket"),
        s3_result.get("key"),
    ):
        cleanup_warning = _delete_artifact_best_effort(
            old_bucket,
            old_key,
            "Failed to delete replaced artifact",
        )

    try:
        sync_status, ingestion_job_id = (
            _start_drive_source_ingestion(
                db,
                source,
                kb,
                cleanup_warning,
            )
        )
        db.refresh(source)
    except Exception as exc:
        db.rollback()
        persisted_source = (
            db.query(KnowledgeSource)
            .filter(
                KnowledgeSource.id == source_id,
                KnowledgeSource.organization_id == org_id,
                KnowledgeSource.knowledge_base_id
                == knowledge_base_id,
            )
            .first()
        )
        if persisted_source:
            persisted_source.sync_status = "uploaded"
            persisted_source.sync_error = (
                "Ingestion state persistence failed: "
                f"{exc}"
            )
            try:
                db.commit()
            except Exception:
                db.rollback()
        raise HTTPException(
            status_code=500,
            detail={
                "code": "INGESTION_STATE_FAILED",
                "message": str(exc),
            },
        ) from exc

    return {
        "source_id": source.id,
        "sync_status": sync_status,
        "ingestion_job_id": ingestion_job_id,
        "sync_error": source.sync_error,
        "warning": cleanup_warning,
    }


# --- Source freshness endpoint ---


@app.get(
    "/api/knowledge-bases/"
    "{knowledge_base_id}/sources/"
    "{source_id}/freshness"
)
def get_source_freshness(
    knowledge_base_id: int,
    source_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.read")
    ),
    db: Session = Depends(get_db),
):
    org_id = membership.organization_id

    source = (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.id == source_id,
            KnowledgeSource.knowledge_base_id
            == knowledge_base_id,
            KnowledgeSource.organization_id
            == org_id,
        )
        .first()
    )

    if not source:
        raise HTTPException(
            status_code=404,
            detail="Source not found",
        )

    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id
            == org_id,
        )
        .first()
    )

    freshness = _derive_freshness(
        source, connection
    )

    return {
        "source_id": source.id,
        "freshness": freshness,
        "last_synced_at": (
            source.last_synced_at.isoformat()
            if source.last_synced_at
            else None
        ),
        "external_modified_at": (
            source.external_modified_at.isoformat()
            if source.external_modified_at
            else None
        ),
        "sync_status": source.sync_status,
        "source_type": source.source_type,
    }
