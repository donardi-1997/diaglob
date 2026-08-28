from app.db import SessionLocal
from app.models import (
    Organization,
    OrganizationMembership,
    Store,
    User,
)

db = SessionLocal()

try:
    existing = (
        db.query(User)
        .filter(
            User.email == "admin@diaglob.tech"
        )
        .first()
    )

    if existing:
        print(
            f"Usuario demo ya existe id={existing.id}"
        )
        raise SystemExit(0)

    diaglob = (
        db.query(Organization)
        .filter(
            Organization.slug == "diaglob-demo"
        )
        .first()
    )

    acme = (
        db.query(Organization)
        .filter(
            Organization.slug == "acme-demo"
        )
        .first()
    )

    if not diaglob or not acme:
        raise RuntimeError(
            "No encontré las organizaciones demo"
        )

    user = User(
        name="Adrián Demo",
        email="admin@diaglob.tech",
    )

    db.add(user)
    db.flush()

    # Owner de Diaglob:
    # acceso a todas sus tiendas.
    diaglob_membership = OrganizationMembership(
        user_id=user.id,
        organization_id=diaglob.id,
        role="owner",
        all_stores=True,
    )

    db.add(diaglob_membership)
    db.flush()

    # Manager de ACME:
    # acceso limitado a tiendas seleccionadas.
    acme_membership = OrganizationMembership(
        user_id=user.id,
        organization_id=acme.id,
        role="manager",
        all_stores=False,
    )

    db.add(acme_membership)
    db.flush()

    acme_colombia = (
        db.query(Store)
        .filter(
            Store.organization_id == acme.id,
            Store.slug == "colombia",
        )
        .first()
    )

    if not acme_colombia:
        raise RuntimeError(
            "No encontré ACME Colombia"
        )

    acme_membership.stores.append(
        acme_colombia
    )

    # Segundo usuario para probar aislamiento.
    agent_user = User(
        name="Laura Agent",
        email="agent@diaglob.tech",
    )

    db.add(agent_user)
    db.flush()

    agent_membership = OrganizationMembership(
        user_id=agent_user.id,
        organization_id=diaglob.id,
        role="agent",
        all_stores=False,
    )

    db.add(agent_membership)
    db.flush()

    colombia = (
        db.query(Store)
        .filter(
            Store.organization_id == diaglob.id,
            Store.slug == "colombia",
        )
        .first()
    )

    agent_membership.stores.append(
        colombia
    )

    db.commit()

    print(
        f"OK - Adrián Demo user_id={user.id}"
    )

    print(
        "OK - Diaglob: owner / todas las tiendas"
    )

    print(
        "OK - ACME: manager / ACME Colombia"
    )

    print(
        f"OK - Laura Agent user_id={agent_user.id}"
    )

    print(
        "OK - Laura Agent: solo Diaglob Colombia"
    )

finally:
    db.close()
