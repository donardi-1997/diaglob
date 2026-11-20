"""Ready-to-use automation models: catalog contract and one-step setup."""
import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.automation_flow_events import EVENT_TO_FLOW_TRIGGER, format_money_display
from app.automation_flow_graph import validate_graph
from app.automation_flow_templates import FLOW_TEMPLATES, get_flow_template, get_flow_templates
from app.db import Base, get_db
from app.main import app, get_current_membership, get_current_user
from app.models import (
    AutomationFlow,
    Organization,
    OrganizationMembership,
    Store,
    User,
    WhatsAppConnection,
    WhatsAppMessageTemplate,
)
from app.services.automation_flow_template_setup import (
    FlowTemplateSetup,
    FlowTemplateSetupError,
    create_flow_from_model,
)
from app.whatsapp_compliance import FLOW_TEMPLATE_VARIABLES

_PLACEHOLDER = re.compile(r"\{\{\s*(\d+)\s*\}\}")
_RUNTIME_VAR = re.compile(r"\{\{\s*([a-z_.]+)\s*\}\}")


# ------------------------------------------------------------------ catalog

@pytest.mark.parametrize("model", [m for m in FLOW_TEMPLATES if "whatsapp" in m["required_integrations"]],
                         ids=lambda m: m["id"])
def test_every_whatsapp_model_ships_a_consistent_meta_template(model):
    setup = model.get("whatsapp_setup")
    assert setup, "WhatsApp models must suggest a Meta template"
    suggested = setup["suggested_template"]
    placeholders = sorted({int(n) for n in _PLACEHOLDER.findall(suggested["body"])})
    assert placeholders == list(range(1, len(suggested["variables"]) + 1))
    assert set(suggested["variables"]) <= FLOW_TEMPLATE_VARIABLES
    assert suggested["category"] in {"UTILITY", "MARKETING"}
    assert re.fullmatch(r"[a-z0-9_]{1,512}", suggested["name"])  # Meta naming rule
    message = next(n for n in model["graph"]["nodes"] if n["id"] == setup["node_id"])
    assert message["type"] == "message"
    # The in-window free text uses the same allow-listed data as the template.
    assert set(_RUNTIME_VAR.findall(message["config"]["message_template"])) <= FLOW_TEMPLATE_VARIABLES
    assert validate_graph(model["graph"]) == []


def test_model_ids_and_meta_names_are_unique():
    ids = [m["id"] for m in FLOW_TEMPLATES]
    names = [m["whatsapp_setup"]["suggested_template"]["name"] for m in FLOW_TEMPLATES if m.get("whatsapp_setup")]
    assert len(ids) == len(set(ids))
    assert len(names) == len(set(names))


def test_trigger_mode_reflects_real_event_wiring():
    modes = {m["id"]: (m["trigger_type"], m["trigger_mode"]) for m in get_flow_templates()}
    wired = set(EVENT_TO_FLOW_TRIGGER.values())
    for trigger, mode in modes.values():
        assert mode == ("automatic" if trigger in wired else "manual")
    assert modes["order_confirmation_flow"] == ("order_created", "automatic")
    assert modes["new_customer_welcome_flow"][1] == "manual"


@pytest.mark.parametrize("amount,currency,expected", [
    (125000, "COP", "125.000 COP"),
    (125000.0, "COP", "125.000 COP"),
    (49.9, "USD", "49,90 USD"),
    (1234567.5, "MXN", "1.234.567,50 MXN"),
    (0, None, "0"),
    (None, "COP", "0 COP"),
])
def test_money_display_uses_latam_format(amount, currency, expected):
    assert format_money_display(amount, currency) == expected


# ------------------------------------------------------------------ service

