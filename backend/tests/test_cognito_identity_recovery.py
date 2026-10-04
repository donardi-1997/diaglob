from unittest.mock import MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import User
from app.services.cognito_identity_recovery import (
    relink_local_user_from_access_token,
)


engine = create_engine(
    "sqlite:///./test_cognito_identity_recovery.db",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def setup_function():
    Base.metadata.create_all(bind=engine)


def teardown_function():
    Base.metadata.drop_all(bind=engine)


def _current_user_response(email: str, *, verified: bool = True):
    return {
        "Username": "new-sub",
        "UserAttributes": [
            {"Name": "email", "Value": email},
            {
                "Name": "email_verified",
                "Value": "true" if verified else "false",
            },
        ],
    }


def test_relinks_verified_email_without_admin_cognito_permission():
    db = SessionLocal()
    try:
        user = User(
            email="merchant@example.com",
            name="Merchant",
            external_auth_id="old-sub",
            active=True,
        )
        db.add(user)
        db.commit()

        cognito = MagicMock()
        cognito.get_user.return_value = _current_user_response(
            "merchant@example.com"
        )

        recovered = relink_local_user_from_access_token(
            db,
            access_token="access-token",
            cognito_sub="new-sub",
            cognito=cognito,
        )

        assert recovered is not None
        assert recovered.id == user.id
        assert recovered.external_auth_id == "new-sub"
        cognito.admin_get_user.assert_not_called()
    finally:
        db.close()


def test_does_not_relink_unverified_email():
    db = SessionLocal()
    try:
        user = User(
            email="merchant@example.com",
            name="Merchant",
            external_auth_id="old-sub",
            active=True,
        )
        db.add(user)
        db.commit()

        cognito = MagicMock()
        cognito.get_user.return_value = _current_user_response(
            "merchant@example.com",
            verified=False,
        )

        recovered = relink_local_user_from_access_token(
            db,
            access_token="access-token",
            cognito_sub="new-sub",
            cognito=cognito,
        )

        assert recovered is None
        db.refresh(user)
        assert user.external_auth_id == "old-sub"
    finally:
        db.close()


def test_does_not_relink_when_current_sub_belongs_to_other_local_user():
    db = SessionLocal()
    try:
        target = User(
            email="merchant@example.com",
            name="Merchant",
            external_auth_id="old-sub",
            active=True,
        )
        conflict = User(
            email="other@example.com",
            name="Other",
            external_auth_id="new-sub",
            active=True,
        )
        db.add_all([target, conflict])
        db.commit()

        cognito = MagicMock()
        cognito.get_user.return_value = _current_user_response(
            "merchant@example.com"
        )

        recovered = relink_local_user_from_access_token(
            db,
            access_token="access-token",
            cognito_sub="new-sub",
            cognito=cognito,
        )

        assert recovered is None
        db.refresh(target)
        assert target.external_auth_id == "old-sub"
    finally:
        db.close()


def test_does_not_relink_when_email_is_not_unique_locally():
    db = SessionLocal()
    try:
        first = User(
            email="merchant@example.com",
            name="Merchant One",
            external_auth_id="old-sub-1",
            active=True,
        )
        second = User(
            email="merchant@example.com",
            name="Merchant Two",
            external_auth_id="old-sub-2",
            active=True,
        )
        db.add_all([first, second])
        db.commit()

        cognito = MagicMock()
        cognito.get_user.return_value = _current_user_response(
            "merchant@example.com"
        )

        recovered = relink_local_user_from_access_token(
            db,
            access_token="access-token",
            cognito_sub="new-sub",
            cognito=cognito,
        )

        assert recovered is None
    finally:
        db.close()
