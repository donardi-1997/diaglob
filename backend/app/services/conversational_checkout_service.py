"""Deterministic conversational COD checkout orchestration.

The LLM is not allowed to infer checkout completion. This service owns every
state transition, normalizes delivery data, requires explicit confirmation of
the normalized address, then requires a separate explicit final order
confirmation before creating an external order.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from ..commerce import search_products
from ..model_domains.conversational_checkout import ConversationalCheckout
from ..models import Agent, CommerceConnection, Conversation, Message, Product, ProductVariant
from .attributed_order_service import create_attributed_shopify_cod_order

ACTIVE_STATUSES = {
    "collecting_variant",
    "collecting_quantity",
    "collecting_name",
    "collecting_phone",
    "collecting_region",
    "collecting_city",
    "collecting_address",
    "collecting_neighborhood",
    "collecting_address_complement",
    "awaiting_address_confirmation",
    "collecting_delivery_reference",
    "awaiting_order_confirmation",
    "creating_order",
}
TERMINAL_STATUSES = {"order_created", "cancelled", "failed", "expired"}
CHECKOUT_TTL = timedelta(hours=24)
MAX_QUANTITY = 10
ADDRESS_CONFIDENCE_MIN = 75

PURCHASE_PATTERNS = (
    "quiero comprar",
    "quiero pedir",
    "hacer pedido",
    "realizar pedido",
    "lo quiero",
    "me lo llevo",
    "comprar",
    "compralo",
    "cómpralo",
    "i want to buy",
    "i want to order",
    "buy it",
    "place an order",
    "quero comprar",
    "quero pedir",
    "fazer pedido",
)
CANCEL_WORDS = {"cancelar", "cancelar pedido", "cancel", "cancel order", "cancelar compra"}
ADDRESS_YES = {
    "si",
    "si esta correcta",
    "si es correcta",
    "correcta",
    "confirmo direccion",
    "yes",
    "yes correct",
    "correct",
    "confirm address",
    "sim",
    "sim esta correto",
    "correto",
    "confirmo endereco",
}
ADDRESS_NO_PREFIXES = ("no", "corregir", "cambiar", "incorrect", "change", "corrigir", "alterar")
FINAL_CONFIRMATIONS = {
    "confirmo",
    "confirmo pedido",
    "confirmar pedido",
    "confirm",
    "confirm order",
}
NO_COMPLEMENT = {"no", "ninguno", "ninguna", "no aplica", "n/a", "na", "none", "sem", "nao", "não"}

STREET_ALIASES = {
    "calle": "Calle",
    "cl": "Calle",
    "carrera": "Carrera",
    "cra": "Carrera",
    "cr": "Carrera",
    "kr": "Carrera",
    "avenida": "Avenida",
    "av": "Avenida",
    "diagonal": "Diagonal",
    "diag": "Diagonal",
    "transversal": "Transversal",
    "transv": "Transversal",
    "tv": "Transversal",
    "circular": "Circular",
    "autopista": "Autopista",
    "rua": "Rua",
    "street": "Street",
    "st": "Street",
    "road": "Road",
    "rd": "Road",
}


def _plain(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    without_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", without_marks.lower().strip())


def _clean_text(value: str, limit: int) -> str:
    return re.sub(r"\s+", " ", value.strip())[:limit]


def _smart_title(value: str, limit: int = 150) -> str:
    value = _clean_text(value, limit)
    return " ".join(part.capitalize() if not part.isupper() else part for part in value.split())


def _money(value: Decimal | float | int | None, currency: str) -> str:
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    return f"{currency} {amount:,.2f}"


def _locale(conversation: Conversation) -> str:
    language = (conversation.store.default_language if conversation.store else "es") or "es"
    if language.lower().startswith("en"):
        return "en"
    if language.lower().startswith("pt"):
        return "pt"
    return "es"


def _purchase_intent(text: str) -> bool:
    value = _plain(text)
    return any(pattern in value for pattern in PURCHASE_PATTERNS)


def _valid_phone(value: str | None) -> bool:
    return len(re.sub(r"\D", "", value or "")) >= 7


def _normalize_phone(value: str) -> str:
    value = value.strip()
    digits = re.sub(r"\D", "", value)
    return ("+" if value.startswith("+") else "") + digits


def normalize_delivery_address(raw: str, country_code: str) -> tuple[str | None, int]:
    """Normalize a street address without inventing missing geographic data."""
    cleaned = re.sub(r"\s+", " ", raw.strip().replace(",", " "))
    if len(cleaned) < 6 or not re.search(r"\d", cleaned):
        return None, 0

    plain = _plain(cleaned)
    first = plain.split(" ", 1)[0]
    street_type = STREET_ALIASES.get(first)
    score = 20 if street_type else 5

    rest = cleaned.split(" ", 1)[1] if " " in cleaned else ""
    rest = re.sub(r"\b(?:no\.?|nro\.?|numero)\b", "#", rest, flags=re.IGNORECASE)
    rest = re.sub(r"\s*#\s*", " # ", rest)
    rest = re.sub(r"\s*-\s*", "-", rest)

    # Common Colombian shorthand: "calle 80 15 24" -> "Calle 80 # 15-24".
    if country_code.upper() == "CO" and street_type and "#" not in rest:
        match = re.match(
            r"^([0-9A-Za-z-]+)\s+([0-9A-Za-z-]+)\s+([0-9A-Za-z-]+)(.*)$",
            rest,
        )
        if match:
            rest = f"{match.group(1)} # {match.group(2)}-{match.group(3)}{match.group(4)}"

    prefix = street_type or cleaned.split(" ", 1)[0].capitalize()
    normalized = f"{prefix} {rest}".strip()
    normalized = re.sub(r"\s+", " ", normalized)

    numeric_groups = re.findall(r"\d+[A-Za-z]?", normalized)
    # A Colombian COD street address needs enough numbering to identify the
    # actual property. A value such as "Calle 80" names only the road and must
    # never advance to address confirmation.
    if country_code.upper() == "CO" and street_type and len(numeric_groups) < 3:
        return None, 0
    if len(numeric_groups) >= 1:
        score += 15
    if len(numeric_groups) >= 3 or "#" in normalized:
        score += 20
    if len(normalized) >= 8:
        score += 10

    # Non-CO addresses can be structurally valid without '#'. Keep the
    # normalizer conservative and let geographic fields complete confidence.
    return normalized[:300], min(score, 65)


def _address_confidence(checkout: ConversationalCheckout) -> int:
    base = 0
    normalized, structural = normalize_delivery_address(
        checkout.address_raw or checkout.address_line or "",
        checkout.country_code,
    )
    if normalized:
        base += structural
    if checkout.region:
        base += 10
    if checkout.city:
        base += 10
    if checkout.neighborhood:
        base += 8
    if _valid_phone(checkout.phone):
        base += 7
    return min(base, 100)


def _address_confirmation_text(checkout: ConversationalCheckout, locale: str) -> str:
    complement = checkout.address_complement or ("No aplica" if locale == "es" else "None" if locale == "en" else "Não se aplica")
    if locale == "en":
        return (
            "I understood your delivery address as:\n"
            f"Address: {checkout.address_line}\n"
            f"Complement: {complement}\n"
            f"Neighborhood: {checkout.neighborhood}\n"
            f"City: {checkout.city}\n"
            f"State/Region: {checkout.region}\n"
            f"Country: {checkout.country_code}\n\n"
            "Is this exactly correct? Reply YES to confirm it or NO to enter it again."
        )
    if locale == "pt":
        return (
            "Entendi seu endereço de entrega assim:\n"
            f"Endereço: {checkout.address_line}\n"
            f"Complemento: {complement}\n"
            f"Bairro: {checkout.neighborhood}\n"
            f"Cidade: {checkout.city}\n"
            f"Estado/Região: {checkout.region}\n"
            f"País: {checkout.country_code}\n\n"
            "Está exatamente correto? Responda SIM para confirmar ou NÃO para digitá-lo novamente."
        )
    return (
        "Entendí tu dirección de entrega así:\n"
        f"Dirección: {checkout.address_line}\n"
        f"Complemento: {complement}\n"
        f"Barrio: {checkout.neighborhood}\n"
        f"Ciudad: {checkout.city}\n"
        f"Departamento/Estado: {checkout.region}\n"
        f"País: {checkout.country_code}\n\n"
        "¿Está exactamente correcta? Responde SÍ para confirmarla o NO para escribirla de nuevo."
    )


def _final_confirmation_text(checkout: ConversationalCheckout, locale: str) -> str:
    total = _money(checkout.total, checkout.currency)
    variant = f" · {checkout.variant_title}" if checkout.variant_title else ""
    address = f"{checkout.address_line}, {checkout.neighborhood}, {checkout.city}, {checkout.region}"
    if checkout.address_complement:
        address += f", {checkout.address_complement}"
    if locale == "en":
        return (
            "Final COD order confirmation:\n"
            f"{checkout.product_title}{variant}\n"
            f"Quantity: {checkout.quantity}\n"
            f"Product total: {total}\n"
            f"Receive at: {address}\n"
            f"Reference: {checkout.delivery_reference}\n"
            f"Recipient: {checkout.customer_name}\n"
            f"Phone: {checkout.phone}\n\n"
            "You will pay when you receive the order. To create it, reply exactly: CONFIRM"
        )
    if locale == "pt":
        return (
            "Confirmação final do pedido contra entrega:\n"
            f"{checkout.product_title}{variant}\n"
            f"Quantidade: {checkout.quantity}\n"
            f"Total dos produtos: {total}\n"
            f"Entrega: {address}\n"
            f"Referência: {checkout.delivery_reference}\n"
            f"Recebe: {checkout.customer_name}\n"
            f"Telefone: {checkout.phone}\n\n"
            "Você paga ao receber. Para criar o pedido, responda exatamente: CONFIRMO"
        )
    return (
        "Confirmación final del pedido contraentrega:\n"
        f"{checkout.product_title}{variant}\n"
        f"Cantidad: {checkout.quantity}\n"
        f"Total de productos: {total}\n"
        f"Entrega: {address}\n"
        f"Referencia: {checkout.delivery_reference}\n"
        f"Recibe: {checkout.customer_name}\n"
        f"Teléfono: {checkout.phone}\n\n"
        "Pagarás al recibir. Para crear el pedido responde exactamente: CONFIRMO"
    )


def _variant_prompt(checkout: ConversationalCheckout, variants: list[ProductVariant], locale: str) -> str:
    options = "\n".join(
        f"{index}. {variant.title} — {_money(variant.price, variant.currency)}"
        for index, variant in enumerate(variants[:8], start=1)
    )
    if locale == "en":
        return f"Which variant do you want? Reply with the number:\n{options}"
    if locale == "pt":
        return f"Qual variante você quer? Responda com o número:\n{options}"
    return f"¿Cuál variante quieres? Responde con el número:\n{options}"


def _available_variants(db: Session, checkout: ConversationalCheckout) -> list[ProductVariant]:
    if not checkout.product_id:
        return []
    return (
        db.query(ProductVariant)
        .join(ProductVariant.product)
        .filter(
            ProductVariant.product_id == checkout.product_id,
            ProductVariant.product.has(
                organization_id=checkout.organization_id,
                store_id=checkout.store_id,
                active=True,
            ),
            ProductVariant.available.is_(True),
            ProductVariant.inventory_quantity > 0,
        )
        .order_by(ProductVariant.id.asc())
        .all()
    )


def _select_variant(checkout: ConversationalCheckout, variant: ProductVariant) -> None:
    checkout.variant_id = variant.id
    checkout.variant_title = variant.title
    checkout.unit_price = float(variant.price)
    checkout.subtotal = float(variant.price) * checkout.quantity
    checkout.total = float(checkout.subtotal) + float(checkout.shipping_amount or 0)
    checkout.currency = variant.currency


def _reset_address(checkout: ConversationalCheckout) -> None:
    checkout.address_raw = None
    checkout.address_line = None
    checkout.address_complement = None
    checkout.neighborhood = None
    checkout.address_confidence_score = 0
    checkout.address_validation_status = "pending"
    checkout.address_confirmed = False
    checkout.address_confirmed_at = None
    checkout.delivery_reference = None
    checkout.customer_confirmed = False
    checkout.customer_confirmed_at = None


def _active_checkout(db: Session, conversation: Conversation) -> ConversationalCheckout | None:
    checkout = (
        db.query(ConversationalCheckout)
        .filter(
            ConversationalCheckout.organization_id == conversation.organization_id,
            ConversationalCheckout.store_id == conversation.store_id,
            ConversationalCheckout.conversation_id == conversation.id,
            ConversationalCheckout.status.in_(ACTIVE_STATUSES),
        )
        .order_by(ConversationalCheckout.id.desc())
        .first()
    )
    if checkout and checkout.expires_at <= datetime.utcnow():
        checkout.status = "expired"
        checkout.updated_at = datetime.utcnow()
        db.commit()
        return None
    return checkout


def _recent_search_text(db: Session, conversation_id: int, current: str) -> str:
    rows = (
        db.query(Message)
        .filter(
            Message.conversation_id == conversation_id,
            Message.sender.in_(["customer", "ai"]),
        )
        .order_by(Message.id.desc())
        .limit(6)
        .all()
    )
    rows.reverse()
    return " ".join([row.text for row in rows] + [current])[-4000:]


def _start_checkout(
    db: Session,
    conversation: Conversation,
    agent: Agent,
    text: str,
) -> tuple[ConversationalCheckout | None, str | None]:
    if not _purchase_intent(text):
        return None, None

    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.organization_id == conversation.organization_id,
            CommerceConnection.store_id == conversation.store_id,
            CommerceConnection.provider == "shopify",
            CommerceConnection.status == "connected",
        )
        .first()
    )
    if not connection:
        conversation.mode = "human"
        db.commit()
        return None, (
            "Quiero ayudarte a cerrar el pedido, pero esta tienda no tiene Shopify conectado para crear la orden automáticamente. "
            "Dejo la conversación para que un asesor continúe."
        )

    query = _recent_search_text(db, conversation.id, text)
    results = search_products(
        db=db,
        organization_id=conversation.organization_id,
        store_id=conversation.store_id,
        query=query,
        limit=5,
    )
    if not results:
        return None, None

    top = results[0]
    product = (
        db.query(Product)
        .filter(
            Product.id == top["product_id"],
            Product.organization_id == conversation.organization_id,
            Product.store_id == conversation.store_id,
            Product.active.is_(True),
        )
        .first()
    )
    if not product:
        return None, None

    available = [variant for variant in product.variants if variant.available and int(variant.inventory_quantity or 0) > 0]
    locale = _locale(conversation)
    if not available:
        if locale == "en":
            return None, "That product is currently out of stock, so I can't start a COD order."
        if locale == "pt":
            return None, "Esse produto está sem estoque no momento, então não posso iniciar o pedido contra entrega."
        return None, "Ese producto está agotado en este momento, así que no puedo iniciar el pedido contraentrega."

    checkout = ConversationalCheckout(
        organization_id=conversation.organization_id,
        store_id=conversation.store_id,
        conversation_id=conversation.id,
        customer_id=conversation.customer_id,
        ai_agent_id=agent.id,
        status="collecting_variant",
        product_id=product.id,
        product_title=product.title,
        quantity=1,
        currency=conversation.store.currency,
        shipping_amount=0,
        country_code=conversation.store.country_code,
        customer_name=None,
        phone=(conversation.customer.phone if conversation.customer else None),
        address_confidence_score=0,
        address_validation_status="pending",
        address_confirmed=False,
        customer_confirmed=False,
        expires_at=datetime.utcnow() + CHECKOUT_TTL,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(checkout)
    db.flush()

    # search_products already narrows variants when the customer includes an
    # exact size/SKU. Use that only when it resolves to one available variant.
    result_variant_ids = {
        int(item["id"])
        for item in top.get("variants", [])
        if item.get("available")
    }
    narrowed = [variant for variant in available if variant.id in result_variant_ids]
    if len(narrowed) == 1:
        _select_variant(checkout, narrowed[0])
        checkout.status = "collecting_quantity"
        db.commit()
        if locale == "en":
            return checkout, f"Perfect. {product.title} · {narrowed[0].title}. How many units do you want?"
        if locale == "pt":
            return checkout, f"Perfeito. {product.title} · {narrowed[0].title}. Quantas unidades você quer?"
        return checkout, f"Perfecto. {product.title} · {narrowed[0].title}. ¿Cuántas unidades quieres?"

    db.commit()
    return checkout, _variant_prompt(checkout, available, locale)


def _finalize_checkout(
    db: Session,
    conversation: Conversation,
    agent: Agent,
    checkout: ConversationalCheckout,
) -> str:
    locale = _locale(conversation)
    if not checkout.address_confirmed or not checkout.address_confirmed_at:
        checkout.status = "awaiting_address_confirmation"
        checkout.customer_confirmed = False
        checkout.customer_confirmed_at = None
        db.commit()
        return _address_confirmation_text(checkout, locale)

    variant = (
        db.query(ProductVariant)
        .join(ProductVariant.product)
        .filter(
            ProductVariant.id == checkout.variant_id,
            ProductVariant.product.has(
                organization_id=checkout.organization_id,
                store_id=checkout.store_id,
                active=True,
            ),
        )
        .first()
    )
    if not variant or not variant.available or int(variant.inventory_quantity or 0) < checkout.quantity:
        checkout.status = "failed"
        checkout.failure_reason = "variant_out_of_stock_before_creation"
        checkout.customer_confirmed = False
        checkout.customer_confirmed_at = None
        conversation.mode = "human"
        db.commit()
        if locale == "en":
            return "The selected variant ran out of stock before confirmation. I won't create an incorrect order; a person will continue with you."
        if locale == "pt":
            return "A variante escolhida ficou sem estoque antes da confirmação. Não vou criar um pedido incorreto; uma pessoa continuará com você."
        return "La variante elegida se agotó antes de confirmar. No voy a crear un pedido incorrecto; un asesor continuará contigo."

    live_price = Decimal(str(variant.price))
    previous_price = Decimal(str(checkout.unit_price or 0))
    if live_price != previous_price:
        _select_variant(checkout, variant)
        checkout.status = "awaiting_order_confirmation"
        checkout.customer_confirmed = False
        checkout.customer_confirmed_at = None
        db.commit()
        if locale == "en":
            prefix = "The price changed while we were confirming your information. Please review the updated total.\n\n"
        elif locale == "pt":
            prefix = "O preço mudou enquanto confirmávamos seus dados. Revise o novo total.\n\n"
        else:
            prefix = "El precio cambió mientras confirmábamos tus datos. Revisa el nuevo total.\n\n"
        return prefix + _final_confirmation_text(checkout, locale)

    checkout.customer_confirmed = True
    checkout.customer_confirmed_at = datetime.utcnow()
    checkout.status = "creating_order"
    checkout.updated_at = datetime.utcnow()
    db.commit()

    name_parts = (checkout.customer_name or "Cliente").split()
    first_name = name_parts[0]
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else None
    address2_parts = [
        checkout.address_complement,
        f"Barrio {checkout.neighborhood}" if checkout.neighborhood else None,
    ]
    shipping_address = {
        "first_name": first_name,
        "last_name": last_name,
        "address1": checkout.address_line,
        "address2": " · ".join(part for part in address2_parts if part) or None,
        "city": checkout.city,
        "province": checkout.region,
        "country_code": checkout.country_code,
        "zip": checkout.postal_code,
        "phone": checkout.phone,
    }
    note = (
        "Diaglob conversational COD checkout\n"
        f"Checkout: {checkout.id}\n"
        f"Address confirmed at: {checkout.address_confirmed_at.isoformat()}\n"
        f"Delivery reference: {checkout.delivery_reference}\n"
        f"Normalized address: {checkout.address_line}; {checkout.neighborhood}; "
        f"{checkout.city}; {checkout.region}; {checkout.country_code}"
    )

    try:
        result = create_attributed_shopify_cod_order(
            db,
            checkout.organization_id,
            checkout.store_id,
            customer_id=checkout.customer_id,
            variant_local_id=int(checkout.variant_id),
            quantity=checkout.quantity,
            customer_email=(conversation.customer.email if conversation.customer else None),
            customer_phone=checkout.phone or "",
            shipping_address=shipping_address,
            note=note,
            idempotency_key=f"chat-cod:{checkout.id}:{checkout.conversation_id}",
            ai_agent_id=agent.id,
            conversation_id=conversation.id,
        )
    except Exception as exc:
        checkout.status = "failed"
        checkout.failure_reason = str(exc)[:500]
        conversation.mode = "human"
        db.commit()
        if locale == "en":
            return "I confirmed your information but couldn't create the external order safely. I stopped the process and a person will continue with you."
        if locale == "pt":
            return "Confirmei seus dados, mas não consegui criar o pedido externo com segurança. Parei o processo e uma pessoa continuará com você."
        return "Confirmé tus datos, pero no pude crear el pedido externo de forma segura. Detuve el proceso y un asesor continuará contigo."

    if not result.get("ok") or result.get("order_id") is None:
        checkout.status = "failed"
        checkout.failure_reason = "external_order_not_created"
        conversation.mode = "human"
        db.commit()
        return "No pude confirmar la creación externa del pedido. No voy a duplicarlo; un asesor revisará el caso."

    checkout.created_order_id = int(result["order_id"])
    checkout.status = "order_created"
    checkout.failure_reason = None
    checkout.updated_at = datetime.utcnow()
    db.commit()

    order_number = result.get("order_number") or result.get("order_id")
    if locale == "en":
        return f"Order {order_number} confirmed. Payment is cash on delivery. Keep your phone available for delivery coordination."
    if locale == "pt":
        return f"Pedido {order_number} confirmado. O pagamento é contra entrega. Mantenha seu telefone disponível para coordenar a entrega."
    return f"Pedido {order_number} confirmado. El pago es contraentrega. Mantén tu teléfono disponible para coordinar la entrega."


def process_conversational_checkout_turn(
    db: Session,
    conversation: Conversation,
    agent: Agent,
    text: str,
) -> str | None:
    """Handle one checkout turn, or return None for the normal AI pipeline."""
    checkout = _active_checkout(db, conversation)
    if checkout is None:
        _, start_answer = _start_checkout(db, conversation, agent, text)
        return start_answer

    locale = _locale(conversation)
    normalized = _plain(text)
    if normalized in CANCEL_WORDS:
        checkout.status = "cancelled"
        checkout.customer_confirmed = False
        checkout.customer_confirmed_at = None
        checkout.updated_at = datetime.utcnow()
        db.commit()
        if locale == "en":
            return "The order process was cancelled. No order was created."
        if locale == "pt":
            return "O processo do pedido foi cancelado. Nenhum pedido foi criado."
        return "Cancelé el proceso del pedido. No se creó ninguna orden."

    if checkout.status == "creating_order":
        if locale == "en":
            return "Your confirmed order is being created. Please don't confirm it again."
        if locale == "pt":
            return "Seu pedido confirmado está sendo criado. Não o confirme novamente."
        return "Tu pedido confirmado se está creando. No es necesario volver a confirmarlo."

    if checkout.status == "collecting_variant":
        variants = _available_variants(db, checkout)
        selected = None
        if normalized.isdigit():
            index = int(normalized) - 1
            if 0 <= index < len(variants):
                selected = variants[index]
        if selected is None:
            matches = [
                variant
                for variant in variants
                if normalized in _plain(variant.title)
                or (variant.sku and normalized == _plain(variant.sku))
            ]
            if len(matches) == 1:
                selected = matches[0]
        if selected is None:
            return _variant_prompt(checkout, variants, locale)
        _select_variant(checkout, selected)
        checkout.status = "collecting_quantity"
        db.commit()
        if locale == "en":
            return "How many units do you want?"
        if locale == "pt":
            return "Quantas unidades você quer?"
        return "¿Cuántas unidades quieres?"

    if checkout.status == "collecting_quantity":
        match = re.fullmatch(r"\s*(\d{1,2})\s*", text)
        quantity = int(match.group(1)) if match else 0
        if quantity < 1 or quantity > MAX_QUANTITY:
            if locale == "en":
                return f"Reply with a quantity from 1 to {MAX_QUANTITY}."
            if locale == "pt":
                return f"Responda com uma quantidade de 1 a {MAX_QUANTITY}."
            return f"Responde con una cantidad entre 1 y {MAX_QUANTITY}."
        variant = db.query(ProductVariant).filter(ProductVariant.id == checkout.variant_id).first()
        if not variant or int(variant.inventory_quantity or 0) < quantity:
            return "No hay suficiente inventario para esa cantidad. Indica una cantidad menor."
        checkout.quantity = quantity
        _select_variant(checkout, variant)
        checkout.status = "collecting_name"
        db.commit()
        if locale == "en":
            return "What full name should I put on the delivery?"
        if locale == "pt":
            return "Qual nome completo devo colocar na entrega?"
        return "¿A nombre de quién recibimos el pedido? Escríbeme el nombre completo."

    if checkout.status == "collecting_name":
        value = _clean_text(text, 150)
        if len(value) < 2 or not re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", value):
            return "Necesito un nombre válido para la persona que recibirá el pedido."
        checkout.customer_name = value
        if _valid_phone(checkout.phone):
            checkout.status = "collecting_region"
            answer = "¿En qué departamento o estado recibirás el pedido?"
        else:
            checkout.status = "collecting_phone"
            answer = "¿Cuál es el número de teléfono de quien recibirá el pedido?"
        db.commit()
        return answer

    if checkout.status == "collecting_phone":
        if not _valid_phone(text):
            return "Necesito un teléfono válido con al menos 7 dígitos."
        checkout.phone = _normalize_phone(text)
        checkout.status = "collecting_region"
        db.commit()
        return "¿En qué departamento o estado recibirás el pedido?"

    if checkout.status == "collecting_region":
        value = _smart_title(text)
        if len(value) < 2:
            return "Necesito el departamento o estado de entrega."
        checkout.region = value
        checkout.status = "collecting_city"
        checkout.address_confirmed = False
        checkout.address_confirmed_at = None
        db.commit()
        return "¿En qué ciudad o municipio recibirás el pedido?"

    if checkout.status == "collecting_city":
        value = _smart_title(text)
        if len(value) < 2:
            return "Necesito la ciudad o municipio de entrega."
        checkout.city = value
        checkout.status = "collecting_address"
        checkout.address_confirmed = False
        checkout.address_confirmed_at = None
        db.commit()
        return "Escribe la dirección completa. Ejemplo: Calle 80 # 15-24. No uses solo referencias como 'al lado del parque'."

    if checkout.status == "collecting_address":
        address, structural_score = normalize_delivery_address(text, checkout.country_code)
        if not address or structural_score < 45:
            checkout.address_validation_status = "invalid"
            checkout.address_confidence_score = 0
            db.commit()
            return "No pude convertir eso en una dirección suficientemente precisa. Escríbela con vía y numeración, por ejemplo: Carrera 15 # 24-36."
        checkout.address_raw = _clean_text(text, 1000)
        checkout.address_line = address
        checkout.address_validation_status = "pending"
        checkout.address_confirmed = False
        checkout.address_confirmed_at = None
        checkout.status = "collecting_neighborhood"
        db.commit()
        return "¿Cuál es el barrio de esa dirección?"

    if checkout.status == "collecting_neighborhood":
        value = _smart_title(text)
        if len(value) < 2:
            return "Necesito el barrio para reducir errores de entrega."
        checkout.neighborhood = value
        checkout.address_confirmed = False
        checkout.address_confirmed_at = None
        checkout.status = "collecting_address_complement"
        db.commit()
        return "¿Es casa, apartamento, oficina o local? Escribe el complemento (por ejemplo 'Apto 302') o responde NO si no aplica."

    if checkout.status == "collecting_address_complement":
        checkout.address_complement = None if normalized in NO_COMPLEMENT else _clean_text(text, 200)
        checkout.address_confirmed = False
        checkout.address_confirmed_at = None
        checkout.address_confidence_score = _address_confidence(checkout)
        if checkout.address_confidence_score < ADDRESS_CONFIDENCE_MIN:
            checkout.address_validation_status = "invalid"
            _reset_address(checkout)
            checkout.status = "collecting_address"
            db.commit()
            return "La dirección todavía no tiene suficiente precisión para un envío contraentrega. Escríbela de nuevo completa, por ejemplo: Carrera 15 # 24-36."
        checkout.address_validation_status = "valid"
        checkout.status = "awaiting_address_confirmation"
        db.commit()
        return _address_confirmation_text(checkout, locale)

    if checkout.status == "awaiting_address_confirmation":
        if normalized in ADDRESS_YES:
            checkout.address_confirmed = True
            checkout.address_confirmed_at = datetime.utcnow()
            checkout.status = "collecting_delivery_reference"
            db.commit()
            return "Dirección confirmada. Ahora dame una referencia que ayude al transportador a encontrar el lugar, por ejemplo: 'edificio gris frente al D1'."
        if normalized.startswith(ADDRESS_NO_PREFIXES):
            _reset_address(checkout)
            checkout.status = "collecting_address"
            db.commit()
            return "Perfecto. No guardaré esa dirección como confirmada. Escríbela nuevamente completa y volveré a mostrártela antes de continuar."
        return _address_confirmation_text(checkout, locale)

    if checkout.status == "collecting_delivery_reference":
        value = _clean_text(text, 500)
        if len(value) < 4:
            return "Dame una referencia un poco más clara para ayudar a encontrar la dirección."
        checkout.delivery_reference = value
        checkout.status = "awaiting_order_confirmation"
        checkout.customer_confirmed = False
        checkout.customer_confirmed_at = None
        db.commit()
        return _final_confirmation_text(checkout, locale)

    if checkout.status == "awaiting_order_confirmation":
        expected = "confirm" if locale == "en" else "confirmo"
        if normalized not in FINAL_CONFIRMATIONS or (locale == "en" and not normalized.startswith("confirm")):
            if locale == "en":
                return "I won't create the order from an ambiguous reply. Review the summary and reply exactly CONFIRM, or CANCEL to stop."
            if locale == "pt":
                return "Não vou criar o pedido com uma resposta ambígua. Revise o resumo e responda exatamente CONFIRMO, ou CANCELAR para parar."
            return "No crearé el pedido con una respuesta ambigua. Revisa el resumen y responde exactamente CONFIRMO, o CANCELAR para detenerlo."
        if normalized != expected and normalized not in {f"{expected} pedido", "confirmar pedido"}:
            return _final_confirmation_text(checkout, locale)
        return _finalize_checkout(db, conversation, agent, checkout)

    return None


def get_current_checkout(
    db: Session,
    organization_id: int,
    store_id: int,
    conversation_id: int,
) -> dict | None:
    """Return the latest checkout state for staff-facing conversation context."""
    checkout = (
        db.query(ConversationalCheckout)
        .filter(
            ConversationalCheckout.organization_id == organization_id,
            ConversationalCheckout.store_id == store_id,
            ConversationalCheckout.conversation_id == conversation_id,
        )
        .order_by(ConversationalCheckout.id.desc())
        .first()
    )
    if not checkout:
        return None
    return {
        "id": checkout.id,
        "status": checkout.status,
        "product_id": checkout.product_id,
        "variant_id": checkout.variant_id,
        "product_title": checkout.product_title,
        "variant_title": checkout.variant_title,
        "quantity": checkout.quantity,
        "currency": checkout.currency,
        "total": float(checkout.total) if checkout.total is not None else None,
        "payment_method": checkout.payment_method,
        "address_line": checkout.address_line,
        "address_complement": checkout.address_complement,
        "neighborhood": checkout.neighborhood,
        "city": checkout.city,
        "region": checkout.region,
        "country_code": checkout.country_code,
        "delivery_reference": checkout.delivery_reference,
        "address_confidence_score": checkout.address_confidence_score,
        "address_validation_status": checkout.address_validation_status,
        "address_confirmed": checkout.address_confirmed,
        "address_confirmed_at": checkout.address_confirmed_at.isoformat() if checkout.address_confirmed_at else None,
        "customer_confirmed": checkout.customer_confirmed,
        "customer_confirmed_at": checkout.customer_confirmed_at.isoformat() if checkout.customer_confirmed_at else None,
        "created_order_id": checkout.created_order_id,
        "failure_reason": checkout.failure_reason,
        "expires_at": checkout.expires_at.isoformat(),
    }
