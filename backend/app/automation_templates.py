"""Automation template catalog.

Static templates for common dropshipping workflows.
Templates are predefined configurations that merchants can
instantiate into their own automations.

Templates use existing engine triggers and actions only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AutomationTemplate:
    id: str
    name: str
    description: str
    category: str
    recommended_for: str
    trigger: dict[str, Any]
    actions: list[dict[str, Any]]
    required_integrations: list[str] = field(default_factory=list)
    optional_integrations: list[str] = field(default_factory=list)
    supported_store_types: list[str] = field(default_factory=lambda: ["shopify", "dropi"])
    version: int = 1
    icon: str = "workflow"
    estimated_setup_minutes: int = 2


TEMPLATES: list[AutomationTemplate] = [
    AutomationTemplate(
        id="abandoned_cart_followup",
        name="Abandoned cart follow-up",
        description="Recover customers who started buying but did not finish. Send a WhatsApp reminder after a short delay.",
        category="Sales",
        recommended_for="Stores with active WhatsApp and Shopify",
        trigger={
            "type": "order.failed",
        },
        actions=[
            {
                "type": "send_whatsapp_message",
                "delay_seconds": 3600,
                "message": (
                    "Hola {{customer.name}}, vimos que tu compra no se completó. "
                    "¿Podemos ayudarte a finalizar tu pedido?"
                ),
            },
        ],
        required_integrations=["whatsapp", "shopify"],
        icon="cart",
        estimated_setup_minutes=2,
    ),

    AutomationTemplate(
        id="order_confirmation",
        name="Order confirmation",
        description="Confirm new orders automatically by WhatsApp. Let customers know their order was received.",
        category="Orders",
        recommended_for="All stores with WhatsApp",
        trigger={
            "type": "order.created",
        },
        actions=[
            {
                "type": "send_whatsapp_message",
                "delay_seconds": 0,
                "message": (
                    "Hola {{customer.name}}, tu pedido ha sido confirmado. "
                    "¡Gracias por tu compra!"
                ),
            },
        ],
        required_integrations=["whatsapp"],
        icon="check-circle",
        estimated_setup_minutes=1,
    ),

    AutomationTemplate(
        id="post_purchase_followup",
        name="Post-purchase follow-up",
        description="Follow up after delivery to ask for feedback or suggest related products.",
        category="Customer Retention",
        recommended_for="Stores wanting to increase repeat purchases",
        trigger={
            "type": "order.created",
        },
        actions=[
            {
                "type": "send_whatsapp_message",
                "delay_seconds": 172800,
                "message": (
                    "Hola {{customer.name}}, ¿qué tal tu experiencia con tu compra? "
                    "Si tienes alguna pregunta, estamos aquí para ayudarte."
                ),
            },
        ],
        required_integrations=["whatsapp"],
        icon="heart",
        estimated_setup_minutes=2,
    ),

    AutomationTemplate(
        id="new_customer_welcome",
        name="New customer welcome",
        description="Welcome new customers and let them know about your store.",
        category="Customer Retention",
        recommended_for="Stores wanting to improve first impression",
        trigger={
            "type": "conversation.created",
        },
        actions=[
            {
                "type": "send_whatsapp_message",
                "delay_seconds": 300,
                "message": (
                    "¡Bienvenido a nuestra tienda! "
                    "Si tienes alguna pregunta sobre nuestros productos, "
                    "no dudes en escribirnos."
                ),
            },
        ],
        required_integrations=["whatsapp"],
        icon="sparkles",
        estimated_setup_minutes=1,
    ),

    AutomationTemplate(
        id="customer_reactivation",
        name="Customer reactivation",
        description="Reconnect with customers who have not purchased recently. Send a special offer or reminder.",
        category="Customer Retention",
        recommended_for="Stores with repeat customers",
        trigger={
            "type": "message.received",
        },
        actions=[
            {
                "type": "send_whatsapp_message",
                "delay_seconds": 0,
                "message": (
                    "Hola {{customer.name}}, ¡te extrañamos! "
                    "Echa un vistazo a nuestras novedades."
                ),
            },
        ],
        required_integrations=["whatsapp"],
        icon="user-check",
        estimated_setup_minutes=2,
    ),

    AutomationTemplate(
        id="failed_order_recovery",
        name="Failed order recovery",
        description="Follow up when an order fails. Offer help to complete the purchase.",
        category="Operations",
        recommended_for="Stores with high checkout abandonment",
        trigger={
            "type": "order.failed",
        },
        actions=[
            {
                "type": "send_whatsapp_message",
                "delay_seconds": 1800,
                "message": (
                    "Hola {{customer.name}}, hubo un problema con tu pedido. "
                    "¿Podemos ayudarte a completarlo?"
                ),
            },
        ],
        required_integrations=["whatsapp"],
        icon="alert-triangle",
        estimated_setup_minutes=1,
    ),

    AutomationTemplate(
        id="high_value_followup",
        name="High-value customer follow-up",
        description="Give VIP treatment to customers with large orders. Thank them personally.",
        category="Customer Retention",
        recommended_for="Stores with high-value orders",
        trigger={
            "type": "order.created",
        },
        actions=[
            {
                "type": "send_whatsapp_message",
                "delay_seconds": 86400,
                "message": (
                    "Hola {{customer.name}}, ¡gracias por tu compra! "
                    "Valoramos mucho tu confianza en nosotros."
                ),
            },
        ],
        required_integrations=["whatsapp"],
        icon="star",
        estimated_setup_minutes=2,
    ),

    AutomationTemplate(
        id="order_status_update",
        name="Order status update",
        description="Notify customers when their order status changes.",
        category="Orders",
        recommended_for="All stores",
        trigger={
            "type": "order.created",
        },
        actions=[
            {
                "type": "send_whatsapp_message",
                "delay_seconds": 0,
                "message": (
                    "Hola {{customer.name}}, tu pedido está siendo procesado. "
                    "Te notificaremos cuando sea enviado."
                ),
            },
        ],
        required_integrations=["whatsapp"],
        icon="truck",
        estimated_setup_minutes=1,
    ),
]


def get_all_templates() -> list[dict]:
    """Return all templates as dicts."""
    return [_template_to_dict(t) for t in TEMPLATES]


def get_template_by_id(template_id: str) -> dict | None:
    """Return a single template by ID."""
    for t in TEMPLATES:
        if t.id == template_id:
            return _template_to_dict(t)
    return None


def get_templates_by_category(category: str) -> list[dict]:
    """Return templates filtered by category."""
    return [_template_to_dict(t) for t in TEMPLATES if t.category == category]


def get_categories() -> list[str]:
    """Return unique categories."""
    return sorted(set(t.category for t in TEMPLATES))


def validate_template_availability(
    template_id: str,
    connected_integrations: set[str],
) -> dict:
    """Check if a template can be used with current integrations.

    Returns dict with:
      - available: bool
      - missing: list of missing integrations
      - status: "ready" | "needs_configuration" | "integration_required"
    """
    template = None
    for t in TEMPLATES:
        if t.id == template_id:
            template = t
            break

    if template is None:
        return {"available": False, "missing": [], "status": "unsupported"}

    missing = [
        integ
        for integ in template.required_integrations
        if integ not in connected_integrations
    ]

    if not missing:
        status = "ready"
    elif len(missing) <= len(template.required_integrations):
        status = "integration_required"
    else:
        status = "needs_configuration"

    return {
        "available": len(missing) == 0,
        "missing": missing,
        "status": status,
    }


def _template_to_dict(t: AutomationTemplate) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "category": t.category,
        "recommended_for": t.recommended_for,
        "trigger": t.trigger,
        "actions": t.actions,
        "required_integrations": t.required_integrations,
        "optional_integrations": t.optional_integrations,
        "supported_store_types": t.supported_store_types,
        "version": t.version,
        "icon": t.icon,
        "estimated_setup_minutes": t.estimated_setup_minutes,
    }


def template_to_automation_data(template_id: str, store_id: int) -> dict | None:
    """Convert a template to automation creation data.

    Returns dict ready for create_legacy_automation or None if not found.
    """
    template = None
    for t in TEMPLATES:
        if t.id == template_id:
            template = t
            break

    if template is None:
        return None

    return {
        "name": template.name,
        "description": template.description,
        "trigger_type": template.trigger.get("type", "manual"),
        "conditions_json": [],
        "actions_json": template.actions,
        "active": False,
        "template_id": template.id,
        "template_version": template.version,
    }
