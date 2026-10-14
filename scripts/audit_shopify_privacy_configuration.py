"""Read-only audit of Shopify protected-data configuration in the source tree.

Run from repository root: python scripts/audit_shopify_privacy_configuration.py
This does NOT assert production deployment, Shopify Partners configuration, or
actual customer deletion/export completion.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OAUTH = ROOT / "backend/app/shopify_oauth.py"
ROUTES = ROOT / "backend/app/api/shopify.py"
SERVICE = ROOT / "backend/app/services/shopify_compliance_webhooks.py"
PROCESSING = ROOT / "backend/app/services/shopify_privacy_processing.py"
TOPICS = ("customers/data_request", "customers/redact", "shop/redact")
REQUIRED_SCOPES_FOR_PRESENT_ORDER_FLOWS = {"read_orders", "write_orders", "write_draft_orders"}
PROTECTED_SCOPES = {"read_customers", "read_orders"}


def scopes_from_ast(source: str) -> list[str]:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "SHOPIFY_SCOPES" for t in node.targets
        ):
            literal = ast.literal_eval(node.value)
            return [part.strip() for part in literal.split(",") if part.strip()]
    raise ValueError("SHOPIFY_SCOPES assignment not found or not static")


def route_has_hmac_check(source: str) -> bool:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "shopify_compliance_webhook":
            calls = [
                child.func.id
                for child in ast.walk(node)
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
            ]
            return "verify_shopify_webhook_hmac" in calls and "process_shopify_compliance_webhook" in calls
    return False


def main() -> int:
    oauth = OAUTH.read_text(encoding="utf-8")
    routes = ROUTES.read_text(encoding="utf-8")
    service = SERVICE.read_text(encoding="utf-8")
    processing = PROCESSING.read_text(encoding="utf-8")
    scopes = scopes_from_ast(oauth)
    findings = {
        "declared_oauth_scopes": scopes,
        "protected_scopes_declared": sorted(PROTECTED_SCOPES.intersection(scopes)),
        "necessary_order_scopes_declared": sorted(REQUIRED_SCOPES_FOR_PRESENT_ORDER_FLOWS.intersection(scopes)),
        "missing_order_scopes": sorted(REQUIRED_SCOPES_FOR_PRESENT_ORDER_FLOWS.difference(scopes)),
        "compliance_endpoint_present": '@router.post("/api/webhooks/shopify/compliance")' in routes,
        "hmac_verifier_called_in_compliance_handler": route_has_hmac_check(routes),
        "topics_present_in_compliance_processor": {topic: topic in service for topic in TOPICS},
        "durable_receipt_prepared": "stage_shopify_privacy_receipt_work_items" in service,
        "processor_explicitly_blocks_automatic_completion": '"fulfillment_complete": False' in processing,
        "production_webhook_subscriptions_verified": False,
        "shopify_partners_scopes_verified": False,
        "end_to_end_privacy_fulfillment_verified": False,
    }
    print(json.dumps(findings, indent=2, ensure_ascii=False))
    success = (
        not findings["missing_order_scopes"]
        and findings["compliance_endpoint_present"]
        and findings["hmac_verifier_called_in_compliance_handler"]
        and all(findings["topics_present_in_compliance_processor"].values())
        and findings["durable_receipt_prepared"]
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
