"""Organization-level product entitlements.

Multi-organization access is intentionally a premium capability. The policy is
kept separate from billing price configuration so Agency/Enterprise can be
introduced commercially later without changing tenant isolation primitives.
"""

MULTI_ORGANIZATION_PLANS = frozenset({"agency", "enterprise"})


def normalize_plan(plan: str | None) -> str:
    return (plan or "none").strip().lower()


def organization_allows_multi_org_access(organization) -> bool:
    """Return whether an organization grants multi-org account access."""
    return normalize_plan(getattr(organization, "plan", None)) in MULTI_ORGANIZATION_PLANS


def memberships_allow_multi_org_access(memberships) -> bool:
    """A user may select among multiple orgs only with a premium entitlement.

    The entitlement can come from any active organization membership. Normal
    Starter/Growth/Pro/Scale users therefore remain single-organization users.
    """
    return any(
        organization_allows_multi_org_access(membership.organization)
        for membership in memberships
    )
