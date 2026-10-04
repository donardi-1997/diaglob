from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from app.api.auth import _relink_deleted_cognito_identity


def _client_error(code: str) -> ClientError:
    return ClientError(
        {
            "Error": {
                "Code": code,
                "Message": code,
            }
        },
        "AdminGetUser",
    )


def test_relinks_when_previous_cognito_identity_was_deleted():
    cognito = MagicMock()
    cognito.admin_get_user.side_effect = _client_error(
        "UserNotFoundException"
    )
    user = SimpleNamespace(
        external_auth_id="old-sub",
        name="Old Name",
        active=False,
    )

    recovered = _relink_deleted_cognito_identity(
        cognito=cognito,
        email_user=user,
        cognito_sub="new-sub",
        name="New Name",
    )

    assert recovered is True
    assert user.external_auth_id == "new-sub"
    assert user.name == "New Name"
    assert user.active is True


def test_does_not_relink_while_previous_identity_still_exists():
    cognito = MagicMock()
    cognito.admin_get_user.return_value = {
        "Username": "old-sub"
    }
    user = SimpleNamespace(
        external_auth_id="old-sub",
        name="Original",
        active=True,
    )

    recovered = _relink_deleted_cognito_identity(
        cognito=cognito,
        email_user=user,
        cognito_sub="new-sub",
        name="Attacker",
    )

    assert recovered is False
    assert user.external_auth_id == "old-sub"
    assert user.name == "Original"


def test_recovery_propagates_unexpected_cognito_errors():
    cognito = MagicMock()
    cognito.admin_get_user.side_effect = _client_error(
        "TooManyRequestsException"
    )
    user = SimpleNamespace(
        external_auth_id="old-sub",
        name="Original",
        active=True,
    )

    with pytest.raises(ClientError):
        _relink_deleted_cognito_identity(
            cognito=cognito,
            email_user=user,
            cognito_sub="new-sub",
            name="New Name",
        )
