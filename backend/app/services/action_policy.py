"""Authorization policy for LLM tools and user-driven actions.

The model never decides whether an action is allowed. It requests an action;
this service evaluates the current membership, permission, store scope,
subscription state, risk level and confirmation requirement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from ..models import MembershipStore, OrganizationMembership, Store
from ..permissions import has_permission
from .trial_service import pending_trial_can_bootstrap_store, refresh_trial_state


ActionRisk = Literal["read", "write", "external", "financial", "destructive"]
ConfirmationLevel = Literal["none", "simple", "critical"]


@dataclass(frozen=True)
class ActionPolicy:
    action: str
    permission: str
    risk: ActionRisk
    confirmation: ConfirmationLevel = "none"
    store_required: bool = True
    description: str = ""


@dataclass(frozen=True)
class ActionDecision:
    allowed: bool
    action: str
    permission: str
    risk: ActionRisk
    confirmation: ConfirmationLevel
    code: str | None = None
    message: str | None = None
    store_id: int | None = None

    def as_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "action": self.action,
            "permission": self.permission,
            "risk": self.risk,
            "confirmation": self.confirmation,
            "code": self.code,
            "message": self.message,
            "store_id": self.store_id,
        }


ACTION_POLICIES: dict[str, ActionPolicy] = {
    "chat.use": ActionPolicy(
        "chat.use", "dashboard.read", "read",
        description="Use the Diaglob operations copilot in the selected store.",
    ),
    "orders.list": ActionPolicy(
        "orders.list", "commerce.read", "read",
        description="List store orders.",
    ),
    "orders.get": ActionPolicy(
        "orders.get", "commerce.read", "read",
        description="Inspect a store order.",
    ),
    "products.list": ActionPolicy(
        "products.list", "commerce.read", "read",
        description="List and search store products.",
    ),
    "customers.search": ActionPolicy(
        "customers.search", "customers.read", "read",
        description="Search customers in the current store.",
    ),
    "tracking.get": ActionPolicy(
        "tracking.get", "commerce.read", "read",
        description="Inspect shipment and tracking status.",
    ),
    "suppliers.cj.search": ActionPolicy(
        "suppliers.cj.search", "commerce.read", "external",
        description="Search the CJ catalog.",
    ),
    "suppliers.cj.quote": ActionPolicy(
        "suppliers.cj.quote", "commerce.read", "external",
        description="Quote CJ freight.",
    ),
    "suppliers.cj.map_variant": ActionPolicy(
        "suppliers.cj.map_variant", "commerce.write", "write", "simple",
        description="Map a Shopify/local variant to a CJ variant.",
    ),
    "fulfillment.retry": ActionPolicy(
        "fulfillment.retry", "commerce.write", "financial", "critical",
        description="Retry automatic fulfillment; this can create a real supplier order.",
    ),
    "automations.list": ActionPolicy(
        "automations.list", "automations.read", "read",
        description="List automations.",
    ),
    "automations.create": ActionPolicy(
        "automations.create", "automations.write", "write", "simple",
        description="Create an automation.",
    ),
    "automations.update": ActionPolicy(
        "automations.update", "automations.write", "write", "simple",
        description="Modify an automation.",
    ),
    "automations.publish": ActionPolicy(
        "automations.publish", "automations.write", "write", "simple",
        description="Publish the current version of an automation.",
    ),
    "automations.activate": ActionPolicy(
        "automations.activate", "automations.write", "external", "simple",
        description="Activate an automation that may call external services.",
    ),
    "automations.pause": ActionPolicy(
        "automations.pause", "automations.write", "write",
        description="Pause an automation.",
    ),
    "automations.test": ActionPolicy(
        "automations.test", "automations.write", "external", "simple",
        description="Test an automation with controlled execution.",
    ),
    "analytics.summary": ActionPolicy(
        "analytics.summary", "analytics.read", "read",
        description="Read store analytics.",
    ),
}


def get_action_policy(action: str) -> ActionPolicy | None:
    return ACTION_POLICIES.get(action)


def _subscription_write_decision(
    db: Session,
    membership: OrganizationMembership,
    permission: str,
) -> tuple[bool, str | None, str | None]:
    if permission == "billing.write":
        return True, None, None

    organization = membership.organization
    refresh_trial_state(db, organization)

    plan = (organization.plan or "none").strip().lower()
    subscription_status = (organization.subscription_status or "").strip().lower()

    paid_active = (
        plan in {"starter", "growth", "pro", "scale", "agency", "enterprise"}
        and subscription_status in {"active", "trialing"}
    )
    trial_active = plan == "trial" and subscription_status == "trialing"
    trial_bootstrap = (
        permission == "stores.write"
        and pending_trial_can_bootstrap_store(db, organization)
    )

    if paid_active or trial_active or trial_bootstrap:
        return True, None, None

    if subscription_status == "trial_pending":
        return False, "TRIAL_ACTIVATION_REQUIRED", (
            "Conecta tu primera tienda para iniciar tus 7 días gratis."
        )
    if subscription_status == "trial_expired":
        return False, "TRIAL_EXPIRED", (
            "Tu prueba gratuita terminó. Elige un plan para continuar."
        )
    if subscription_status == "trial_blocked":
        return False, "TRIAL_NOT_ELIGIBLE", (
            "Esta cuenta no es elegible para otra prueba gratuita."
        )
    return False, "PLAN_REQUIRED", (
        "No tienes un plan activo. Elige un plan para utilizar esta función."
    )


def _store_access_allowed(
    db: Session,
    membership: OrganizationMembership,
    store_id: int,
) -> tuple[bool, str | None, str | None]:
    store = (
        db.query(Store.id)
        .filter(
            Store.id == store_id,
            Store.organization_id == membership.organization_id,
            Store.active.is_(True),
        )
        .first()
    )
    if store is None:
        return False, "STORE_NOT_FOUND", "Store not found."

    if membership.all_stores:
        return True, None, None

    allowed = (
        db.query(MembershipStore.membership_id)
        .filter(
            MembershipStore.membership_id == membership.id,
            MembershipStore.store_id == store_id,
        )
        .first()
    )
    if allowed is None:
        return False, "STORE_ACCESS_DENIED", "Store access denied."

    return True, None, None


def evaluate_action(
    db: Session,
    membership: OrganizationMembership,
    action: str,
    *,
    store_id: int | None = None,
) -> ActionDecision:
    policy = get_action_policy(action)
    if policy is None:
        return ActionDecision(
            False, action, "", "read", "none",
            code="ACTION_UNKNOWN",
            message="Unknown action.",
            store_id=store_id,
        )

    if not membership.active:
        return ActionDecision(
            False, action, policy.permission, policy.risk, policy.confirmation,
            code="MEMBERSHIP_INACTIVE",
            message="Membership is inactive.",
            store_id=store_id,
        )

    if not has_permission(membership.role, policy.permission):
        return ActionDecision(
            False, action, policy.permission, policy.risk, policy.confirmation,
            code="PERMISSION_DENIED",
            message="Permission denied.",
            store_id=store_id,
        )

    if policy.store_required:
        if store_id is None:
            return ActionDecision(
                False, action, policy.permission, policy.risk, policy.confirmation,
                code="STORE_CONTEXT_REQUIRED",
                message="A store context is required for this action.",
            )
        store_ok, code, message = _store_access_allowed(db, membership, store_id)
        if not store_ok:
            return ActionDecision(
                False, action, policy.permission, policy.risk, policy.confirmation,
                code=code,
                message=message,
                store_id=store_id,
            )

    if policy.permission.endswith(".write"):
        subscription_ok, code, message = _subscription_write_decision(
            db, membership, policy.permission
        )
        if not subscription_ok:
            return ActionDecision(
                False, action, policy.permission, policy.risk, policy.confirmation,
                code=code,
                message=message,
                store_id=store_id,
            )

    return ActionDecision(
        True, action, policy.permission, policy.risk, policy.confirmation,
        store_id=store_id,
    )


def list_action_policies() -> list[ActionPolicy]:
    return sorted(ACTION_POLICIES.values(), key=lambda policy: policy.action)


__all__ = [
    "ACTION_POLICIES",
    "ActionDecision",
    "ActionPolicy",
    "evaluate_action",
    "get_action_policy",
    "list_action_policies",
]
