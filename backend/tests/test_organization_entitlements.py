from types import SimpleNamespace

from app.organization_entitlements import (
    memberships_allow_multi_org_access,
    organization_allows_multi_org_access,
)


def _membership(plan: str):
    return SimpleNamespace(
        organization=SimpleNamespace(plan=plan),
    )


def test_standard_plans_do_not_allow_multi_org_access():
    for plan in ("starter", "growth", "pro", "scale", "none", None):
        organization = SimpleNamespace(plan=plan)
        assert organization_allows_multi_org_access(organization) is False


def test_agency_and_enterprise_allow_multi_org_access():
    assert organization_allows_multi_org_access(SimpleNamespace(plan="agency"))
    assert organization_allows_multi_org_access(SimpleNamespace(plan="ENTERPRISE"))


def test_any_entitled_membership_unlocks_multi_org_context():
    memberships = [_membership("growth"), _membership("agency")]
    assert memberships_allow_multi_org_access(memberships) is True


def test_standard_memberships_remain_single_org():
    memberships = [_membership("growth"), _membership("scale")]
    assert memberships_allow_multi_org_access(memberships) is False
