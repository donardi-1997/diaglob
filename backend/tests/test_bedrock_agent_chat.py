from app.services.bedrock_agent_chat import (
    build_bedrock_tool_config,
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
