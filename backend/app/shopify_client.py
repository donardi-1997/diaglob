import os

import httpx


SHOPIFY_GRAPHQL_VERSION = (
    os.getenv(
        "SHOPIFY_API_VERSION", "2024-10"
    ).strip()
    or "2024-10"
)

SHOPIFY_TIMEOUT = 30


class ShopifyGraphQLClient:
    def __init__(
        self,
        shop_domain: str,
        access_token: str,
    ):
        if not shop_domain:
            raise ValueError(
                "shop_domain is required"
            )

        if not access_token:
            raise ValueError(
                "access_token is required"
            )

        self._shop_domain = (
            shop_domain.lower().strip()
        )

        self._access_token = access_token

        self._url = (
            f"https://{self._shop_domain}"
            f"/admin/api/"
            f"{SHOPIFY_GRAPHQL_VERSION}"
            f"/graphql.json"
        )

        self._headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": (
                self._access_token
            ),
        }

    def query(
        self,
        graphql_query: str,
        variables: dict | None = None,
    ) -> dict:
        payload: dict = {
            "query": graphql_query,
        }

        if variables:
            payload["variables"] = variables

        try:
            response = httpx.post(
                self._url,
                json=payload,
                headers=self._headers,
                timeout=SHOPIFY_TIMEOUT,
            )

        except httpx.TimeoutException as exc:
            raise ShopifyTimeoutError(
                "Shopify request timed out"
            ) from exc

        except httpx.HTTPError as exc:
            raise ShopifyAPIError(
                "Unable to reach Shopify"
            ) from exc

        if response.status_code == 401:
            raise ShopifyAuthError(
                "Invalid or expired Shopify "
                "access token"
            )

        if response.status_code == 402:
            raise ShopifyPlanError(
                "Shopify plan does not support "
                "this operation"
            )

        if response.status_code == 429:
            raise ShopifyRateLimitError(
                "Shopify rate limit exceeded"
            )

        if response.status_code >= 400:
            raise ShopifyAPIError(
                f"Shopify HTTP error "
                f"{response.status_code}"
            )

        try:
            data = response.json()
        except (
            ValueError,
            Exception,
        ) as exc:
            raise ShopifyAPIError(
                "Invalid JSON from Shopify"
            ) from exc

        errors = data.get("errors") or []

        if errors:
            first = errors[0] if errors else {}

            raise ShopifyGraphQLError(
                first.get(
                    "message",
                    "GraphQL error",
                )
            )

        return data.get("data", {})


class ShopifyAPIError(Exception):
    pass


class ShopifyAuthError(ShopifyAPIError):
    pass


class ShopifyPlanError(ShopifyAPIError):
    pass


class ShopifyRateLimitError(
    ShopifyAPIError
):
    pass


class ShopifyTimeoutError(ShopifyAPIError):
    pass


class ShopifyGraphQLError(
    ShopifyAPIError
):
    pass


class ShopifyUserError(
    ShopifyAPIError
):
    pass


# ============================================================
# DRAFT ORDER MUTATION
# ============================================================

DRAFT_ORDER_CREATE_MUTATION = """
mutation draftOrderCreate($input: DraftOrderInput!) {
  draftOrderCreate(input: $input) {
    draftOrder {
      id
      name
      totalPriceSet {
        shopMoney {
          amount
          currencyCode
        }
      }
      invoiceUrl
      lineItems(first: 100) {
        edges {
          node {
            id
          }
        }
      }
    }
    userErrors {
      field
      message
    }
  }
}
"""


ORDER_CREATE_MUTATION = """
mutation orderCreate($order: OrderCreateOrderInput!) {
  orderCreate(order: $order) {
    order {
      id
      name
      email
      phone
      note
      tags
      lineItems(first: 100) {
        nodes {
          variant {
            id
          }
          quantity
        }
      }
    }
    userErrors {
      field
      message
    }
  }
}
"""
