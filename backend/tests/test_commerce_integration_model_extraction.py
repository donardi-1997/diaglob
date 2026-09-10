from app import models
from app.model_domains.commerce_integrations import (
    CommerceConnection,
    DropiConnection,
    MetaAdsConnection,
)


def test_legacy_exports_preserve_class_identity():
    assert CommerceConnection is models.CommerceConnection
    assert DropiConnection is models.DropiConnection
    assert MetaAdsConnection is models.MetaAdsConnection


def test_models_are_physically_owned_by_domain_module():
    assert CommerceConnection.__module__ == "app.model_domains.commerce_integrations"
    assert DropiConnection.__module__ == "app.model_domains.commerce_integrations"
    assert MetaAdsConnection.__module__ == "app.model_domains.commerce_integrations"


def test_models_share_legacy_base_metadata():
    for model in (CommerceConnection, DropiConnection, MetaAdsConnection):
        assert model.__table__ is models.Base.metadata.tables[model.__tablename__]


def test_table_contracts_are_preserved():
    assert set(CommerceConnection.__table__.columns.keys()) == {
        "id", "organization_id", "store_id", "provider", "external_store_url",
        "access_token_encrypted", "refresh_token_encrypted", "api_key_encrypted",
        "api_secret_encrypted", "access_token_expires_at", "refresh_token_expires_at",
        "scopes", "status", "connected_at", "last_sync_at", "last_error",
        "created_at", "updated_at",
    }
    assert set(DropiConnection.__table__.columns.keys()) == {
        "id", "organization_id", "store_id", "external_store_id", "api_url",
        "api_token_encrypted", "webhook_token", "status", "connected_at",
        "last_sync_at", "last_error", "created_at", "updated_at",
    }
    assert set(MetaAdsConnection.__table__.columns.keys()) == {
        "id", "organization_id", "store_id", "provider", "external_account_id",
        "external_account_name", "account_currency", "account_timezone",
        "access_token_encrypted", "status", "last_sync_at", "last_sync_status",
        "last_error_category", "connected_at", "created_at", "updated_at",
    }


def test_named_unique_constraints_are_preserved():
    commerce_names = {c.name for c in CommerceConnection.__table__.constraints}
    dropi_names = {c.name for c in DropiConnection.__table__.constraints}
    meta_names = {c.name for c in MetaAdsConnection.__table__.constraints}

    assert "uq_commerce_connection_store" in commerce_names
    assert "uq_commerce_provider_store_url" in commerce_names
    assert "uq_dropi_connection_store" in dropi_names
    assert "uq_dropi_webhook_token" in dropi_names
    assert "uq_meta_ads_connection_store" in meta_names
