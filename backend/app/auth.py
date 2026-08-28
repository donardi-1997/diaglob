import os

import jwt
from fastapi import HTTPException
from jwt import PyJWKClient


AWS_REGION = os.getenv(
    "AWS_REGION",
    "us-east-2",
)

COGNITO_USER_POOL_ID = os.getenv(
    "COGNITO_USER_POOL_ID",
    "us-east-2_t1eBd0ZSg",
)

COGNITO_CLIENT_ID = os.getenv(
    "COGNITO_CLIENT_ID",
    "7gas2mvvovukjpk05jhbku4303",
)

COGNITO_ISSUER = (
    f"https://cognito-idp.{AWS_REGION}.amazonaws.com/"
    f"{COGNITO_USER_POOL_ID}"
)

COGNITO_JWKS_URL = (
    f"{COGNITO_ISSUER}/.well-known/jwks.json"
)

jwks_client = PyJWKClient(
    COGNITO_JWKS_URL
)


def verify_cognito_access_token(
    token: str,
) -> dict:
    try:
        signing_key = (
            jwks_client.get_signing_key_from_jwt(
                token
            )
        )

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=COGNITO_ISSUER,
            options={
                "verify_aud": False,
            },
            leeway=60,
        )

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Token expired",
        )

    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
        )

    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Unable to validate token",
        )

    if payload.get("token_use") != "access":
        raise HTTPException(
            status_code=401,
            detail="Invalid token type",
        )

    if (
        payload.get("client_id")
        != COGNITO_CLIENT_ID
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid token client",
        )

    if not payload.get("sub"):
        raise HTTPException(
            status_code=401,
            detail="Token subject missing",
        )

    return payload
