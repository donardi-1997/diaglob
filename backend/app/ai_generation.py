import os

import boto3


AWS_REGION = os.getenv(
    "AWS_REGION",
    "us-east-2",
)

CHAT_MODEL_ID = os.getenv(
    "DIAGLOB_CHAT_MODEL_ID",
    "us.amazon.nova-2-lite-v1:0",
)


def get_bedrock_runtime():
    return boto3.client(
        "bedrock-runtime",
        region_name=AWS_REGION,
    )


def generate_grounded_answer(
    *,
    question: str,
    evidence: list[dict],
    agent_name: str,
    agent_role: str,
    store_name: str | None = None,
    country_code: str | None = None,
    currency: str | None = None,
    timezone: str | None = None,
    language: str | None = None,
    commerce_results: list[dict] | None = None,
):
    if not evidence and not commerce_results:
        if language == "en":
            return (
                "I couldn't find enough information "
                "in the assigned knowledge sources "
                "to answer safely."
            )

        return (
            "No encontré información suficiente "
            "en las fuentes de conocimiento "
            "asignadas para responder con seguridad."
        )

    context_blocks = []

    for index, result in enumerate(
        evidence,
        start=1,
    ):
        text = (
            result.get("text")
            or ""
        ).strip()

        if not text:
            continue

        context_blocks.append(
            f"[Fuente {index}]\n{text}"
        )

    context = "\n\n".join(
        context_blocks
    )

    commerce_blocks = []

    for product in (
        commerce_results
        or []
    ):
        commerce_blocks.append(
            (
                f"Producto: "
                f"{product.get('title', '')}"
            )
        )

        for variant in (
            product.get(
                "variants",
                [],
            )
        ):
            commerce_blocks.append(
                (
                    f"- Variante: "
                    f"{variant.get('title', '')} | "
                    f"Precio: "
                    f"{variant.get('price')} "
                    f"{variant.get('currency')} | "
                    f"Stock: "
                    f"{variant.get('inventory_quantity')} | "
                    f"Disponible: "
                    f"{variant.get('available')}"
                )
            )

    commerce_context = (
        "\n".join(
            commerce_blocks
        )
        if commerce_blocks
        else
        "No hay resultados comerciales relevantes."
    )

    market_lines = []

    if store_name:
        market_lines.append(
            f"Tienda: {store_name}"
        )

    if country_code:
        market_lines.append(
            f"País / mercado: {country_code}"
        )

    if currency:
        market_lines.append(
            f"Moneda: {currency}"
        )

    if timezone:
        market_lines.append(
            f"Zona horaria: {timezone}"
        )

    if language:
        market_lines.append(
            f"Idioma principal: {language}"
        )

    if market_lines:
        market_context = "\n".join(
            market_lines
        )
    else:
        market_context = (
            "No se proporcionó un mercado específico."
        )

    system_prompt = f"""
Eres {agent_name}, un agente IA de Diaglob.
Tu función es {agent_role}.

CONTEXTO COMERCIAL ACTUAL:
{market_context}

Reglas obligatorias:
- Responde únicamente usando la evidencia proporcionada.
- No inventes políticas, precios, inventario, disponibilidad ni condiciones.
- Si la evidencia no permite responder, dilo claramente.
- Nunca mezcles información comercial de tiendas o mercados diferentes.
- Si existe una moneda configurada para la tienda, usa esa moneda cuando hables de precios.
- Nunca conviertas una moneda a otra salvo que el cliente lo solicite explícitamente y exista información suficiente para hacerlo.
- Si existe un idioma principal configurado para la tienda, úsalo como idioma por defecto.
- Si el cliente escribe claramente en otro idioma, puedes responder en el idioma del cliente.
- Las reglas, precios o condiciones de otro país no deben aplicarse automáticamente al mercado actual.
- Sé breve, útil y natural.
- No menciones detalles internos de AWS, Bedrock, vectores, RAG, data sources ni bases de conocimiento.
""".strip()

    user_prompt = f"""
PREGUNTA DEL CLIENTE:

{question}

MERCADO ACTUAL:

{market_context}

EVIDENCIA DE CONOCIMIENTO:

{context}

DATOS COMERCIALES ACTUALES:

{commerce_context}

Reglas sobre datos comerciales:
- Los precios, disponibilidad y stock de DATOS COMERCIALES ACTUALES tienen prioridad sobre documentos.
- Nunca inventes una variante, precio, cantidad, descuento, promoción o disponibilidad.
- Si stock es 0 o Disponible es False, no digas que está disponible.
- Mantén exactamente la moneda indicada en los datos comerciales.
- No mezcles productos de otros mercados.
- No afirmes que existen tiendas físicas, tienda online, enlaces de compra, domicilios, métodos de pago o puntos de venta salvo que esa información esté explícitamente disponible.
- No prometas acciones que todavía no puedas ejecutar.
- Si el cliente pregunta por una variante concreta, responde solamente sobre esa variante cuando haya coincidencia clara.
- No muestres información interna como SKU, IDs, scores o cantidades de búsqueda salvo que sea útil para el cliente.
- Para WhatsApp, responde de forma natural y breve.
- Evita encabezados Markdown como ###.
- Evita respuestas largas cuando una respuesta de dos o tres frases sea suficiente.

Responde únicamente con base en la evidencia y respetando el mercado actual.
""".strip()

    response = (
        get_bedrock_runtime()
        .converse(
            modelId=CHAT_MODEL_ID,

            system=[
                {
                    "text":
                        system_prompt,
                }
            ],

            messages=[
                {
                    "role":
                        "user",

                    "content": [
                        {
                            "text":
                                user_prompt,
                        }
                    ],
                }
            ],

            inferenceConfig={
                "maxTokens":
                    500,

                "temperature":
                    0.2,

                "topP":
                    0.9,
            },
        )
    )

    output = (
        response
        .get("output", {})
        .get("message", {})
        .get("content", [])
    )

    text_parts = [
        block.get(
            "text",
            "",
        )
        for block in output
        if block.get("text")
    ]

    return "\n".join(
        text_parts
    ).strip()
