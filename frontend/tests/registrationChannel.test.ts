import assert from "node:assert/strict";
import test from "node:test";

import { registrationChannelForReturnTo } from "../src/services/registrationChannel.ts";

test("ordinary signup and navigation use the direct Paddle signup origin", () => {
  for (const value of [
    undefined, null, "", "/app", "/plans", "/", "/login",
    "/shopify/install", "https://diaglob.tech/shopify/install?shop=test.myshopify.com",
    "//evil.com/shopify/install?shop=test.myshopify.com",
    "/shopify/install?shop=test.myshopify.com&next=https://evil.com",
    "/shopify/install?shop=test.myshopify.com&shop=other.myshopify.com",
    "/shopify/install?shop=https://evil.com",
    "/shopify/install?shop=test.myshopify.com#fragment",
  ]) {
    assert.equal(registrationChannelForReturnTo(value), "direct");
  }
});

test("a valid Shopify installation return path marks signup as pending only", () => {
  assert.equal(registrationChannelForReturnTo("/shopify/install?authorized=1"), "shopify_install");
  assert.equal(registrationChannelForReturnTo("/shopify/install?authorized=2"), "direct");
  assert.equal(
    registrationChannelForReturnTo("/shopify/install?shop=test.myshopify.com"),
    "shopify_install",
  );
  assert.equal(
    registrationChannelForReturnTo("/shopify/install?shop=TEST.MYSHOPIFY.COM"),
    "shopify_install",
  );
});
