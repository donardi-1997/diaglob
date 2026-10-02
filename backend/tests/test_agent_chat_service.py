"""Operations copilot orchestration tests."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.model_domains.ai_agent import AgentActionApproval, AgentChatMessage, AgentChatToolCall
from app.models import AutomationFlow, Order, Organization, OrganizationMembership, Store, User
from app.services import agent_chat_service as service


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def seed(db):
    organization = Organization(
        name="Copilot Org",
        slug="copilot-org",
        plan="growth",
        subscription_status="active",
        active=True,
    )
    db.add(organization)
    db.flush()

    user = User(
        email="copilot@example.com",
        name="Copilot User",
        active=True,
    )
    db.add(user)
    db.flush()

    membership = OrganizationMembership(
        user_id=user.id,
        organization_id=organization.id,
        role="manager",
        all_stores=True,
        active=True,
    )
    db.add(membership)
    db.flush()

    store = Store(
        organization_id=organization.id,
        name="Copilot Store",
        slug="copilot-store",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
        active=True,
        deleted=False,
    )
    db.add(store)
    db.flush()

    order = Order(
        organization_id=organization.id,
        store_id=store.id,
        external_order_id="COPILOT-1",
        shopify_order_id="COPILOT-1",
        order_number="C-100",
        total_amount=199000,
        currency="COP",
        financial_status="paid",
        payment_status="paid",
        fulfillment_status="unfulfilled",
        lifecycle_status="paid",
        source="shopify",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(order)
    db.commit()
    db.refresh(membership)
    return membership, store, order


def model_response(content, stop_reason):
    return {
        "message": {"role": "assistant", "content": content},
        "stop_reason": stop_reason,
        "usage": {
            "input_tokens": 20,
            "output_tokens": 10,
            "total_tokens": 30,
        },
        "model_id": "test-model",
    }


def test_read_tool_executes_and_model_resumes(db, monkeypatch):
    membership, store, order = seed(db)
    session = service.create_chat_session(
        db,
        membership,
        store_id=store.id,
        context={"page": "commerce"},
    )
    calls = []

    def fake_converse(**kwargs):
        calls.append(kwargs["messages"])
        if len(calls) == 1:
            return model_response(
                [
                    {
                        "toolUse": {
                            "toolUseId": "tool-1",
                            "name": "orders.list",
                            "input": {"limit": 10},
                        }
                    }
                ],
                "tool_use",
            )
        assert calls[-1][-1]["role"] == "user"
        tool_result = calls[-1][-1]["content"][0]["toolResult"]
        assert tool_result["toolUseId"] == "tool-1"
        assert tool_result["content"][0]["json"]["status"] == "success"
        assert tool_result["content"][0]["json"]["result"]["items"][0]["id"] == order.id
        return model_response(
            [{"text": "Encontré un pedido pagado pendiente de fulfillment."}],
            "end_turn",
        )

    monkeypatch.setattr(service, "converse", fake_converse)

    result = service.send_chat_message(
        db,
        membership,
        session["id"],
        text="¿Qué pedidos pagados tengo?",
    )

    assert len(calls) == 2
    assert result["has_pending_turn"] is False
    assert result["pending_actions"] == []
    assert result["messages"][-1]["text"].startswith("Encontré")
    assert result["messages"][-1]["billable"] is True
    tool_calls = db.query(AgentChatToolCall).all()
    assert len(tool_calls) == 1
    assert tool_calls[0].status == "success"
    assert db.query(AgentChatMessage).filter(AgentChatMessage.billable.is_(True)).count() == 1


def test_write_tool_pauses_for_approval_then_resumes_once(db, monkeypatch):
    membership, store, _order = seed(db)
    session = service.create_chat_session(
        db,
        membership,
        store_id=store.id,
    )
    model_calls = 0

    def fake_converse(**_kwargs):
        nonlocal model_calls
        model_calls += 1
        if model_calls == 1:
            return model_response(
                [
                    {
                        "text": "Puedo crear el flujo."
                    },
                    {
                        "toolUse": {
                            "toolUseId": "tool-write-1",
                            "name": "automations.create",
                            "input": {
                                "name": "Pedidos de alto valor",
                                "graph": {},
                            },
                        }
                    },
                ],
                "tool_use",
            )
        return model_response(
            [{"text": "La automatización fue creada como borrador."}],
            "end_turn",
        )

    monkeypatch.setattr(service, "converse", fake_converse)

    pending = service.send_chat_message(
        db,
        membership,
        session["id"],
        text="Crea una automatización para pedidos de alto valor.",
    )

    assert model_calls == 1
    assert len(pending["pending_actions"]) == 1
    action = pending["pending_actions"][0]
    assert action["tool_name"] == "automations.create"
    assert action["approval"]["status"] == "pending"
    assert db.query(AutomationFlow).count() == 0

    completed = service.approve_chat_action(
        db,
        membership,
        session["id"],
        action["approval"]["id"],
    )

    assert model_calls == 2
    assert completed["pending_actions"] == []
    assert completed["messages"][-1]["text"].startswith("La automatización")
    assert db.query(AutomationFlow).count() == 1
    approval = db.query(AgentActionApproval).one()
    assert approval.status == "consumed"


def test_pending_approval_blocks_new_user_turn(db, monkeypatch):
    membership, store, _order = seed(db)
    session = service.create_chat_session(db, membership, store_id=store.id)

    monkeypatch.setattr(
        service,
        "converse",
        lambda **_kwargs: model_response(
            [
                {
                    "toolUse": {
                        "toolUseId": "tool-write-2",
                        "name": "automations.create",
                        "input": {"name": "Blocked flow", "graph": {}},
                    }
                }
            ],
            "tool_use",
        ),
    )

    service.send_chat_message(
        db,
        membership,
        session["id"],
        text="Crea un flujo.",
    )

    with pytest.raises(service.AgentChatError, match="CHAT_APPROVAL_PENDING"):
        service.send_chat_message(
            db,
            membership,
            session["id"],
            text="Mientras tanto dime otra cosa.",
        )


def test_cancelled_action_is_returned_to_model_without_side_effect(db, monkeypatch):
    membership, store, _order = seed(db)
    session = service.create_chat_session(db, membership, store_id=store.id)
    model_calls = 0

    def fake_converse(**kwargs):
        nonlocal model_calls
        model_calls += 1
        if model_calls == 1:
            return model_response(
                [
                    {
                        "toolUse": {
                            "toolUseId": "tool-write-3",
                            "name": "automations.create",
                            "input": {"name": "Cancelled flow", "graph": {}},
                        }
                    }
                ],
                "tool_use",
            )
        tool_result = kwargs["messages"][-1]["content"][0]["toolResult"]
        assert tool_result["content"][0]["json"]["status"] == "cancelled"
        return model_response(
            [{"text": "De acuerdo, no realicé el cambio."}],
            "end_turn",
        )

    monkeypatch.setattr(service, "converse", fake_converse)

    pending = service.send_chat_message(
        db,
        membership,
        session["id"],
        text="Crea un flujo que quizá no quiera.",
    )
    approval_id = pending["pending_actions"][0]["approval"]["id"]

    result = service.cancel_chat_action(
        db,
        membership,
        session["id"],
        approval_id,
    )

    assert result["messages"][-1]["text"] == "De acuerdo, no realicé el cambio."
    assert db.query(AutomationFlow).count() == 0
    assert db.query(AgentActionApproval).one().status == "cancelled"
