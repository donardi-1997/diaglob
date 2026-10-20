"""Regression checks for removing Shopify's unnecessary direct customer scope.

These are source-only guards. Order webhooks and protected customer data remain
subject to Shopify's separate PCD review; do not confuse scope reduction with
permission to process name, email, phone, or addresses.
"""
from __future__ import annotations

import ast
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import re
import tomllib

from app.shopify_oauth import SHOPIFY_SCOPES, build_authorization_url


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_customer_read_not_requested_by_oauth_or_app_config(monkeypatch):
    declared = tomllib.loads((REPO_ROOT / "shopify.app.toml").read_text(encoding="utf-8"))
    app_scopes = set(declared["access_scopes"]["scopes"].split(","))
    oauth_scopes = set(SHOPIFY_SCOPES.split(","))
    assert app_scopes == oauth_scopes
    assert len(app_scopes) == 7
    assert "read_customers" not in app_scopes
    assert {
        "read_products",
        "read_inventory",
        "read_orders",
        "write_orders",
        "write_draft_orders",
        "read_merchant_managed_fulfillment_orders",
        "write_merchant_managed_fulfillment_orders",
    } == app_scopes

    monkeypatch.setenv("SHOPIFY_CLIENT_ID", "synthetic-app")
    monkeypatch.setenv("SHOPIFY_REDIRECT_URI", "https://example.com/callback")
    query = parse_qs(urlsplit(build_authorization_url("dev.myshopify.com", "nonce")).query)
    assert set(query["scope"][0].split(",")) == app_scopes


def test_direct_customer_graphql_reads_not_used_by_shopify_client_modules():
    """Conservative static guard: customer(id:...) / customers(...) queries.

    Dynamic queries and other network clients need separate runtime auditing.
    """
    violations = []
    for path in (REPO_ROOT / "backend" / "app").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if "ShopifyGraphQLClient" not in source:
            continue
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            value = node.value
            if re.search(r"\bquery\b", value, flags=re.IGNORECASE) and re.search(
                r"\b(?:customer|customers)\s*\(", value, flags=re.IGNORECASE
            ):
                violations.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
    assert violations == [], "Review customer read scope before adding queries: " + ", ".join(violations)


def test_minimum_scope_does_not_disable_privacy_webhook_declarations():
    app = tomllib.loads((REPO_ROOT / "shopify.app.toml").read_text(encoding="utf-8"))
    topics = {
        topic
        for sub in app["webhooks"]["subscriptions"]
        for topic in sub.get("compliance_topics", [])
    }
    assert {"customers/data_request", "customers/redact", "shop/redact"} <= topics
