"""Boundary tests for the physically extracted tenancy model domain."""

from datetime import timedelta

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models as legacy
from app.db import Base
from app.model_domains import tenancy


def test_legacy_model_surface_reexports_tenancy_classes():
    assert legacy.Organization is tenancy.Organization
    assert legacy.Store is tenancy.Store
    assert legacy.User is tenancy.User
    assert legacy.OrganizationInvitation is tenancy.OrganizationInvitation
    assert legacy.OrganizationMembership is tenancy.OrganizationMembership
    assert legacy.MembershipStore is tenancy.MembershipStore

    assert legacy.agent_stores is tenancy.agent_stores
    assert legacy.knowledge_base_stores is tenancy.knowledge_base_stores
    assert legacy.organization_invitation_stores is tenancy.organization_invitation_stores


def test_tenancy_models_are_physically_owned_by_domain_module():
    assert tenancy.Organization.__module__ == "app.model_domains.tenancy"
    assert tenancy.Store.__module__ == "app.model_domains.tenancy"
    assert tenancy.User.__module__ == "app.model_domains.tenancy"
    assert tenancy.OrganizationInvitation.__module__ == "app.model_domains.tenancy"
    assert tenancy.OrganizationMembership.__module__ == "app.model_domains.tenancy"
    assert tenancy.MembershipStore.__module__ == "app.model_domains.tenancy"


def test_tenancy_table_contracts_remain_registered_once():
    expected = {
        "organizations": tenancy.Organization.__table__,
        "stores": tenancy.Store.__table__,
        "users": tenancy.User.__table__,
        "organization_invitations": tenancy.OrganizationInvitation.__table__,
        "organization_memberships": tenancy.OrganizationMembership.__table__,
        "membership_stores": tenancy.MembershipStore.__table__,
        "agent_stores": tenancy.agent_stores,
        "knowledge_base_stores": tenancy.knowledge_base_stores,
        "organization_invitation_stores": tenancy.organization_invitation_stores,
    }

    for table_name, table in expected.items():
        assert Base.metadata.tables[table_name] is table


def test_store_and_membership_unique_constraints_are_preserved():
    store_constraints = {constraint.name for constraint in tenancy.Store.__table__.constraints}
    membership_constraints = {
        constraint.name for constraint in tenancy.OrganizationMembership.__table__.constraints
    }

    assert "uq_store_org_slug" in store_constraints
    assert "uq_user_organization_membership" in membership_constraints


def test_relationship_secondaries_keep_the_same_association_tables():
    store_relationships = inspect(tenancy.Store).relationships
    invitation_relationships = inspect(tenancy.OrganizationInvitation).relationships
    membership_relationships = inspect(tenancy.OrganizationMembership).relationships

    assert store_relationships.agents.secondary is tenancy.agent_stores
    assert store_relationships.knowledge_bases.secondary is tenancy.knowledge_base_stores
    assert invitation_relationships.stores.secondary is tenancy.organization_invitation_stores
    assert membership_relationships.stores.secondary is tenancy.MembershipStore.__table__


def test_store_active_since_event_listeners_survive_physical_move():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        organization = tenancy.Organization(
            name="Tenancy Boundary Org",
            slug="tenancy-boundary-org",
            plan="starter",
            subscription_status="active",
        )
        db.add(organization)
        db.flush()

        store = tenancy.Store(
            organization_id=organization.id,
            name="Boundary Store",
            slug="boundary-store",
            country_code="CO",
            currency="COP",
            timezone="America/Bogota",
            active=True,
        )
        db.add(store)
        db.commit()
        db.refresh(store)

        assert store.active_since is not None
        activated_at = store.active_since

        store.active = False
        db.commit()
        db.refresh(store)
        assert store.active_since is None

        store.active = True
        db.commit()
        db.refresh(store)
        assert store.active_since is not None
        assert store.active_since >= activated_at - timedelta(seconds=1)

    Base.metadata.drop_all(bind=engine)