@pytest.fixture()
def ctx():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    org = Organization(name="Model Org", slug="model-org", plan="pro", subscription_status="active")
    session.add(org)
    session.flush()
    store = Store(organization_id=org.id, name="Model Store", slug="model-store", country_code="CO",
                  currency="COP", timezone="America/Bogota", default_language="es")
    session.add(store)
    session.flush()
    user = User(email="models@test.com", name="Models", external_auth_id="models-sub")
    session.add(user)
    session.flush()
    membership = OrganizationMembership(user_id=user.id, organization_id=org.id, role="manager")
    connection = WhatsAppConnection(
        organization_id=org.id, store_id=store.id, phone_number_id="pn", business_account_id="waba",
        access_token_encrypted="x", verify_token="v", status="connected",
    )
    session.add_all([membership, connection])
    session.flush()
    session.commit()
    yield SimpleNamespace(session=session, org=org, store=store, user=user, membership=membership,
                          connection=connection)
    session.close()
    engine.dispose()


def _meta_template(ctx, body="Hola {{1}}, recibimos tu pedido {{2}} por {{3}}.", status="approved"):
    template = WhatsAppMessageTemplate(
        organization_id=ctx.org.id, whatsapp_connection_id=ctx.connection.id,
        provider_template_name="diaglob_pedido_recibido", language_code="es", category="UTILITY",
        status=status, components={"items": [{"type": "BODY", "text": body}]},
    )
    ctx.session.add(template)
    ctx.session.commit()
    return template


def _create(ctx, model_id="order_confirmation_flow", **setup):
    return create_flow_from_model(
        ctx.session, organization_id=ctx.org.id, store_id=ctx.store.id, user_id=ctx.user.id,
        model_id=model_id, setup=FlowTemplateSetup(**setup) if setup else None,
    )


def _message_config(ctx, flow_id):
    flow = ctx.session.get(AutomationFlow, flow_id)
    from app.models import AutomationFlowVersion
    graph = ctx.session.get(AutomationFlowVersion, flow.current_version_id).graph
    return next(n for n in graph["nodes"] if n["id"] == "message")["config"]


def test_binds_approved_template_with_suggested_variables(ctx):
    template = _meta_template(ctx)
    result = _create(ctx, whatsapp_template_id=template.id)
    config = _message_config(ctx, result["flow"]["id"])
    assert config["whatsapp_template_id"] == template.id
    assert config["message_mode"] == "auto"
    assert config["template_variables"] == {"body": ["customer.name", "order.number", "order.total_display"]}
    assert config["template_provider_name"] == "diaglob_pedido_recibido"
    assert result["flow"]["status"] == "draft"
    assert result["whatsapp_template_bound"] is True and result["activated"] is False


def test_can_publish_and_activate_in_one_step(ctx):
    template = _meta_template(ctx)
    result = _create(ctx, whatsapp_template_id=template.id, activate=True, message_mode="template",
                     name="Confirmación COD")
    flow = ctx.session.get(AutomationFlow, result["flow"]["id"])
    assert flow.status == "active" and flow.active_version_id == flow.current_version_id
    assert flow.name == "Confirmación COD"
    assert result["activated"] is True and result["next_step"] == "monitor_runs"
    assert _message_config(ctx, flow.id)["message_mode"] == "template"


def test_without_setup_keeps_backward_compatible_draft(ctx):
    result = _create(ctx)
    assert result["flow"]["status"] == "draft"
    assert "whatsapp_template_id" not in _message_config(ctx, result["flow"]["id"])


@pytest.mark.parametrize("setup,body,status,code", [
    ({}, "Hola {{1}}", "pending", "WHATSAPP_TEMPLATE_NOT_APPROVED"),
    ({}, "Hola {{1}} {{2}}", "approved", "TEMPLATE_PARAMETER_COUNT_MISMATCH"),
    ({"template_variables": {"body": ["customer.email", "order.number", "order.total"]}},
     "Hola {{1}} {{2}} {{3}}", "approved", "TEMPLATE_VARIABLES_UNSUPPORTED"),
    ({"template_variables": {"body": "customer.name"}}, "Hola {{1}}", "approved", "TEMPLATE_VARIABLES_INVALID"),
    ({"message_mode": "free_form"}, "Hola {{1}} {{2}} {{3}}", "approved", "MESSAGE_MODE_INVALID"),
])
def test_rejects_invalid_setups_without_creating_a_flow(ctx, setup, body, status, code):
    template = _meta_template(ctx, body=body, status=status)
    with pytest.raises(FlowTemplateSetupError) as exc:
        _create(ctx, whatsapp_template_id=template.id, **setup)
    assert exc.value.code == code
    assert ctx.session.query(AutomationFlow).count() == 0


