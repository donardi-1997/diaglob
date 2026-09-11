"""One-off hardening for merchant trial edge cases."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected block not found in {path}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    replace_once(
        "backend/app/services/ai_usage_service.py",
        "from .trial_service import get_trial_entitlement, refresh_trial_state\n",
        "from .trial_service import refresh_trial_state\n",
    )

    replace_once(
        "backend/app/services/ai_usage_service.py",
        "    purchased_total, extra_remaining = _extra_credit_totals(db, organization_id)\n"
        "    remaining_included = max(included - used, 0)\n",
        "    purchased_total, extra_remaining = _extra_credit_totals(db, organization_id)\n"
        "    if plan == \"trial\":\n"
        "        # Trial is intentionally capped. Purchased/legacy credits cannot\n"
        "        # extend free usage beyond the 1,000-response allowance.\n"
        "        extra_remaining = 0\n"
        "    remaining_included = max(included - used, 0)\n",
    )

    replace_once(
        "backend/app/services/ai_usage_service.py",
        "    if used < included:\n"
        "        return {\n"
        "            \"available\": True,\n"
        "            \"source\": \"included\",\n"
        "            \"grant_id\": None,\n"
        "            \"remaining_included\": max(included - used, 0),\n"
        "        }\n\n"
        "    grant = (\n",
        "    if used < included:\n"
        "        return {\n"
        "            \"available\": True,\n"
        "            \"source\": \"included\",\n"
        "            \"grant_id\": None,\n"
        "            \"remaining_included\": max(included - used, 0),\n"
        "        }\n\n"
        "    if plan == \"trial\":\n"
        "        return {\n"
        "            \"available\": False,\n"
        "            \"source\": None,\n"
        "            \"grant_id\": None,\n"
        "            \"reason\": \"trial_ai_limit_reached\",\n"
        "        }\n\n"
        "    grant = (\n",
    )

    replace_once(
        "backend/app/services/shopify_service.py",
        "    except TrialIdentityAlreadyUsed as exc:\n"
        "        db.commit()\n"
        "        raise ShopifyConnectionError(str(exc)) from exc\n",
        "    except TrialIdentityAlreadyUsed as exc:\n"
        "        (\n"
        "            db.query(ShopifyOAuthState)\n"
        "            .filter(ShopifyOAuthState.id == oauth_state.id)\n"
        "            .update({ShopifyOAuthState.used: True}, synchronize_session=False)\n"
        "        )\n"
        "        db.commit()\n"
        "        raise ShopifyConnectionError(str(exc)) from exc\n",
    )

    print("Trial edge-case hardening applied")


if __name__ == "__main__":
    main()
