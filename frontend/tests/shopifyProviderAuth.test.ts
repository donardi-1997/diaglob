import assert from "node:assert/strict";
import test from "node:test";
import { isShopifyProviderAuthFailure } from "../src/services/shopifyProviderAuth.ts";

test("Shopify credential renewal cannot trigger DIAGLOB login refresh", () => {
  assert.equal(isShopifyProviderAuthFailure(401, {code: "SHOPIFY_REAUTH_REQUIRED"}), true);
  assert.equal(isShopifyProviderAuthFailure(401, {code: "SHOPIFY_SHOP_IDENTITY_MISMATCH"}), true);
});

test("real DIAGLOB session expiry must continue using existing auth refresh", () => {
  assert.equal(isShopifyProviderAuthFailure(401, "Unauthorized"), false);
  assert.equal(isShopifyProviderAuthFailure(401, {code: "UNAUTHORIZED"}), false);
  assert.equal(isShopifyProviderAuthFailure(401, {code: "TOKEN_EXPIRED"}), false);
  assert.equal(isShopifyProviderAuthFailure(403, {code: "SHOPIFY_REAUTH_REQUIRED"}), false);
  assert.equal(isShopifyProviderAuthFailure(502, {code: "SHOPIFY_REAUTH_REQUIRED"}), false);
  assert.equal(isShopifyProviderAuthFailure(undefined, null), false);
  assert.equal(isShopifyProviderAuthFailure(401, {error: "invalid token"}), false);
});
