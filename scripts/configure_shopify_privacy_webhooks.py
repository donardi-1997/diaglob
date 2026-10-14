#!/usr/bin/env python3
"""Add mandatory Shopify privacy topics to the EXISTING Shopify CLI app config.

This intentionally refuses to create a new shopify.app.toml: the current app
client_id, access scopes, and OAuth callback URLs must be preserved.
Run: python scripts/configure_shopify_privacy_webhooks.py path/to/shopify.app.toml
Then verify diff and execute `shopify app deploy` with the correct Shopify app.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import tomllib

TOPICS = ("customers/data_request", "customers/redact", "shop/redact")
URI = "https://api.diaglob.tech/api/webhooks/shopify/compliance"
BLOCK = (
    "\n# Mandatory Shopify privacy webhooks; served by FastAPI with raw-body HMAC validation.\n"
    "[[webhooks.subscriptions]]\n"
    f'compliance_topics = ["{TOPICS[0]}", "{TOPICS[1]}", "{TOPICS[2]}"]\n'
    f'uri = "{URI}"\n'
)


def configure(path: Path) -> bool:
    if not path.is_file():
        raise ValueError("Existing Shopify CLI configuration required; refusing to create placeholder app")
    original = path.read_text(encoding="utf-8")
    config = tomllib.loads(original)
    if not config.get("client_id") or not config.get("application_url"):
        raise ValueError("Not an initialized Shopify app config (client_id/application_url missing)")
    webhooks = config.get("webhooks")
    if not isinstance(webhooks, dict) or not webhooks.get("api_version"):
        raise ValueError("Existing [webhooks] with api_version required; do not guess the active version")
    existing = {
        topic: row.get("uri")
        for row in webhooks.get("subscriptions", [])
        for topic in row.get("compliance_topics", [])
    }
    unknown = sorted(set(existing) - set(TOPICS))
    if unknown:
        raise ValueError(f"Unknown compliance topics in config: {unknown}")
    mismatched = {key: value for key, value in existing.items() if value != URI}
    if mismatched:
        raise ValueError("Existing privacy webhook destinations differ; resolve manually before deployment")
    if all(existing.get(topic) == URI for topic in TOPICS):
        print("All privacy topics already configured; no changes")
        return False
    if existing:
        raise ValueError("Some compliance topics already declared; edit existing subscription manually")
    if not original.endswith("\n"):
        original += "\n"
    new_text = original + BLOCK
    parsed = tomllib.loads(new_text)
    configured = {
        topic
        for sub in parsed["webhooks"]["subscriptions"]
        if sub.get("uri") == URI
        for topic in sub.get("compliance_topics", [])
    }
    if not set(TOPICS).issubset(configured):
        raise ValueError("Post-write verification failed")
    path.write_text(new_text, encoding="utf-8")
    print(f"Configured three Shopify privacy webhooks in {path}")
    print("Not deployed: run `shopify app deploy` with the correct app credentials")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path, help="Existing shopify.app.toml path")
    arguments = parser.parse_args()
    try:
        configure(arguments.config)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Configuration not changed: {exc}\n")
