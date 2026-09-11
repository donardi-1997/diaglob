from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class OrganizationPlanLimits:
    active_stores: int
    monthly_customers: int
    members: int
    included_ai_responses: int


PLAN_LIMITS: dict[str, OrganizationPlanLimits] = {
    "trial": OrganizationPlanLimits(
        active_stores=1,
        monthly_customers=1_000,
        members=2,
        included_ai_responses=1_000,
    ),
    "starter": OrganizationPlanLimits(
        active_stores=1,
        monthly_customers=1_000,
        members=2,
        included_ai_responses=1_000,
    ),
    "growth": OrganizationPlanLimits(
        active_stores=2,
        monthly_customers=5_000,
        members=5,
        included_ai_responses=5_000,
    ),
    "pro": OrganizationPlanLimits(
        active_stores=5,
        monthly_customers=20_000,
        members=10,
        included_ai_responses=20_000,
    ),
    "scale": OrganizationPlanLimits(
        active_stores=10,
        monthly_customers=50_000,
        members=15,
        included_ai_responses=50_000,
    ),
}


NO_PLAN_LIMITS = OrganizationPlanLimits(
    active_stores=0,
    monthly_customers=0,
    members=0,
    included_ai_responses=0,
)


def normalize_plan(
    plan: Optional[str],
) -> str:
    return (
        (plan or "none")
        .strip()
        .lower()
    )


def get_organization_limits(
    organization,
) -> OrganizationPlanLimits:
    """
    Devuelve los límites globales de la organización.

    Las tiendas NO reciben capacidad individual.
    Todas las tiendas de una organización comparten
    estos mismos límites.
    """

    plan = normalize_plan(
        getattr(
            organization,
            "plan",
            None,
        )
    )

    return PLAN_LIMITS.get(
        plan,
        NO_PLAN_LIMITS,
    )


def get_limits_for_plan(
    plan: Optional[str],
) -> OrganizationPlanLimits:
    """
    Útil para previews de upgrade/downgrade,
    antes de modificar Organization.plan.
    """

    return PLAN_LIMITS.get(
        normalize_plan(plan),
        NO_PLAN_LIMITS,
    )


def organization_has_plan(
    organization,
) -> bool:
    return (
        normalize_plan(
            getattr(
                organization,
                "plan",
                None,
            )
        )
        in PLAN_LIMITS
    )


def organization_can_activate_store(
    organization,
    current_active_stores: int,
) -> bool:
    limits = get_organization_limits(
        organization,
    )

    return (
        current_active_stores
        < limits.active_stores
    )


def organization_can_add_member(
    organization,
    current_members: int,
) -> bool:
    limits = get_organization_limits(
        organization,
    )

    return (
        current_members
        < limits.members
    )


def organization_has_customer_capacity(
    organization,
    monthly_customer_count: int,
    additional_customers: int = 1,
) -> bool:
    limits = get_organization_limits(
        organization,
    )

    return (
        monthly_customer_count
        + additional_customers
        <= limits.monthly_customers
    )


def organization_usage(
    organization,
    *,
    active_stores: int,
    monthly_customers: int,
    members: int,
) -> dict:
    limits = get_organization_limits(
        organization,
    )

    return {
        "plan": normalize_plan(
            getattr(
                organization,
                "plan",
                None,
            )
        ),

        "stores": {
            "used": active_stores,
            "limit": limits.active_stores,
            "remaining": max(
                limits.active_stores
                - active_stores,
                0,
            ),
        },

        "customers": {
            "used": monthly_customers,
            "limit": limits.monthly_customers,
            "remaining": max(
                limits.monthly_customers
                - monthly_customers,
                0,
            ),
        },

        "members": {
            "used": members,
            "limit": limits.members,
            "remaining": max(
                limits.members
                - members,
                0,
            ),
        },
    }
