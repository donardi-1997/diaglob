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


def _wa_setup(name: str, category: str, body: str, variables: list[str]) -> dict:
    """Suggested Meta template for the model's message node.

    `body` uses Meta's positional {{n}} parameters and `variables[n-1]` is the
    Diaglob value suggested for each one. Utility templates are for
    transactional order/shipping updates; marketing ones need opt-in.
    """
    return {
        "node_id": "message",
        "suggested_template": {
            "name": name,
            "category": category,
            "language": "es",
            "body": body,
            "variables": variables,
        },
    }


FLOW_TEMPLATES = [
    {
        "id": "voice_order_confirmation",
        "name": "Confirmar COD por llamada + fulfillment",
        "description": "Detecta pedidos contraentrega, confirma por llamada IA y encola el pedido confirmado para fulfillment.",
        "category": "Orders",
        "recommended_role": "sales",
        "required_integrations": ["voice", "shopify", "cj_auto_fulfillment"],
        "icon": "phone-call",
        "estimated_setup_minutes": 2,
        "graph": _call_confirmation_flow(),
    },
    {
        "id": "order_confirmation_flow",
        "name": "Confirmar pedido",
        "description": "Confirma por WhatsApp cada pedido nuevo con su número y total.",
        "category": "Orders",
        "recommended_role": "sales",
        "required_integrations": ["whatsapp"],
        "icon": "check-circle",
        "estimated_setup_minutes": 2,
        "graph": _message_flow(
            "order_created",
            "Hola {{customer.name}}, recibimos tu pedido {{order.number}} por {{order.total_display}}. "
            "Te avisaremos cuando sea despachado.",
        ),
        "whatsapp_setup": _wa_setup(
            "diaglob_pedido_recibido", "UTILITY",
            "Hola {{1}}, recibimos tu pedido {{2}} por {{3}}. Te avisaremos cuando sea despachado.",
            ["customer.name", "order.number", "order.total_display"],
        ),
    },
    {
        "id": "order_cancelled_notice",
        "name": "Avisar pedido cancelado",
        "description": "Informa al cliente cuando su pedido se cancela, para evitar dudas y reclamos.",
        "category": "Orders",
        "recommended_role": "support",
        "required_integrations": ["whatsapp"],
        "icon": "alert-triangle",
        "estimated_setup_minutes": 2,
        "graph": _message_flow(
            "order_cancelled",
            "Hola {{customer.name}}, tu pedido {{order.number}} fue cancelado. "
            "Si no lo solicitaste o tienes dudas, responde este mensaje y te ayudamos.",
        ),
        "whatsapp_setup": _wa_setup(
            "diaglob_pedido_cancelado", "UTILITY",
            "Hola {{1}}, tu pedido {{2}} fue cancelado. Si no lo solicitaste o tienes dudas, "
            "responde este mensaje y te ayudamos.",
            ["customer.name", "order.number"],
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
            "Hola {{customer.name}}, vimos que tu compra en {{store.name}} no se completó. "
            "¿Podemos ayudarte a terminarla?",
            wait=(30, "minutes"),
        ),
        "whatsapp_setup": _wa_setup(
            "diaglob_compra_incompleta", "MARKETING",
            "Hola {{1}}, vimos que tu compra en {{2}} no se completó. ¿Podemos ayudarte a terminarla?",
            ["customer.name", "store.name"],
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
            "Hola {{customer.name}}, gracias por confiar en {{store.name}}. Si necesitas ayuda, estamos aquí.",
            wait=(5, "minutes"),
        ),
        "whatsapp_setup": _wa_setup(
            "diaglob_bienvenida", "MARKETING",
            "Hola {{1}}, gracias por confiar en {{2}}. Si necesitas ayuda, estamos aquí.",
            ["customer.name", "store.name"],
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
            message="Hola {{customer.name}}, gracias por seguir eligiendo {{store.name}}. "
            "Queremos darte una atención prioritaria.",
        ),
        "whatsapp_setup": _wa_setup(
            "diaglob_seguimiento_vip", "MARKETING",
            "Hola {{1}}, gracias por seguir eligiendo {{2}}. Queremos darte una atención prioritaria.",
            ["customer.name", "store.name"],
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
            message="Hola {{customer.name}}, hace tiempo no sabemos de ti en {{store.name}}. "
            "¿Podemos ayudarte con algo?",
        ),
        "whatsapp_setup": _wa_setup(
            "diaglob_reactivacion", "MARKETING",
            "Hola {{1}}, hace tiempo no sabemos de ti en {{2}}. ¿Podemos ayudarte con algo?",
            ["customer.name", "store.name"],
        ),
    },
    {
        "id": "shipment_dispatched_notice",
        "name": "Avisar pedido despachado",
        "description": "Envía la guía y la transportadora en cuanto se crea el envío.",
        "category": "Logistics",
        "recommended_role": "logistics",
        "required_integrations": ["whatsapp"],
        "icon": "truck",
        "estimated_setup_minutes": 2,
        "graph": _message_flow(
            "shipment_created",
            "Hola {{customer.name}}, tu pedido fue despachado con {{shipment.carrier}}. "
            "Tu número de guía es {{shipment.tracking_number}}.",
        ),
        "whatsapp_setup": _wa_setup(
            "diaglob_pedido_despachado", "UTILITY",
            "Hola {{1}}, tu pedido fue despachado con {{2}}. Tu número de guía es {{3}}.",
            ["customer.name", "shipment.carrier", "shipment.tracking_number"],
        ),
    },
    {
        "id": "shipment_out_for_delivery_notice",
        "name": "Avisar pedido en reparto",
        "description": "Avisa automáticamente cuando la transportadora marca el envío en ruta de entrega.",
        "category": "Logistics",
        "recommended_role": "logistics",
        "required_integrations": ["whatsapp"],
        "icon": "truck",
        "estimated_setup_minutes": 1,
        "graph": _message_flow(
            "shipment_out_for_delivery",
            "Hola {{customer.name}}, tu envío {{shipment.tracking_number}} con {{shipment.carrier}} ya está en reparto. Te recomendamos estar atento a la entrega.",
        ),
        "whatsapp_setup": _wa_setup(
            "diaglob_pedido_en_reparto", "UTILITY",
            "Hola {{1}}, tu envío {{2}} con {{3}} ya está en reparto. Te recomendamos estar atento a la entrega.",
            ["customer.name", "shipment.tracking_number", "shipment.carrier"],
        ),
    },
    {
        "id": "shipment_delayed_notice",
        "name": "Avisar envío retrasado",
        "description": "Avisa con anticipación cuando la transportadora reporta un retraso.",
        "category": "Logistics",
        "recommended_role": "logistics",
        "required_integrations": ["whatsapp"],
        "icon": "truck",
        "estimated_setup_minutes": 2,
        "graph": _message_flow(
            "shipment_delayed",
            "Hola {{customer.name}}, tu envío {{shipment.tracking_number}} con {{shipment.carrier}} "
            "presenta un retraso. Lo estamos siguiendo y te avisaremos cualquier novedad.",
        ),
        "whatsapp_setup": _wa_setup(
            "diaglob_envio_retrasado", "UTILITY",
            "Hola {{1}}, tu envío {{2}} con {{3}} presenta un retraso. Lo estamos siguiendo y te "
            "avisaremos cualquier novedad.",
            ["customer.name", "shipment.tracking_number", "shipment.carrier"],
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
            "Hola {{customer.name}}, detectamos una novedad con tu envío {{shipment.tracking_number}} de {{shipment.carrier}}. Estamos revisándola y te mantendremos informado.",
        ),
        "whatsapp_setup": _wa_setup(
            "diaglob_novedad_entrega", "UTILITY",
            "Hola {{1}}, detectamos una novedad con tu envío {{2}} de {{3}}. Estamos revisándola y "
            "te mantendremos informado.",
            ["customer.name", "shipment.tracking_number", "shipment.carrier"],
        ),
    },
    {
        "id": "shipment_delivered_followup",
        "name": "Seguimiento después de entrega",
        "description": "Contacta al cliente cuando la transportadora confirma la entrega.",
        "category": "Post-sales",
        "recommended_role": "post_sales",
        "required_integrations": ["whatsapp"],
        "icon": "check-circle",
        "estimated_setup_minutes": 1,
        "graph": _message_flow(
            "shipment_delivered",
            "Hola {{customer.name}}, {{shipment.carrier}} reportó como entregado tu envío {{shipment.tracking_number}}. ¿Recibiste todo correctamente?",
        ),
        "whatsapp_setup": _wa_setup(
            "diaglob_pedido_entregado", "UTILITY",
            "Hola {{1}}, {{2}} reportó como entregado tu envío {{3}}. ¿Recibiste todo correctamente?",
            ["customer.name", "shipment.carrier", "shipment.tracking_number"],
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
            "Hola {{customer.name}}, registramos tu solicitud de postventa en {{store.name}}. "
            "Nuestro equipo revisará el caso y te mantendrá informado.",
        ),
        "whatsapp_setup": _wa_setup(
            "diaglob_caso_postventa", "UTILITY",
            "Hola {{1}}, registramos tu solicitud de postventa en {{2}}. Nuestro equipo revisará el "
            "caso y te mantendrá informado.",
            ["customer.name", "store.name"],
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
            "Hola {{customer.name}}, ¿cómo fue tu experiencia con tu pedido de {{store.name}}? "
            "Tu opinión nos ayuda a mejorar.",
            wait=(7, "days"),
        ),
        "whatsapp_setup": _wa_setup(
            "diaglob_resena_entrega", "MARKETING",
            "Hola {{1}}, ¿cómo fue tu experiencia con tu pedido de {{2}}? Tu opinión nos ayuda a mejorar.",
            ["customer.name", "store.name"],
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


def _trigger_type(template: dict) -> str | None:
    for node in template["graph"].get("nodes", []):
        if node.get("type") == "trigger":
            return (node.get("config") or {}).get("trigger_type")
    return None


def _with_trigger_mode(template: dict) -> dict:
    """`automatic` only when a real domain event dispatches the trigger.

    Derived from the event bridge so the catalog never promises automation
    for triggers that today only run manually or from a campaign.
    """
    from .automation_flow_events import EVENT_TO_FLOW_TRIGGER

    trigger = _trigger_type(template)
    template["trigger_type"] = trigger
    template["trigger_mode"] = (
        "automatic" if trigger in set(EVENT_TO_FLOW_TRIGGER.values()) else "manual"
    )
    return template


def get_flow_templates(category: str | None = None) -> list[dict]:
    templates = FLOW_TEMPLATES
    if category:
        templates = [
            item for item in templates
            if item["category"].lower() == category.strip().lower()
        ]
    return [_with_trigger_mode(item) for item in deepcopy(templates)]


def get_flow_template(template_id: str) -> dict | None:
    for item in FLOW_TEMPLATES:
        if item["id"] == template_id:
            return _with_trigger_mode(deepcopy(item))
    return None


def get_flow_template_categories() -> list[str]:
    return sorted({item["category"] for item in FLOW_TEMPLATES})
