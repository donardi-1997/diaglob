"""HTTP authorization regressions with synthetic, in-memory tenant/store data."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import knowledge, payments, post_sales, telegram
from app.api.deps import get_current_membership
from app.db import Base, get_db
from app.models import (
    Conversation, Customer, KnowledgeBase, KnowledgeSource, Organization,
    OrganizationMembership, Store, User,
)
from app.services import telegram_service
from app.telegram_models import TelegramConnection
from app.telegram_security import encrypt_telegram_secret


@pytest.fixture(scope="module")
def store_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db(store_engine):
    session = sessionmaker(bind=store_engine, autoflush=False)()
    try:
        yield session
    finally:
        session.close()
        with store_engine.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())


@pytest.fixture
def data(db, monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    org = Organization(name="Scope org", slug="scope-org", plan="growth", subscription_status="active")
    foreign_org = Organization(name="Foreign org", slug="foreign-org", plan="growth", subscription_status="active")
    user = User(name="Restricted manager", email="scope@example.invalid", external_auth_id="scope-user")
    db.add_all([org, foreign_org, user])
    db.flush()
    stores = [
        Store(organization_id=owner.id, name=slug, slug=slug, country_code="CO", currency="COP",
              timezone="America/Bogota", active=True, deleted=False)
        for owner, slug in [(org, "assigned"), (org, "unassigned"), (foreign_org, "foreign")]
    ]
    db.add_all(stores)
    db.flush()
    assigned, unassigned, foreign = stores
    membership = OrganizationMembership(
        organization_id=org.id, user_id=user.id, role="manager", all_stores=False, active=True,
    )
    membership.stores = [assigned]
    db.add(membership)
    conversations = []
    for store in stores:
        customer = Customer(organization_id=store.organization_id, name="Synthetic buyer", phone=f"telegram:{store.id}")
        db.add(customer)
        db.flush()
        conversation = Conversation(
            organization_id=store.organization_id, store_id=store.id, customer_id=customer.id,
            channel="Telegram", mode="human",
        )
        db.add_all([conversation, TelegramConnection(
            organization_id=store.organization_id, store_id=store.id, bot_id=100 + store.id,
            bot_token_encrypted=encrypt_telegram_secret("synthetic-token"),
            webhook_secret_encrypted=encrypt_telegram_secret("synthetic-secret"),
            webhook_path_token=f"synthetic-{store.id}", status="connected",
        )])
        conversations.append(conversation)
    kbs = []
    for name, owner, kb_stores, scope in [
        ("Assigned KB", org, [assigned], "selected_stores"),
        ("Hidden KB", org, [unassigned], "selected_stores"),
        ("Shared KB", org, [assigned, unassigned], "selected_stores"),
        ("Organization KB", org, [], "organization"),
        ("Foreign KB", foreign_org, [foreign], "selected_stores"),
    ]:
        kb = KnowledgeBase(
            organization_id=owner.id, name=name, scope=scope, external_status="ready",
            external_id="synthetic-kb", external_data_source_id="synthetic-ds",
        )
        kb.stores = kb_stores
        db.add(kb)
        db.flush()
        db.add(KnowledgeSource(
            organization_id=owner.id, knowledge_base_id=kb.id, name="synthetic.txt",
            s3_bucket="synthetic", s3_key="synthetic", source_type="file",
        ))
        kbs.append(kb)
    db.commit()
    sender = Mock(return_value={"message_id": 123})
    monkeypatch.setattr(telegram_service, "telegram_send_message", sender)
    # If a broken guard reaches connect, it must still never call a real provider.
    monkeypatch.setattr(telegram_service, "get_me", Mock(side_effect=AssertionError("unauthorized provider call")))
    monkeypatch.setattr(telegram_service, "delete_webhook", Mock(return_value=True))
    return SimpleNamespace(
        membership=membership, assigned=assigned, unassigned=unassigned, foreign=foreign,
        conversations=conversations, assigned_kb=kbs[0], hidden_kb=kbs[1], shared_kb=kbs[2],
        organization_kb=kbs[3], foreign_kb=kbs[4], sender=sender,
    )


@pytest.fixture
def client(db, data):
    app = FastAPI()
    for router in [payments.router, telegram.router, post_sales.router, knowledge.router]:
        app.include_router(router)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_membership] = lambda: data.membership
    with TestClient(app) as client:
        yield client


STORE_REQUESTS = [
    ("GET", "payments/providers", None),
    ("GET", "payments/nequi/status", None),
    ("POST", "payments/nequi/connect", {"provider": "nequi", "client_id": "id", "client_secret": "secret"}),
    ("DELETE", "payments/nequi/disconnect", None),
    ("POST", "payments", {"amount": "100", "currency": "COP", "customer_phone": "+573000000000"}),
    ("GET", "payments/99", None),
    ("POST", "payments/99/reconcile", None),
    ("POST", "payments/99/cancel", None),
    ("POST", "payments/99/reverse", {"reason": "Synthetic test"}),
    ("GET", "telegram", None),
    ("POST", "telegram/connect", {"bot_token": "synthetic-token"}),
    ("DELETE", "telegram/disconnect", None),
    ("GET", "post-sales/summary", None),
    ("GET", "post-sales/cases", None),
    ("POST", "post-sales/cases", {"case_type": "refund", "title": "Synthetic case"}),
    ("GET", "post-sales/cases/99", None),
    ("PATCH", "post-sales/cases/99", {"status": "closed"}),
    ("POST", "post-sales/cases/99/notes", {"note": "Synthetic note"}),
]


@pytest.mark.parametrize("method,path,body", STORE_REQUESTS)
@pytest.mark.parametrize("scope,expected", [("unassigned", 403), ("foreign", 404), ("deleted", 404)])
def test_store_routes_reject_unauthorized_scope(client, db, data, method, path, body, scope, expected):
    store = data.foreign if scope == "foreign" else data.unassigned
    if scope == "deleted":
        store.deleted = True
        db.commit()
    response = client.request(method, f"/api/stores/{store.id}/{path}", json=body)
    assert response.status_code == expected, response.text
    data.sender.assert_not_called()


@pytest.mark.parametrize("path", ["payments/providers", "payments/nequi/status", "telegram", "post-sales/cases"])
def test_assigned_store_reads_still_work(client, data, path):
    assert client.get(f"/api/stores/{data.assigned.id}/{path}").status_code == 200


@pytest.mark.parametrize("path", ["payments/providers", "telegram", "post-sales/cases"])
def test_all_store_members_keep_organization_access(client, db, data, path):
    data.membership.all_stores = True
    db.commit()
    assert client.get(f"/api/stores/{data.unassigned.id}/{path}").status_code == 200


@pytest.mark.parametrize("scope,expected", [("unassigned", 403), ("foreign", 404), ("deleted", 404)])
def test_telegram_send_checks_conversation_store(client, db, data, scope, expected):
    conversation = data.conversations[2 if scope == "foreign" else 1]
    if scope == "deleted":
        data.unassigned.deleted = True
        db.commit()
    response = client.post(f"/api/conversations/{conversation.id}/telegram/send", json={"text": "Synthetic test"})
    assert response.status_code == expected
    data.sender.assert_not_called()


def test_telegram_send_to_assigned_conversation_still_works(client, data):
    response = client.post(
        f"/api/conversations/{data.conversations[0].id}/telegram/send", json={"text": "Synthetic test"},
    )
    assert response.status_code == 200, response.text
    data.sender.assert_called_once()


KB_REQUESTS = [
    ("GET", "", None),
    ("PATCH", "", {"name": "Unauthorized rename"}),
    ("DELETE", "", None),
    ("POST", "/retry-provisioning", None),
    ("GET", "/sources", None),
    ("POST", "/sources", None),
    ("DELETE", "/sources/99", None),
    ("POST", "/sources/google-sheet", {"spreadsheet_id": "synthetic", "sheet_name": "Sheet1"}),
    ("POST", "/sources/google-doc", {"file_id": "synthetic", "file_name": "Synthetic", "mime_type": "text/plain"}),
    ("POST", "/sources/google-drive-file", {"file_id": "synthetic", "file_name": "Synthetic", "mime_type": "text/plain"}),
    ("POST", "/sources/google-drive-folder", {"folder_id": "synthetic", "folder_name": "Synthetic"}),
    ("POST", "/sources/99/sync", None),
    ("POST", "/sources/99/sync-folder", None),
    ("POST", "/sources/99/sync-drive-file", None),
    ("GET", "/sources/99/ingestion-status", None),
    ("GET", "/sources/99/freshness", None),
]


@pytest.mark.parametrize("method,path,body", KB_REQUESTS)
@pytest.mark.parametrize("scope", ["hidden_kb", "foreign_kb"])
def test_all_knowledge_paths_deny_invisible_bases(client, data, method, path, body, scope):
    kb = getattr(data, scope)
    kwargs = {"json": body}
    if method == "POST" and path == "/sources":
        kwargs = {"files": {"file": ("synthetic.txt", b"Synthetic content", "text/plain")}}
    response = client.request(method, f"/api/knowledge-bases/{kb.id}{path}", **kwargs)
    assert response.status_code == 404, response.text
    assert kb.name != "Unauthorized rename"


def test_knowledge_collection_filters_invisible_bases(client, data):
    response = client.get("/api/knowledge-bases")
    assert response.status_code == 200
    assert {item["id"] for item in response.json()["items"]} == {
        data.assigned_kb.id, data.shared_kb.id, data.organization_kb.id,
    }


@pytest.mark.parametrize("scope", ["shared_kb", "organization_kb"])
def test_restricted_members_can_read_but_not_modify_shared_knowledge(client, data, scope):
    kb = getattr(data, scope)
    assert client.get(f"/api/knowledge-bases/{kb.id}").status_code == 200
    response = client.patch(f"/api/knowledge-bases/{kb.id}", json={"name": "Unauthorized rename"})
    assert response.status_code == 403
    assert kb.name != "Unauthorized rename"


def test_assigned_knowledge_can_be_modified(client, data):
    response = client.patch(f"/api/knowledge-bases/{data.assigned_kb.id}", json={"name": "Authorized rename"})
    assert response.status_code == 200
    assert data.assigned_kb.name == "Authorized rename"


def test_all_store_members_can_manage_shared_knowledge(client, db, data):
    data.membership.all_stores = True
    db.commit()
    response = client.patch(f"/api/knowledge-bases/{data.shared_kb.id}", json={"name": "Authorized rename"})
    assert response.status_code == 200


def test_every_affected_store_path_has_shared_authorization_guard():
    from app.api.store_access import require_authorized_path_store

    for router in [payments.router, telegram.router, post_sales.router]:
        for route in router.routes:
            if "{store_id}" in route.path:
                assert any(dep.dependency is require_authorized_path_store for dep in route.dependencies), route.path


def test_every_knowledge_path_has_shared_authorization_guard():
    from app.api.knowledge_access import require_authorized_knowledge_base

    paths = [route for route in knowledge.router.routes if "{knowledge_base_id}" in route.path]
    assert len(paths) >= 16
    for route in paths:
        assert any(dep.dependency is require_authorized_knowledge_base for dep in route.dependencies), route.path
