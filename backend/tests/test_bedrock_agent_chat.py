from app.services.bedrock_agent_chat import (
    build_bedrock_tool_config,
    build_system_prompt,
    provider_tool_name,
)


def test_converse_normalizes_tool_names_in_history_without_mutating_storage(monkeypatch):
    from copy import deepcopy
    from types import SimpleNamespace
    from app.services import bedrock_agent_chat as adapter
    messages = [
        {"role": "user", "content": [{"text": "Consulta productos y pedidos"}]},
        {"role": "assistant", "content": [{"toolUse": {
            "toolUseId": "call-1", "name": "products.list", "input": {},
        }}]},
        {"role": "user", "content": [{"toolResult": {
            "toolUseId": "call-1", "content": [{"json": {"items": []}}],
        }}]},
    ]
    original = deepcopy(messages)

    class Client:
        def converse(self, **kwargs):
            assert kwargs["messages"][1]["content"][0]["toolUse"]["name"] == "products_list"
            assert kwargs["messages"][2] == original[2]
            return {"output": {"message": {"role": "assistant", "content": [{"toolUse": {
                "toolUseId": "call-2", "name": "orders_list", "input": {},
            }}]}}}

    monkeypatch.setattr(adapter, "_client", lambda region: Client())
    monkeypatch.setattr(adapter, "get_settings", lambda: SimpleNamespace(
        agent_model_id="test-model", agent_model_region="us-east-2", agent_max_tokens=1200,
    ))
    result = adapter.converse(messages=messages, tools=[{"name": "orders.list"}], store_id=7)
    assert messages == original
    assert result["message"]["content"][0]["toolUse"]["name"] == "orders.list"


def test_bedrock_tool_names_are_provider_safe():
    assert provider_tool_name("automations.create") == "automations_create"
    assert provider_tool_name("suppliers.cj.quote") == "suppliers_cj_quote"


def test_bedrock_tool_schema_removes_nullable_union_and_extra_properties():
    config, reverse = build_bedrock_tool_config(
        [
            {
                "name": "orders.list",
                "description": "List orders",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "status": {"type": ["string", "null"]},
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 100,
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            }
        ]
    )

    assert config is not None
    spec = config["tools"][0]["toolSpec"]
    assert spec["name"] == "orders_list"
    assert reverse["orders_list"] == "orders.list"
    schema = spec["inputSchema"]["json"]
    assert set(schema) == {"type", "properties", "required"}
    assert schema["properties"]["status"]["type"] == "string"
    assert "additionalProperties" not in schema



def test_system_prompt_includes_safe_page_context_and_marks_it_untrusted():
    prompt = build_system_prompt(
        store_id=7,
        context={
            "page": "customers",
            "page_label": "Clientes",
            "entity_type": "customer",
            "entity_id": 42,
            "search_query": "ana",
            "context_source": "current_view",
            "page_text": "Cliente Ana · 3 pedidos",
            "secret_key": "must-not-be-forwarded",
        },
    )

    assert "Current UI page: customers" in prompt
    assert '"page_label": "Clientes"' in prompt
    assert '"entity_id": 42' in prompt
    assert "Cliente Ana · 3 pedidos" in prompt
    assert "untrusted reference data" in prompt
    assert "must-not-be-forwarded" not in prompt
