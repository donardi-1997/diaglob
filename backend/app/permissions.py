ROLE_PERMISSIONS = {
    "owner": {
        "*",
    },

    "manager": {
        "dashboard.read",
        "conversations.read",
        "conversations.write",
        "customers.read",
        "customers.write",
        "stores.read",
        "stores.write",
        "agents.read",
        "agents.write",
        "knowledge.read",
        "knowledge.write",
        "commerce.read",
        "commerce.write",
        "automations.read",
        "automations.write",
        "analytics.read",
        "users.read",
        "users.write",
        "billing.read",
        "billing.write",
    },

    "operator": {
        "dashboard.read",
        "conversations.read",
        "conversations.write",
        "customers.read",
        "stores.read",
    },

    "analyst": {
        "dashboard.read",
        "conversations.read",
        "customers.read",
        "stores.read",
        "analytics.read",
    },
}


def get_permissions_for_role(role: str) -> list[str]:
    permissions = ROLE_PERMISSIONS.get(
        role,
        set(),
    )

    if "*" in permissions:
        all_permissions = set()

        for role_permissions in ROLE_PERMISSIONS.values():
            all_permissions.update(
                permission
                for permission in role_permissions
                if permission != "*"
            )

        all_permissions.update(
            {
                "organization.write",
                "users.write",
                "billing.read",
                "billing.write",
            }
        )

        return sorted(all_permissions)

    return sorted(permissions)


def has_permission(
    role: str,
    permission: str,
) -> bool:
    permissions = ROLE_PERMISSIONS.get(
        role,
        set(),
    )

    return (
        "*" in permissions
        or permission in permissions
    )
