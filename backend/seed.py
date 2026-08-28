from app.db import Base, SessionLocal, engine
from app.models import (
    Agent,
    Conversation,
    Customer,
    CustomerStoreProfile,
    KnowledgeBase,
    Message,
    Organization,
    Store,
)

Base.metadata.create_all(bind=engine)

db = SessionLocal()

try:
    # ========================================================
    # DIAGLOB DEMO
    # ========================================================

    org = Organization(
        name="Diaglob Demo",
        slug="diaglob-demo",
    )

    db.add(org)
    db.flush()

    colombia = Store(
        organization_id=org.id,
        name="Diaglob Colombia",
        slug="colombia",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
        shopify_domain="diaglob-co.myshopify.com",
    )

    mexico = Store(
        organization_id=org.id,
        name="Diaglob México",
        slug="mexico",
        country_code="MX",
        currency="MXN",
        timezone="America/Mexico_City",
        default_language="es",
        shopify_domain="diaglob-mx.myshopify.com",
    )

    usa = Store(
        organization_id=org.id,
        name="Diaglob USA",
        slug="usa",
        country_code="US",
        currency="USD",
        timezone="America/New_York",
        default_language="en",
        shopify_domain="diaglob-us.myshopify.com",
    )

    db.add_all([
        colombia,
        mexico,
        usa,
    ])
    db.flush()

    sales_agent = Agent(
        organization_id=org.id,
        name="Sales Agent LATAM",
        role="sales",
    )

    support_agent = Agent(
        organization_id=org.id,
        name="Global Support",
        role="support",
    )

    db.add_all([
        sales_agent,
        support_agent,
    ])
    db.flush()

    sales_agent.stores.extend([
        colombia,
        mexico,
    ])

    support_agent.stores.extend([
        colombia,
        mexico,
        usa,
    ])

    policies = KnowledgeBase(
        organization_id=org.id,
        name="Políticas corporativas",
        scope="organization",
    )

    products = KnowledgeBase(
        organization_id=org.id,
        name="Catálogo LATAM",
        scope="selected_stores",
    )

    logistics = KnowledgeBase(
        organization_id=org.id,
        name="Logística internacional",
        scope="selected_stores",
    )

    usa_support = KnowledgeBase(
        organization_id=org.id,
        name="USA Support Knowledge",
        scope="selected_stores",
    )

    db.add_all([
        policies,
        products,
        logistics,
        usa_support,
    ])
    db.flush()

    products.stores.extend([
        colombia,
        mexico,
    ])

    logistics.stores.extend([
        colombia,
        mexico,
        usa,
    ])

    usa_support.stores.append(usa)

    sales_agent.knowledge_bases.extend([
        policies,
        products,
        logistics,
    ])

    support_agent.knowledge_bases.extend([
        policies,
        logistics,
        usa_support,
    ])

    demo = [
        {
            "store": colombia,
            "agent": sales_agent,
            "name": "Laura Gómez",
            "phone": "+57 300 555 0184",
            "email": "laura@email.com",
            "country": "CO",
            "preview": "¿Tienen los tenis negros en talla 38?",
            "orders": 6,
            "spent": 842400,
            "last_order": "#1037",
        },
        {
            "store": colombia,
            "agent": support_agent,
            "name": "Sebastián Ruiz",
            "phone": "+57 310 555 0144",
            "email": "sebastian@email.com",
            "country": "CO",
            "preview": "Quiero cambiar la dirección de entrega.",
            "orders": 1,
            "spent": 169900,
            "last_order": "#1040",
        },
        {
            "store": mexico,
            "agent": sales_agent,
            "name": "Fernanda Cruz",
            "phone": "+52 55 5555 0199",
            "email": "fernanda@example.com",
            "country": "MX",
            "preview": "¿Hacen envíos a Guadalajara?",
            "orders": 3,
            "spent": 3499,
            "last_order": "#MX-203",
        },
        {
            "store": usa,
            "agent": support_agent,
            "name": "Emily Carter",
            "phone": "+1 305 555 0194",
            "email": "emily@example.com",
            "country": "US",
            "preview": "Do you have this product in black?",
            "orders": 2,
            "spent": 189.98,
            "last_order": "#US-441",
        },
    ]

    for item in demo:
        customer = Customer(
            organization_id=org.id,
            name=item["name"],
            phone=item["phone"],
            email=item["email"],
            country_code=item["country"],
        )

        db.add(customer)
        db.flush()

        profile = CustomerStoreProfile(
            organization_id=org.id,
            customer_id=customer.id,
            store_id=item["store"].id,
            orders_count=item["orders"],
            total_spent=item["spent"],
            currency=item["store"].currency,
            last_order_ref=item["last_order"],
        )

        db.add(profile)

        conversation = Conversation(
            organization_id=org.id,
            store_id=item["store"].id,
            customer_id=customer.id,
            agent_id=item["agent"].id,
            channel="WhatsApp",
            preview=item["preview"],
            unread=1,
            mode="ai",
            tags="shopify",
        )

        db.add(conversation)
        db.flush()

        db.add(
            Message(
                conversation_id=conversation.id,
                sender="customer",
                text=item["preview"],
            )
        )

    # ========================================================
    # ACME
    # ========================================================

    acme = Organization(
        name="ACME Store",
        slug="acme-demo",
    )

    db.add(acme)
    db.flush()

    acme_colombia = Store(
        organization_id=acme.id,
        name="ACME Colombia",
        slug="colombia",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
    )

    db.add(acme_colombia)
    db.flush()

    acme_agent = Agent(
        organization_id=acme.id,
        name="ACME Sales",
        role="sales",
    )

    db.add(acme_agent)
    db.flush()

    acme_agent.stores.append(acme_colombia)

    maria = Customer(
        organization_id=acme.id,
        name="María Torres",
        phone="+57 311 555 0199",
        email="maria@acme.test",
        country_code="CO",
    )

    db.add(maria)
    db.flush()

    db.add(
        CustomerStoreProfile(
            organization_id=acme.id,
            customer_id=maria.id,
            store_id=acme_colombia.id,
            orders_count=3,
            total_spent=459700,
            currency="COP",
            last_order_ref="#A-203",
        )
    )

    conversation = Conversation(
        organization_id=acme.id,
        store_id=acme_colombia.id,
        customer_id=maria.id,
        agent_id=acme_agent.id,
        channel="WhatsApp",
        preview="Hola, quiero información sobre un producto.",
        unread=1,
        mode="ai",
        tags="high_intent,shopify",
    )

    db.add(conversation)
    db.flush()

    db.add(
        Message(
            conversation_id=conversation.id,
            sender="customer",
            text="Hola, quiero información sobre un producto.",
        )
    )

    db.commit()

    print("OK - modelo multi-tenant")
    print("OK - modelo multi-store")
    print("OK - multi-country")
    print("OK - Agents <-> Stores")
    print("OK - KnowledgeBases <-> Stores")
    print("OK - Agents <-> KnowledgeBases")
    print("OK - Customer <-> Store commerce profile")
    print("OK - Conversations -> real Agent")

finally:
    db.close()
