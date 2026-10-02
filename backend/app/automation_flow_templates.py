"""Durable one-click templates for the visual Flow Builder."""
from __future__ import annotations

from copy import deepcopy


def _node(node_id: str, node_type: str, x: int, y: int, **config):
    return {
        "id": node_id,
        "type": node_type,
        "config": config,
        "position": {"x": x, "y": y},
    }


def _message_flow(trigger_type: str, message: str, *, wait: tuple[int, str] | None = None):
    nodes = [_node("trigger", "trigger", 260, 60, trigger_type=trigger_type)]
    edges = []
    previous = "trigger"
    if wait:
        value, unit = wait
        nodes.append(_node("wait", "wait", 260, 190, value=value, unit=unit))
        edges.append({"source": previous, "target": "wait"})
        previous = "wait"
    nodes.append(
        _node(
            "message",
            "message",
            260,
            330,
            message_mode="auto",
            message_template=message,
        )
    )
    nodes.append(_node("end", "end", 260, 480, label="Completado"))
    edges.extend([
        {"source": previous, "target": "message"},
        {"source": "message", "target": "end"},
    ])
    return {"nodes": nodes, "edges": edges}


def _conditional_message_flow(
    trigger_type: str,
    *,
    field: str,
    operator: str,
    value,
    message: str,
):
    return {
        "nodes": [
            _node("trigger", "trigger", 260, 60, trigger_type=trigger_type),
            _node(
                "condition",
                "condition",
                260,
                190,
                field=field,
                operator=operator,
                value=value,
            ),
            _node(
                "message",
                "message",
                120,
                340,
                message_mode="auto",
                message_template=message,
            ),
            _node("end_yes", "end", 120, 500, label="Mensaje enviado"),
            _node("end_no", "end", 410, 340, label="No aplica"),
        ],
        "edges": [
            {"source": "trigger", "target": "condition"},
            {"source": "condition", "target": "message", "label": "true"},
            {"source": "condition", "target": "end_no", "label": "false"},
            {"source": "message", "target": "end_yes"},
        ],
    }


def _call_confirmation_flow():
    return {
        "nodes": [
            _node("trigger", "trigger", 320, 40, trigger_type="order_created"),
            _node(
                "is_cod",
                "condition",
                320,
                170,
                field="order.is_cod",
                operator="is_true",
                value=True,
            ),
            _node(
                "call",
                "call",
                180,
                330,
                call_prompt=(
                    "Hola {{customer.name}}, te llamamos de {{store.name}} para confirmar "
                    "tu pedido #{{order.number}} por {{order.total}} {{order.currency}}. "
                    "El pedido incluye {{order.items_summary}} y la entrega está registrada "
                    "para {{order.shipping.city}}, {{order.shipping.province}}. "
                    "Por favor confirma claramente si deseas recibirlo."
                ),
                call_language="es",
                call_purpose="order_confirmation",
                timeout_minutes=5,
            ),
            _node(
                "fulfill",
                "tool",
                20,
                540,
                tool_name="fulfillment.enqueue_trigger_order",
                arguments={},
            ),
            _node("confirmed", "end", 20, 720, label="Confirmado y enviado a fulfillment"),
            _node("rejected", "end", 180, 720, label="Pedido rechazado"),
            _node("no_answer", "end", 350, 720, label="No contestó"),
            _node("failed", "end", 510, 720, label="Llamada fallida"),
            _node("not_cod", "end", 520, 330, label="No requiere confirmación COD"),
        ],
        "edges": [
            {"source": "trigger", "target": "is_cod"},
            {"source": "is_cod", "target": "call", "label": "true"},
            {"source": "is_cod", "target": "not_cod", "label": "false"},
            {"source": "call", "target": "fulfill", "label": "confirmed"},
            {"source": "call", "target": "rejected", "label": "rejected"},
            {"source": "call", "target": "no_answer", "label": "no_answer"},
            {"source": "call", "target": "failed", "label": "failed"},
            {"source": "fulfill", "target": "confirmed"},
        ],
    }


