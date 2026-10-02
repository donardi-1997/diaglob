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
            "items": {"type": "array", "minItems": 1},
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
            "graph": {"type": "object"},
        }, ["flow_id", "graph"]),
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
]
