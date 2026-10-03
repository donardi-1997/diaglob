from app.services.bedrock_agent_chat import (
    build_bedrock_tool_config,
    build_system_prompt,
    provider_tool_name,
)


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
