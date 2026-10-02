"""Shopify shop-scoped webhook subscription management."""

from __future__ import annotations

from urllib.parse import urljoin

from .models import CommerceConnection
from .settings import get_settings
from .shopify_client import ShopifyGraphQLClient, ShopifyUserError
from .shopify_security import decrypt_shopify_secret


ORDER_WEBHOOK_TOPICS = (
    "ORDERS_CREATE",
    "ORDERS_UPDATED",
    "ORDERS_CANCELLED",
)

LIST_WEBHOOKS_QUERY = """
query DiaglobWebhookSubscriptions {
  webhookSubscriptions(first: 100) {
    edges {
      node {
        id
        topic
        uri
      }
    }
  }
}
"""

CREATE_WEBHOOK_MUTATION = """
mutation DiaglobWebhookSubscriptionCreate(
  $topic: WebhookSubscriptionTopic!,
  $webhookSubscription: WebhookSubscriptionInput!
) {
  webhookSubscriptionCreate(
    topic: $topic,
    webhookSubscription: $webhookSubscription
  ) {
    webhookSubscription {
      id
      topic
      uri
    }
    userErrors {
      field
      message
    }
  }
}
"""


def shopify_webhook_callback_url() -> str:
    base = get_settings().public_api_base_url.rstrip("/") + "/"
    return urljoin(base, "api/webhooks/shopify")


def ensure_shopify_order_webhooks(
    connection: CommerceConnection,
) -> dict:
    """Ensure the three order lifecycle subscriptions exist for this shop.

    The operation is idempotent: existing subscriptions with the same topic and
    callback URI are retained, while only missing subscriptions are created.
    """

    token = decrypt_shopify_secret(
        connection.access_token_encrypted
    )
    client = ShopifyGraphQLClient(
        shop_domain=connection.external_store_url,
        access_token=token,
    )
    callback_url = shopify_webhook_callback_url()

    data = client.query(LIST_WEBHOOKS_QUERY)
    edges = (
        (data.get("webhookSubscriptions") or {})
        .get("edges")
        or []
    )

    existing = {
        (
            str((edge.get("node") or {}).get("topic") or ""),
            str((edge.get("node") or {}).get("uri") or ""),
        )
        for edge in edges
        if isinstance(edge, dict)
    }

    created: list[dict] = []
    retained: list[str] = []

    for topic in ORDER_WEBHOOK_TOPICS:
        if (topic, callback_url) in existing:
            retained.append(topic)
            continue

        mutation = client.query(
            CREATE_WEBHOOK_MUTATION,
            {
                "topic": topic,
                "webhookSubscription": {
                    "uri": callback_url,
                },
            },
        )
        result = mutation.get(
            "webhookSubscriptionCreate"
        ) or {}
        user_errors = result.get("userErrors") or []

        if user_errors:
            message = (
                user_errors[0].get("message")
                or "Unable to create Shopify webhook subscription"
            )
            raise ShopifyUserError(message)

        subscription = result.get("webhookSubscription") or {}
        if not subscription.get("id"):
            raise ShopifyUserError(
                "Shopify did not return the created webhook subscription"
            )

        created.append(
            {
                "id": subscription.get("id"),
                "topic": subscription.get("topic") or topic,
                "uri": subscription.get("uri") or callback_url,
            }
        )

    return {
        "ok": True,
        "callback_url": callback_url,
        "created": created,
        "retained": retained,
        "topics": list(ORDER_WEBHOOK_TOPICS),
    }
