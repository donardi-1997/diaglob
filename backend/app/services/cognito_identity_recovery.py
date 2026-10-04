import os

import boto3
from botocore.exceptions import ClientError
from sqlalchemy.orm import Session

from ..auth import COGNITO_USER_POOL_ID
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
    """Recover a local user after its old Cognito identity was deleted.

    The relink is intentionally fail-closed:
    - the current Cognito token must resolve to a verified email;
    - a local active user with that email must already exist;
    - if the local user points to another Cognito identity, that old identity
      must be confirmed deleted before the new sub can replace it.
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

    local_user = (
        db.query(User)
        .filter(
            User.email == email,
            User.active.is_(True),
        )
        .first()
    )

    if not local_user:
        return None

    previous_sub = local_user.external_auth_id

    if previous_sub == cognito_sub:
        return local_user

    if previous_sub:
        try:
            client.admin_get_user(
                UserPoolId=COGNITO_USER_POOL_ID,
                Username=previous_sub,
            )
        except ClientError as exc:
            code = (
                exc.response.get("Error", {})
                .get("Code")
            )
            if code != "UserNotFoundException":
                return None
        else:
            return None

    local_user.external_auth_id = cognito_sub
    db.commit()
    db.refresh(local_user)
    return local_user
