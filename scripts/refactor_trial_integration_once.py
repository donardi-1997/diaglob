"""One-off integration of merchant trial lifecycle into existing application seams."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected block not found in {path}: {old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    # Registration: every newly created organization receives one pending trial.
    replace_once(
        "backend/app/api/auth.py",
        "from ..permissions import get_permissions_for_role\n",
        "from ..permissions import get_permissions_for_role\n"
        "from ..services.trial_service import create_pending_trial\n",
    )
    replace_once(
        "backend/app/api/auth.py",
        "        db.add(organization)\n        db.flush()\n\n        membership = (\n",
        "        db.add(organization)\n        db.flush()\n\n"
        "        create_pending_trial(\n"
        "            db,\n"
        "            organization,\n"
        "            now=datetime.utcnow(),\n"
        "        )\n\n"
        "        membership = (\n",
    )

    # Permission boundary: trial_pending may only bootstrap stores; trialing is active.
    replace_once(
        "backend/app/api/deps.py",
        "from ..permissions import has_permission\n",
        "from ..permissions import has_permission\n"
        "from ..services.trial_service import (\n"
        "    pending_trial_can_bootstrap_store,\n"
        "    refresh_trial_state,\n"
        ")\n",
    )
    replace_once(
        "backend/app/api/deps.py",
        "    def dependency(\n"
        "        request: Request,\n"
        "        membership: OrganizationMembership = Depends(\n"
        "            get_current_membership\n"
        "        ),\n"
        "    ):\n",
        "    def dependency(\n"
        "        request: Request,\n"
        "        membership: OrganizationMembership = Depends(\n"
        "            get_current_membership\n"
        "        ),\n"
        "        db: Session = Depends(get_db),\n"
        "    ):\n",
    )
    old_gate = '''            organization = (\n                membership.organization\n            )\n\n            plan = (\n                organization.plan\n                or "none"\n            ).strip().lower()\n\n            subscription_status = (\n                organization.subscription_status\n                or ""\n            ).strip().lower()\n\n            active_plan = (\n                plan in {\n                    "starter",\n                    "growth",\n                    "pro",\n                    "scale",\n                    "agency",\n                    "enterprise",\n                }\n                and subscription_status in {\n                    "active",\n                    "trialing",\n                }\n            )\n\n            if not active_plan:\n                raise HTTPException(\n                    status_code=402,\n                    detail={\n                        "code": "PLAN_REQUIRED",\n                        "message": (\n                            "No tienes un plan activo. "\n                            "Elige un plan para utilizar "\n                            "esta función."\n                        ),\n                    },\n                )\n'''
    new_gate = '''            organization = membership.organization\n            refresh_trial_state(db, organization)\n\n            plan = (organization.plan or "none").strip().lower()\n            subscription_status = (\n                organization.subscription_status or ""\n            ).strip().lower()\n\n            paid_active = (\n                plan in {\n                    "starter",\n                    "growth",\n                    "pro",\n                    "scale",\n                    "agency",\n                    "enterprise",\n                }\n                and subscription_status in {"active", "trialing"}\n            )\n            trial_active = (\n                plan == "trial"\n                and subscription_status == "trialing"\n            )\n            trial_bootstrap = (\n                permission == "stores.write"\n                and pending_trial_can_bootstrap_store(db, organization)\n            )\n\n            if not (paid_active or trial_active or trial_bootstrap):\n                if subscription_status == "trial_pending":\n                    code = "TRIAL_ACTIVATION_REQUIRED"\n                    message = (\n                        "Conecta tu primera tienda para iniciar tus 7 días gratis."\n                    )\n                elif subscription_status == "trial_expired":\n                    code = "TRIAL_EXPIRED"\n                    message = (\n                        "Tu prueba gratuita terminó. Elige un plan para continuar."\n                    )\n                elif subscription_status == "trial_blocked":\n                    code = "TRIAL_NOT_ELIGIBLE"\n                    message = (\n                        "Esta cuenta no es elegible para otra prueba gratuita. "\n                        "Elige un plan para continuar."\n                    )\n                else:\n                    code = "PLAN_REQUIRED"\n                    message = (\n                        "No tienes un plan activo. "\n                        "Elige un plan para utilizar esta función."\n                    )\n\n                raise HTTPException(\n                    status_code=402,\n                    detail={"code": code, "message": message},\n                )\n'''
    replace_once("backend/app/api/deps.py", old_gate, new_gate)

    # Store creation must honor the active-store limit too, including Trial=1.
    replace_once(
        "backend/app/api/stores.py",
        "    store = Store(\n",
        "    if payload.active:\n"
        "        ensure_active_store_capacity(\n"
        "            db,\n"
        "            membership.organization_id,\n"
        "        )\n\n"
        "    store = Store(\n",
    )

    # Shopify: verified OAuth identity activates/claims the trial before connection commit.
    replace_once(
        "backend/app/services/shopify_service.py",
        "from ..shopify_security import encrypt_shopify_secret\n",
        "from ..shopify_security import encrypt_shopify_secret\n"
        "from .trial_service import (\n"
        "    TrialIdentityAlreadyUsed,\n"
        "    activate_trial_for_verified_store,\n"
        ")\n",
    )
    replace_once(
        "backend/app/services/shopify_service.py",
        "        return _shopify_connect_frontend_url(connected=False)\n\n"
        "    now = datetime.utcnow()\n",
        "        return _shopify_connect_frontend_url(connected=False)\n\n"
        "    try:\n"
        "        activate_trial_for_verified_store(\n"
        "            db,\n"
        "            organization_id=oauth_state.organization_id,\n"
        "            store_id=oauth_state.store_id,\n"
        "            provider=\"shopify\",\n"
        "            external_identity=normalized_shop,\n"
        "        )\n"
        "    except TrialIdentityAlreadyUsed as exc:\n"
        "        db.commit()\n"
        "        raise ShopifyConnectionError(str(exc)) from exc\n\n"
        "    now = datetime.utcnow()\n",
    )
    replace_once(
        "backend/app/api/shopify.py",
        "        if code == \"SHOPIFY_NOT_CONFIGURED\":\n"
        "            raise HTTPException(status_code=503, detail={\"code\": code, \"message\": str(exc)})\n",
        "        if code == \"SHOPIFY_NOT_CONFIGURED\":\n"
        "            raise HTTPException(status_code=503, detail={\"code\": code, \"message\": str(exc)})\n"
        "        if code in {\"TRIAL_STORE_ALREADY_USED\", \"TRIAL_NOT_AVAILABLE\"}:\n"
        "            raise HTTPException(\n"
        "                status_code=409,\n"
        "                detail={\n"
        "                    \"code\": code,\n"
        "                    \"message\": (\n"
        "                        \"Esta tienda ya utilizó una prueba gratuita de DIAGLOB. \"\n"
        "                        \"Puedes conectarla con un plan de pago.\"\n"
        "                    ),\n"
        "                },\n"
        "            )\n",
    )
    replace_once(
        "backend/app/api/shopify.py",
        "    except (ShopifyOAuthError, ShopifyProviderError) as exc:\n",
        "    except (ShopifyOAuthError, ShopifyProviderError, ShopifyConnectionError) as exc:\n",
    )

    # Nuvemshop: claim verified store ID and provide friendly duplicate/trial errors.
    replace_once(
        "backend/app/services/nuvemshop_service.py",
        "from ..nuvemshop_security import encrypt_secret, decrypt_secret\n",
        "from ..nuvemshop_security import encrypt_secret, decrypt_secret\n"
        "from .trial_service import (\n"
        "    TrialIdentityAlreadyUsed,\n"
        "    activate_trial_for_verified_store,\n"
        ")\n",
    )
    replace_once(
        "backend/app/services/nuvemshop_service.py",
        "    if existing:\n"
        "        raise NuvemshopConnectionError(\"Commerce connection already exists for this store\")\n\n"
        "    now = datetime.utcnow()\n",
        "    if existing:\n"
        "        raise NuvemshopConnectionError(\"COMMERCE_ALREADY_CONNECTED\")\n\n"
        "    conflicting = (\n"
        "        db.query(CommerceConnection)\n"
        "        .filter(\n"
        "            CommerceConnection.provider == \"nuvemshop\",\n"
        "            CommerceConnection.external_store_url == str(nuvemshop_store_id),\n"
        "        )\n"
        "        .first()\n"
        "    )\n"
        "    if conflicting:\n"
        "        raise NuvemshopConnectionError(\"NUVEMSHOP_STORE_ALREADY_CONNECTED\")\n\n"
        "    try:\n"
        "        activate_trial_for_verified_store(\n"
        "            db,\n"
        "            organization_id=organization_id,\n"
        "            store_id=store_id,\n"
        "            provider=\"nuvemshop\",\n"
        "            external_identity=str(nuvemshop_store_id),\n"
        "        )\n"
        "    except TrialIdentityAlreadyUsed as exc:\n"
        "        db.commit()\n"
        "        raise NuvemshopConnectionError(str(exc)) from exc\n\n"
        "    now = datetime.utcnow()\n",
    )
    replace_once(
        "backend/app/api/nuvemshop.py",
        "            \"COMMERCE_ALREADY_CONNECTED\": (409, {\"code\": code, \"message\": \"Esta tienda ya tiene una integración de comercio.\"}),\n",
        "            \"COMMERCE_ALREADY_CONNECTED\": (409, {\"code\": code, \"message\": \"Esta tienda ya tiene una integración de comercio.\"}),\n"
        "            \"NUVEMSHOP_STORE_ALREADY_CONNECTED\": (409, {\"code\": code, \"message\": \"Esta tienda Nuvemshop ya está conectada a DIAGLOB.\"}),\n"
        "            \"TRIAL_STORE_ALREADY_USED\": (409, {\"code\": code, \"message\": \"Esta tienda ya utilizó una prueba gratuita de DIAGLOB. Puedes conectarla con un plan de pago.\"}),\n"
        "            \"TRIAL_NOT_AVAILABLE\": (409, {\"code\": code, \"message\": \"La prueba gratuita ya no está disponible para esta cuenta.\"}),\n",
    )

    # Organization payload exposes trial state and lazily expires/converts it.
    replace_once(
        "backend/app/api/organizations.py",
        "from ..permissions import get_permissions_for_role\n",
        "from ..permissions import get_permissions_for_role\n"
        "from ..services.trial_service import serialize_trial_status\n",
    )
    replace_once(
        "backend/app/api/organizations.py",
        "    organization = membership.organization\n\n    plan = get_plan(\n",
        "    organization = membership.organization\n"
        "    trial_status = serialize_trial_status(db, organization)\n\n"
        "    plan = get_plan(\n",
    )
    replace_once(
        "backend/app/api/organizations.py",
        "        \"plan\": organization.plan,\n        \"plan_name\": plan[\"name\"],\n",
        "        \"plan\": organization.plan,\n"
        "        \"plan_name\": plan[\"name\"],\n"
        "        \"subscription_status\": organization.subscription_status,\n"
        "        \"trial\": trial_status,\n",
    )

    # AI usage: trial capacity is scoped to the seven-day entitlement window and
    # webhook-driven AI is blocked even though it bypasses HTTP permission deps.
    replace_once(
        "backend/app/services/ai_usage_service.py",
        "from ..plan_limits import get_organization_limits\n",
        "from ..plan_limits import get_organization_limits\n"
        "from .trial_service import get_trial_entitlement, refresh_trial_state\n",
    )
    replace_once(
        "backend/app/services/ai_usage_service.py",
        "    if not organization:\n"
        "        return {\"error\": \"Organization not found\"}\n\n"
        "    if billing_period_start is None and billing_period_end is None:\n"
        "        billing_period_start, billing_period_end = get_ai_usage_window()\n\n"
        "    plan = (organization.plan or \"none\").strip().lower()\n",
        "    if not organization:\n"
        "        return {\"error\": \"Organization not found\"}\n\n"
        "    trial_entitlement = refresh_trial_state(db, organization)\n"
        "    plan = (organization.plan or \"none\").strip().lower()\n\n"
        "    if billing_period_start is None and billing_period_end is None:\n"
        "        if (\n"
        "            plan == \"trial\"\n"
        "            and trial_entitlement is not None\n"
        "            and trial_entitlement.started_at is not None\n"
        "        ):\n"
        "            billing_period_start = trial_entitlement.started_at\n"
        "            billing_period_end = trial_entitlement.ends_at\n"
        "        else:\n"
        "            billing_period_start, billing_period_end = get_ai_usage_window()\n",
    )
    replace_once(
        "backend/app/services/ai_usage_service.py",
        "    if not organization:\n"
        "        return {\"available\": False, \"source\": None, \"reason\": \"organization_not_found\"}\n\n"
        "    start, end = get_ai_usage_window(now)\n"
        "    included = get_organization_limits(organization).included_ai_responses\n",
        "    if not organization:\n"
        "        return {\"available\": False, \"source\": None, \"reason\": \"organization_not_found\"}\n\n"
        "    trial_entitlement = refresh_trial_state(db, organization, now=now)\n"
        "    plan = (organization.plan or \"none\").strip().lower()\n"
        "    subscription_status = (\n"
        "        organization.subscription_status or \"\"\n"
        "    ).strip().lower()\n\n"
        "    if subscription_status in {\n"
        "        \"trial_pending\",\n"
        "        \"trial_expired\",\n"
        "        \"trial_blocked\",\n"
        "    }:\n"
        "        return {\n"
        "            \"available\": False,\n"
        "            \"source\": None,\n"
        "            \"grant_id\": None,\n"
        "            \"reason\": subscription_status,\n"
        "        }\n\n"
        "    if (\n"
        "        plan == \"trial\"\n"
        "        and subscription_status == \"trialing\"\n"
        "        and trial_entitlement is not None\n"
        "        and trial_entitlement.started_at is not None\n"
        "    ):\n"
        "        start = trial_entitlement.started_at\n"
        "        end = trial_entitlement.ends_at\n"
        "    else:\n"
        "        start, end = get_ai_usage_window(now)\n\n"
        "    included = get_organization_limits(organization).included_ai_responses\n",
    )

    # Frontend organization contract receives nested trial metadata.
    replace_once(
        "frontend/src/services/organizations.ts",
        "  plan_name: string;\n  billing_period_months: number;\n",
        "  plan_name: string;\n"
        "  subscription_status: string | null;\n"
        "  trial: {\n"
        "    status: string;\n"
        "    started_at: string | null;\n"
        "    ends_at: string | null;\n"
        "    days_remaining: number | null;\n"
        "    ai_response_limit: number;\n"
        "  };\n"
        "  billing_period_months: number;\n",
    )

    # Alembic head expectation was intentionally advanced with the new migration.
    print("Merchant trial integration applied")


if __name__ == "__main__":
    main()