def test_requires_template_for_mode_and_whatsapp_models(ctx):
    with pytest.raises(FlowTemplateSetupError) as exc:
        _create(ctx, message_mode="template")
    assert exc.value.code == "WHATSAPP_TEMPLATE_REQUIRED"
    template = _meta_template(ctx)
    with pytest.raises(FlowTemplateSetupError) as exc:
        _create(ctx, model_id="operations_snapshot", whatsapp_template_id=template.id)
    assert exc.value.code == "TEMPLATE_HAS_NO_WHATSAPP_MESSAGE"


def test_template_must_belong_to_the_store_connection(ctx):
    other_store = Store(organization_id=ctx.org.id, name="Other", slug="other", country_code="CO",
                        currency="COP", timezone="America/Bogota", default_language="es")
    ctx.session.add(other_store)
    ctx.session.flush()
    other_connection = WhatsAppConnection(
        organization_id=ctx.org.id, store_id=other_store.id, phone_number_id="pn2",
        business_account_id="waba2", access_token_encrypted="x", verify_token="v2", status="connected",
    )
    ctx.session.add(other_connection)
    ctx.session.flush()
    foreign = WhatsAppMessageTemplate(
        organization_id=ctx.org.id, whatsapp_connection_id=other_connection.id,
        provider_template_name="foreign", language_code="es", status="approved",
        components={"items": [{"type": "BODY", "text": "Hola {{1}} {{2}} {{3}}"}]},
    )
    ctx.session.add(foreign)
    ctx.session.commit()
    with pytest.raises(FlowTemplateSetupError) as exc:
        _create(ctx, whatsapp_template_id=foreign.id)
    assert exc.value.code == "WHATSAPP_TEMPLATE_NOT_FOUND"


# ---------------------------------------------------------------------- API

def _client(ctx):
    app.dependency_overrides[get_current_user] = lambda: ctx.user
    app.dependency_overrides[get_current_membership] = lambda: ctx.membership
    app.dependency_overrides[get_db] = lambda: ctx.session
    return TestClient(app)


def test_api_lists_setup_metadata_and_creates_with_or_without_body(ctx):
    template = _meta_template(ctx)
    client = _client(ctx)
    base = f"/api/stores/{ctx.store.id}/automation-flow-templates"
    try:
        listed = client.get(base).json()["items"]
        order = next(item for item in listed if item["id"] == "order_confirmation_flow")
        assert order["trigger_mode"] == "automatic"
        assert order["whatsapp_setup"]["suggested_template"]["variables"][1] == "order.number"

        legacy = client.post(f"{base}/order_confirmation_flow")
        assert legacy.status_code == 200 and legacy.json()["flow"]["status"] == "draft"

        ready = client.post(f"{base}/order_confirmation_flow",
                            json={"whatsapp_template_id": template.id, "activate": True})
        assert ready.status_code == 200, ready.text
        assert ready.json()["activated"] is True
        assert ready.json()["flow"]["status"] == "active"

        bad = client.post(f"{base}/order_confirmation_flow", json={"whatsapp_template_id": 999999})
        assert bad.status_code == 404 and bad.json()["detail"] == {"code": "WHATSAPP_TEMPLATE_NOT_FOUND"}
    finally:
        app.dependency_overrides.clear()


def test_reusing_a_model_gets_a_unique_name_instead_of_failing(ctx):
    names = [_create(ctx)["flow"]["name"] for _ in range(3)]
    assert names == ["Confirmar pedido", "Confirmar pedido (2)", "Confirmar pedido (3)"]


def test_get_flow_template_exposes_trigger_mode():
    assert get_flow_template("shipment_dispatched_notice")["trigger_mode"] == "automatic"
