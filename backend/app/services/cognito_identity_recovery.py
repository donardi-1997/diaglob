import os

import boto3
from botocore.exceptions import ClientError
from sqlalchemy.orm import Session

from ..models import User


def _cognito_client():
    region = (
        os.getenv("AWS_REGION")
        or os.getenv("AWS_DEFAULT_REGION")
        or "us-east-2"
    )
    return boto3.client(
        "cognito-idp",
        region_name=region,
    )


def relink_local_user_from_access_token(
    db: Session,
    *,
    access_token: str,
    cognito_sub: str,
    cognito=None,
) -> User | None:
    """Recover a local Diaglob user from a verified Cognito identity.

    This intentionally avoids Cognito admin APIs so the normal login path
    does not depend on instance IAM permissions.

    The relink is allowed only when:
    - Cognito accepts the access token;
    - Cognito says the email is verified;
    - exactly one active local user owns that email;
    - no different local user is already linked to the current Cognito sub.
    """
    client = cognito or _cognito_client()

    try:
        current = client.get_user(
            AccessToken=access_token,
        )
    except ClientError:
        return None

    attributes = {
        item["Name"]: item["Value"]
        for item in current.get("UserAttributes", [])
    }

    email = attributes.get("email", "").strip().lower()
    email_verified = (
        attributes.get("email_verified", "false").lower()
        == "true"
    )

    if not email or not email_verified:
        return None

    email_users = (
        db.query(User)
        .filter(
            User.email == email,
            User.active.is_(True),
        )
        .all()
    )

    if len(email_users) != 1:
        return None

    local_user = email_users[0]

    conflicting_sub_user = (
        db.query(User)
        .filter(
            User.external_auth_id == cognito_sub,
            User.id != local_user.id,
        )
        .first()
    )

    if conflicting_sub_user:
        return None

    if local_user.external_auth_id != cognito_sub:
        local_user.external_auth_id = cognito_sub
        db.commit()
        db.refresh(local_user)

    return local_user
