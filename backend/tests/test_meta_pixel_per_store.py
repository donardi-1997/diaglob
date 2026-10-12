"""Store-specific Meta Pixel settings; synthetic SQLite, no Meta/Shopify requests."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.meta_pixel import (
    MetaPixelSettings, delete_meta_pixel, get_meta_pixel, router, set_meta_pixel,
)
from app.api.store_access import require_authorized_path_store
from app.db import Base
from app.models import MetaPixelConfiguration, Organization, Store


@pytest.fixture()
def data():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        orgs = [
            Organization(id=11, name="Alpha", slug="pixel-alpha"),
            Organization(id=22, name="Beta", slug="pixel-beta"),
        ]
        stores = [
            Store(id=71, organization_id=11, name="One", slug="one",
                  country_code="CO", currency="COP", timezone="America/Bogota",
                  active=True, deleted=False),
            Store(id=72, organization_id=11, name="Two", slug="two",
                  country_code="CO", currency="COP", timezone="America/Bogota",
                  active=True, deleted=False),
            Store(id=73, organization_id=22, name="Foreign", slug="foreign",
                  country_code="MX", currency="MXN", timezone="America/Mexico_City",
                  active=True, deleted=False),
        ]
        db.add_all(orgs + stores)
        db.commit()
        yield db, stores
    engine.dispose()


def test_pixel_saved_independently_per_store_and_never_activated(data):
    db, stores = data
    member = SimpleNamespace(organization_id=11)
    assert get_meta_pixel(71, member, stores[0], db)["configured"] is False
    first = set_meta_pixel(
        71, MetaPixelSettings(pixel_id="123456789012345",
                              existing_tracking="shopify_meta"),
        member, stores[0], db,
    )
    assert first["configured"] is True
    assert first["enabled"] is False
    assert first["extension_installed"] is False
    assert first["status"] == "awaiting_extension"
    assert first["duplicate_tracking_risk"] == "high"
    second = set_meta_pixel(
        72, MetaPixelSettings(pixel_id="222222222222222",
                              existing_tracking="none"),
        member, stores[1], db,
    )
    assert second["duplicate_tracking_risk"] == "none_reported"
    assert get_meta_pixel(71, member, stores[0], db)["pixel_id"] == "123456789012345"
    assert get_meta_pixel(72, member, stores[1], db)["pixel_id"] == "222222222222222"
    assert db.query(MetaPixelConfiguration).count() == 2
    first = set_meta_pixel(
        71, MetaPixelSettings(pixel_id="333333333333333"),
        member, stores[0], db,
    )
    assert first["pixel_id"] == "333333333333333"
    assert first["enabled"] is False
    assert db.query(MetaPixelConfiguration).count() == 2
    delete_meta_pixel(71, member, stores[0], db)
    assert get_meta_pixel(71, member, stores[0], db)["configured"] is False
    assert get_meta_pixel(72, member, stores[1], db)["configured"] is True


@pytest.mark.parametrize("pixel_id", ["", "abc", "123abc456", "1234567", "1" * 31])
def test_reject_invalid_pixel_ids(pixel_id):
    with pytest.raises(ValidationError):
        MetaPixelSettings(pixel_id=pixel_id)


def test_inactive_store_rejected(data):
    db, stores = data
    stores[0].active = False
    with pytest.raises(HTTPException) as exc:
        set_meta_pixel(71, MetaPixelSettings(pixel_id="123456789012345"),
                       SimpleNamespace(organization_id=11), stores[0], db)
    assert exc.value.status_code == 409


def test_routes_require_store_membership_and_role_permissions():
    from app.api.store_access import require_authorized_path_store
    paths = [r for r in router.routes if "/meta-pixel" in r.path]
    assert len(paths) == 7
    for route in paths:
        assert any(
            dependency.call is require_authorized_path_store
            for dependency in route.dependant.dependencies
        )
        assert any(
            dependency.call.__name__ == "dependency"
            for dependency in route.dependant.dependencies
        )


def test_restricted_member_cannot_read_another_store_in_same_org(data):
    db, stores = data
    member = SimpleNamespace(organization_id=11, all_stores=False,
                             stores=[stores[0]])
    with pytest.raises(HTTPException) as exc:
        require_authorized_path_store(store_id=72, membership=member, db=db)
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        require_authorized_path_store(store_id=73, membership=member, db=db)
    assert exc.value.status_code == 404
