"""LLM-facing tool catalog.

This module exposes capabilities, not authority. Every tool is filtered through
ActionPolicyService before it becomes visible to or executable by an agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from ..models import OrganizationMembership
from .action_policy import evaluate_action


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    title: str
    description: str
    category: str
    action: str
    input_schema: dict[str, Any]

    def as_dict(self, *, authorization: dict | None = None) -> dict:
        payload = {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "action": self.action,
            "input_schema": self.input_schema,
        }
        if authorization is not None:
            payload["authorization"] = authorization
        return payload


def _object_schema(properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


TOOLS: dict[str, ToolDefinition] = {
    "orders.list": ToolDefinition(
        "orders.list",
        "Listar pedidos",
        "Lista pedidos de la tienda actual y permite filtrar por estado.",
        "orders",
        "orders.list",
        _object_schema({
            "status": {"type": ["string", "null"]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
        }),
    ),
    "orders.get": ToolDefinition(
        "orders.get",
        "Ver pedido",
        "Consulta el detalle de un pedido de la tienda actual.",
        "orders",
        "orders.get",
        _object_schema(
            {"order_id": {"type": "integer", "minimum": 1}},
            ["order_id"],
        ),
    ),
    "products.list": ToolDefinition(
        "products.list",
        "Buscar productos",
        "Lista o busca productos y variantes en la tienda actual.",
        "products",
        "products.list",
        _object_schema({
            "query": {"type": ["string", "null"]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
        }),
    ),
    "customers.search": ToolDefinition(
        "customers.search",
        "Buscar clientes",
        "Busca clientes dentro de la organización y tienda actual.",
        "customers",
        "customers.search",
        _object_schema({
            "query": {"type": ["string", "null"]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
        }),
    ),
    "tracking.get": ToolDefinition(
        "tracking.get",
        "Consultar tracking",
        "Consulta el shipment y tracking asociado a una orden de proveedor.",
        "tracking",
        "tracking.get",
        _object_schema(
            {"supplier_order_id": {"type": "integer", "minimum": 1}},
            ["supplier_order_id"],
        ),
    ),
    "suppliers.cj.search": ToolDefinition(
        "suppliers.cj.search",
        "Buscar en CJ",
        "Busca productos en el catálogo de CJ Dropshipping.",
        "suppliers",
        "suppliers.cj.search",
        _object_schema({
            "query": {"type": ["string", "null"]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            "page": {"type": "integer", "minimum": 1},
        }),
    ),
    "suppliers.cj.quote": ToolDefinition(
        "suppliers.cj.quote",
        "Cotizar envío CJ",
        "Cotiza opciones de envío de CJ para variantes y destino.",
        "suppliers",
        "suppliers.cj.quote",
        _object_schema({
            "start_country_code": {"type": "string", "minLength": 2, "maxLength": 2},
            "end_country_code": {"type": "string", "minLength": 2, "maxLength": 2},
            "zip_code": {"type": ["string", "null"]},
            "items": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "variant_id": {"type": "string", "minLength": 1},
                        "quantity": {"type": "integer", "minimum": 1, "maximum": 1000},
                    },
                    "required": ["variant_id", "quantity"],
                    "additionalProperties": False,
                },
            },
        }, ["start_country_code", "end_country_code", "items"]),
    ),
    "suppliers.cj.map_variant": ToolDefinition(
        "suppliers.cj.map_variant",
        "Vincular variante CJ",
        "Vincula una variante local/Shopify con una variante de CJ.",
        "suppliers",
        "suppliers.cj.map_variant",
        _object_schema({
            "product_variant_id": {"type": "integer", "minimum": 1},
            "external_product_id": {"type": "string"},
            "external_variant_id": {"type": "string"},
            "external_sku": {"type": ["string", "null"]},
        }, ["product_variant_id", "external_product_id", "external_variant_id"]),
    ),
    "fulfillment.retry": ToolDefinition(
        "fulfillment.retry",
        "Reintentar fulfillment",
        "Reintenta fulfillment automático; puede crear una orden real en CJ.",
        "orders",
        "fulfillment.retry",
        _object_schema({}),
    ),
    "automations.list": ToolDefinition(
        "automations.list",
        "Listar automatizaciones",
        "Lista automatizaciones visuales de la tienda.",
        "automations",
        "automations.list",
        _object_schema({}),
    ),
    "automations.create": ToolDefinition(
        "automations.create",
        "Crear automatización",
        "Crea un borrador de automatización visual.",
        "automations",
        "automations.create",
        _object_schema({
            "name": {"type": "string"},
            "graph": {"type": "object"},
        }, ["name", "graph"]),
    ),
    "automations.update": ToolDefinition(
        "automations.update",
        "Modificar automatización",
        "Modifica el borrador de una automatización visual.",
        "automations",
        "automations.update",
        _object_schema({
            "flow_id": {"type": "integer", "minimum": 1},
            "name": {"type": ["string", "null"]},
            "description": {"type": ["string", "null"]},
            "graph": {"type": ["object", "null"]},
        }, ["flow_id"]),
    ),
    "automations.publish": ToolDefinition(
        "automations.publish",
        "Publicar automatización",
        "Publica la versión actual antes de activarla.",
        "automations",
        "automations.publish",
        _object_schema(
            {"flow_id": {"type": "integer", "minimum": 1}},
            ["flow_id"],
        ),
    ),
    "automations.activate": ToolDefinition(
        "automations.activate",
        "Activar automatización",
        "Activa una versión de automatización para ejecución real.",
        "automations",
        "automations.activate",
        _object_schema(
            {"flow_id": {"type": "integer", "minimum": 1}},
            ["flow_id"],
        ),
    ),
    "automations.pause": ToolDefinition(
        "automations.pause",
        "Pausar automatización",
        "Pausa una automatización activa.",
        "automations",
        "automations.pause",
        _object_schema(
            {"flow_id": {"type": "integer", "minimum": 1}},
            ["flow_id"],
        ),
    ),
    "automations.test": ToolDefinition(
        "automations.test",
        "Probar automatización",
        "Ejecuta una prueba controlada de una automatización.",
        "automations",
        "automations.test",
        _object_schema(
            {"flow_id": {"type": "integer", "minimum": 1}},
            ["flow_id"],
        ),
    ),
    "analytics.summary": ToolDefinition(
        "analytics.summary",
        "Resumen analítico",
        "Consulta métricas operativas de la tienda.",
        "analytics",
        "analytics.summary",
        _object_schema({}),
    ),
}


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return False


def _validate_value(value: Any, schema: dict, path: str) -> list[str]:
    errors: list[str] = []
    expected = schema.get("type")
    expected_types = expected if isinstance(expected, list) else [expected]
    expected_types = [item for item in expected_types if item]

    if expected_types and not any(
        _matches_type(value, expected_type)
        for expected_type in expected_types
    ):
        return [f"{path}: invalid type"]

    if value is None:
        return errors

    if isinstance(value, str):
        minimum = schema.get("minLength")
        maximum = schema.get("maxLength")
        if minimum is not None and len(value) < int(minimum):
            errors.append(f"{path}: too short")
        if maximum is not None and len(value) > int(maximum):
            errors.append(f"{path}: too long")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and value < minimum:
            errors.append(f"{path}: below minimum")
        if maximum is not None and value > maximum:
            errors.append(f"{path}: above maximum")

    if isinstance(value, list):
        minimum = schema.get("minItems")
        maximum = schema.get("maxItems")
        if minimum is not None and len(value) < int(minimum):
            errors.append(f"{path}: too few items")
        if maximum is not None and len(value) > int(maximum):
            errors.append(f"{path}: too many items")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(
                    _validate_value(item, item_schema, f"{path}[{index}]")
                )

    if isinstance(value, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict):
            required = set(schema.get("required") or [])
            for key in required:
                if key not in value:
                    errors.append(f"{path}.{key}: required")
            if schema.get("additionalProperties") is False:
                unknown = sorted(set(value) - set(properties))
                for key in unknown:
                    errors.append(f"{path}.{key}: unknown field")
            for key, child_schema in properties.items():
                if key in value and isinstance(child_schema, dict):
                    errors.extend(
                        _validate_value(
                            value[key],
                            child_schema,
                            f"{path}.{key}",
                        )
                    )

    return errors


def validate_tool_arguments(
    tool: ToolDefinition,
    arguments: dict,
) -> list[str]:
    if not isinstance(arguments, dict):
        return ["arguments: object required"]
    return _validate_value(arguments, tool.input_schema, "arguments")


def get_tool(name: str) -> ToolDefinition | None:
    return TOOLS.get(name)


def list_authorized_tools(
    db: Session,
    membership: OrganizationMembership,
    *,
    store_id: int | None,
    include_denied: bool = False,
) -> list[dict]:
    items: list[dict] = []
    for tool in sorted(TOOLS.values(), key=lambda item: (item.category, item.name)):
        decision = evaluate_action(
            db,
            membership,
            tool.action,
            store_id=store_id,
        )
        if decision.allowed or include_denied:
            items.append(
                tool.as_dict(authorization=decision.as_dict())
            )
    return items


__all__ = [
    "TOOLS",
    "ToolDefinition",
    "get_tool",
    "list_authorized_tools",
    "validate_tool_arguments",
]