FLOW_TEMPLATES = [
    {
        "id": "voice_order_confirmation",
        "name": "Confirmar pedido por llamada",
        "description": "Llama al cliente con IA y separa confirmado, rechazado, sin respuesta o fallo.",
        "category": "Orders",
        "recommended_role": "sales",
        "required_integrations": ["voice"],
        "icon": "phone-call",
        "estimated_setup_minutes": 2,
        "graph": _call_confirmation_flow(),
    },
    {
        "id": "order_confirmation_flow",
        "name": "Confirmar pedido",
        "description": "Confirma por WhatsApp un pedido nuevo usando el motor durable de flujos.",
        "category": "Orders",
        "recommended_role": "sales",
        "required_integrations": ["whatsapp"],
        "icon": "check-circle",
        "estimated_setup_minutes": 1,
        "graph": _message_flow(
            "order_created",
            "Hola {{customer.name}}, recibimos tu pedido. Te mantendremos al tanto de su avance.",
        ),
    },
    {
        "id": "failed_order_recovery_flow",
        "name": "Recuperar pedido fallido",
        "description": "Espera 30 minutos y contacta al cliente cuando una compra no se completa.",
        "category": "Sales",
        "recommended_role": "sales",
        "required_integrations": ["whatsapp"],
        "icon": "cart",
        "estimated_setup_minutes": 2,
        "graph": _message_flow(
            "failed_order",
            "Hola {{customer.name}}, vimos que tu compra no se completó. ¿Podemos ayudarte?",
            wait=(30, "minutes"),
        ),
    },
    {
        "id": "new_customer_welcome_flow",
        "name": "Bienvenida a cliente nuevo",
        "description": "Da una bienvenida breve después del primer alta del cliente.",
        "category": "Retention",
        "recommended_role": "retention",
        "required_integrations": ["whatsapp"],
        "icon": "sparkles",
        "estimated_setup_minutes": 2,
        "graph": _message_flow(
            "customer_created",
            "Hola {{customer.name}}, gracias por confiar en nosotros. Si necesitas ayuda, estamos aquí.",
            wait=(5, "minutes"),
        ),
    },
    {
        "id": "vip_followup_flow",
        "name": "Seguimiento VIP",
        "description": "Contacta únicamente a clientes clasificados como VIP.",
        "category": "Retention",
        "recommended_role": "retention",
        "required_integrations": ["whatsapp"],
        "icon": "star",
        "estimated_setup_minutes": 2,
        "graph": _conditional_message_flow(
            "customer_segment",
            field="customer.segment",
            operator="equals",
            value="vip",
            message="Hola {{customer.name}}, gracias por seguir eligiéndonos. Queremos darte una atención prioritaria.",
        ),
    },
    {
        "id": "customer_reactivation_flow",
        "name": "Reactivar cliente",
        "description": "Contacta a clientes que Customer Intelligence marca para seguimiento.",
        "category": "Retention",
        "recommended_role": "retention",
        "required_integrations": ["whatsapp"],
        "icon": "user-check",
        "estimated_setup_minutes": 2,
        "graph": _conditional_message_flow(
            "customer_segment",
            field="customer.needs_followup",
            operator="is_true",
            value=True,
            message="Hola {{customer.name}}, hace tiempo no sabemos de ti. ¿Podemos ayudarte con algo?",
        ),
    },
    {
        "id": "delivery_exception_followup",
        "name": "Novedad de entrega",
        "description": "Avisa al cliente cuando el tracking normalizado reporta una excepción.",
        "category": "Post-sales",
        "recommended_role": "logistics",
        "required_integrations": ["whatsapp"],
        "icon": "truck",
        "estimated_setup_minutes": 2,
        "graph": _message_flow(
            "shipment_delivery_exception",
            "Hola {{customer.name}}, detectamos una novedad con la entrega de tu pedido. Estamos revisándola y te mantendremos informado.",
        ),
    },
    {
        "id": "post_sales_case_acknowledgement",
        "name": "Confirmar caso de postventa",
        "description": "Confirma al cliente que su garantía, devolución o novedad quedó registrada.",
        "category": "Post-sales",
        "recommended_role": "post_sales",
        "required_integrations": ["whatsapp"],
        "icon": "shield",
        "estimated_setup_minutes": 1,
        "graph": _message_flow(
            "post_sales_case_created",
            "Hola {{customer.name}}, registramos tu solicitud de postventa. Nuestro equipo revisará el caso y te mantendrá informado.",
        ),
    },
    {
        "id": "delivery_review_followup",
        "name": "Reseña después de entrega",
        "description": "Espera siete días después de la entrega y solicita feedback sin inventar incentivos.",
        "category": "Retention",
        "recommended_role": "retention",
        "required_integrations": ["whatsapp"],
        "icon": "heart",
        "estimated_setup_minutes": 2,
        "graph": _message_flow(
            "shipment_delivered",
            "Hola {{customer.name}}, ¿cómo fue tu experiencia con el pedido? Tu opinión nos ayuda a mejorar.",
            wait=(7, "days"),
        ),
    },
    {
        "id": "operations_snapshot",
        "name": "Snapshot operativo",
        "description": "Consulta un resumen analítico dentro de un flujo manual para diagnóstico.",
        "category": "Intelligence",
        "recommended_role": "analyst",
        "required_integrations": [],
        "icon": "workflow",
        "estimated_setup_minutes": 1,
        "graph": {
            "nodes": [
                _node("trigger", "trigger", 260, 60, trigger_type="manual"),
                _node(
                    "analytics",
                    "tool",
                    260,
                    230,
                    tool_name="analytics.summary",
                    arguments={},
                ),
                _node("end", "end", 260, 400, label="Analizado"),
            ],
            "edges": [
                {"source": "trigger", "target": "analytics"},
                {"source": "analytics", "target": "end"},
            ],
        },
    },
]


def get_flow_templates(category: str | None = None) -> list[dict]:
    templates = FLOW_TEMPLATES
    if category:
        templates = [
            item for item in templates
            if item["category"].lower() == category.strip().lower()
        ]
    return deepcopy(templates)


def get_flow_template(template_id: str) -> dict | None:
    for item in FLOW_TEMPLATES:
        if item["id"] == template_id:
            return deepcopy(item)
    return None


def get_flow_template_categories() -> list[str]:
    return sorted({item["category"] for item in FLOW_TEMPLATES})
