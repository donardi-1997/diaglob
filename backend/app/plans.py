PLAN_LIMITS = {
    "none": {
        "name": "Sin plan",
        "active_stores": 0,
    },
    "starter": {
        "name": "Starter",
        "active_stores": 1,
    },
    "growth": {
        "name": "Growth",
        "active_stores": 2,
    },
    "pro": {
        "name": "Pro",
        "active_stores": 3,
    },
    "scale": {
        "name": "Scale",
        "active_stores": 5,
    },
}


DEFAULT_PLAN = "none"


def get_plan(plan: str | None):
    normalized = (
        plan or DEFAULT_PLAN
    ).strip().lower()

    return PLAN_LIMITS.get(
        normalized,
        PLAN_LIMITS[DEFAULT_PLAN],
    )


def get_active_store_limit(
    plan: str | None,
):
    return get_plan(plan)[
        "active_stores"
    ]
