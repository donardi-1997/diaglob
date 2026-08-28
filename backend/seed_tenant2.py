from app.db import SessionLocal
from app.models import Organization, Customer, Conversation, Message

db = SessionLocal()

try:
    existing = (
        db.query(Organization)
        .filter(
            Organization.slug == "acme-demo"
        )
        .first()
    )

    if existing:
        print(
            f"ACME ya existe con id={existing.id}"
        )
        raise SystemExit(0)

    organization = Organization(
        name="ACME Store",
        slug="acme-demo",
    )

    db.add(organization)
    db.flush()

    customer = Customer(
        organization_id=organization.id,
        name="María Torres",
        phone="+57 311 555 0199",
        email="maria@acme.test",
        country="Colombia",
        shopify_orders=3,
        shopify_total_spent=459700,
        shopify_last_order="#A-203",
    )

    db.add(customer)
    db.flush()

    conversation = Conversation(
        organization_id=organization.id,
        customer_id=customer.id,
        channel="WhatsApp",
        preview="Hola, quiero información sobre un producto.",
        unread=1,
        agent="sales",
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

    print(
        f"OK - ACME Store creada con id={organization.id}"
    )
    print(
        f"OK - conversación creada con id={conversation.id}"
    )

finally:
    db.close()
