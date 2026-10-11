import assert from "node:assert/strict";
import test from "node:test";
import { parseShopifyHostedPricingReturn } from "../src/services/shopifyBillingReturn.ts";

test("Shopify plan_handle only triggers provider re-verification", () => {
  const result = parseShopifyHostedPricingReturn(
    "?plan_handle=pro-forged&shop=attacker.myshopify.com&tab=billing",
  );

  assert.equal(result.shouldReverify, true);
  assert.equal(result.cleanedSearch, "tab=billing");
});

test("client-selected plan parameters cannot impersonate a Shopify return", () => {
  for (const search of [
    "",
    "?plan=pro",
    "?target_plan=growth",
    "?shop=merchant.myshopify.com",
  ]) {
    assert.equal(parseShopifyHostedPricingReturn(search).shouldReverify, false);
  }
});

test("duplicate or hostile return values are never propagated into cleaned URL", () => {
  const result = parseShopifyHostedPricingReturn(
    "?plan_handle=starter&plan_handle=pro&shop=x.myshopify.com&safe=1",
  );

  assert.equal(result.shouldReverify, true);
  assert.equal(result.cleanedSearch, "safe=1");
});
