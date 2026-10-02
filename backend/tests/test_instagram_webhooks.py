from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.instagram_models import InstagramConnection
from app.models import Conversation, Message, Organization, Store
from app.services.instagram_webhooks import process_webhook_payload


def test_instagram_webhook_creates_shared_inbox_conversation():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        org = Organization(
            name="Instagram Org",
            slug="instagram-org",
            plan="growth",
            subscription_status="active",
            active=True,
        )
        db.add(org)
        db.flush()
        store = Store(
            organization_id=org.id,
            name="Instagram Store",
            slug="instagram-store",
            country_code="CO",
            currency="COP",
            timezone="America/Bogota",
            default_language="es",
            active=True,
            deleted=False,
        )
        db.add(store)
        db.flush()
        db.add(
            InstagramConnection(
                organization_id=org.id,
                store_id=store.id,
                instagram_account_id="ig-business-1",
                page_id="page-1",
                username="diaglob_test",
                access_token_encrypted="encrypted-for-test",
                status="connected",
            )
        )
        db.commit()

        result = process_webhook_payload(
            db,
            {
                "object": "instagram",
                "entry": [
                    {
                        "id": "ig-business-1",
                        "messaging": [
                            {
                                "sender": {"id": "igsid-123"},
                                "recipient": {"id": "ig-business-1"},
                                "message": {
                                    "mid": "mid-1",
                                    "text": "Hola",
                                },
                            }
                        ],
                    }
                ],
            },
        )

        assert len(result["inbound_conversation_ids"]) == 1
        conversation = db.query(Conversation).one()
        assert conversation.channel == "Instagram"
        assert conversation.customer.phone == "instagram:igsid-123"
        message = db.query(Message).one()
        assert message.provider == "instagram"
        assert message.external_message_id == "mid-1"

        duplicate = process_webhook_payload(
            db,
            {
                "object": "instagram",
                "entry": [
                    {
                        "id": "ig-business-1",
                        "messaging": [
                            {
                                "sender": {"id": "igsid-123"},
                                "message": {
                                    "mid": "mid-1",
                                    "text": "Hola",
                                },
                            }
                        ],
                    }
                ],
            },
        )
        assert duplicate["new_messages"] == []
        assert db.query(Message).count() == 1
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
