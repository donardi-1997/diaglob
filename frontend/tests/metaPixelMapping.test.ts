import assert from "node:assert/strict";
import test from "node:test";

import {convertShopifyEvent, EVENT_MAP} from "../../shopify/web-pixel-staging/src/mapping.mjs";

test("all five supported Shopify events map to Meta names with stable event IDs", () => {
  const names = Object.keys(EVENT_MAP);
  assert.deepEqual(names, [
    "page_viewed", "product_viewed", "product_added_to_cart",
    "checkout_started", "checkout_completed",
  ]);
  for (const name of names) {
    const data = convertShopifyEvent({id: "evt-A", name, timestamp: "2026-10-11T15:00:00Z"});
    assert.equal(data?.event_id, "shopify:evt-A");
    assert.equal(data?.event_name, EVENT_MAP[name]);
    assert.equal(data?.event_time, "2026-10-11T15:00:00Z");
    assert.equal("email" in data, false);
    assert.equal("ip" in data, false);
    assert.equal("customer" in data, false);
  }
});

test("purchases use actual checkout values and never invent USD", () => {
  const base = {id: "test-purchase-1", name: "checkout_completed"};
  const ok = convertShopifyEvent({...base, data: {
    checkout: {totalPrice: {amount: "49900", currencyCode: "COP"}, email: "ignored@example.com"},
  }});
  assert.equal(ok?.event_name, "Purchase");
  assert.equal(ok?.value, 49900);
  assert.equal(ok?.currency, "COP");
  assert.equal(JSON.stringify(ok).includes("ignored@example.com"), false);
  const empty = convertShopifyEvent({...base, data: {checkout: {}}});
  assert.equal(empty?.value, undefined);
  assert.equal(empty?.currency, undefined);
});

test("product and cart events never export names or personal data", () => {
  const viewed = convertShopifyEvent({
    name: "product_viewed", id: "pv1", data: {
      productVariant: {
        id: "gid://shopify/ProductVariant/123",
        product: {id: "gid://shopify/Product/42", title: "PRIVATE"},
        price: {amount: "15.40", currencyCode: "EUR"},
      },
    },
  });
  assert.equal(viewed?.content_ids?.[0], "gid://shopify/Product/42");
  assert.equal(viewed?.value, 15.4);
  assert.equal(JSON.stringify(viewed).includes("PRIVATE"), false);
});

test("invalid events, invalid currencies and missing event ids fail closed", () => {
  assert.equal(convertShopifyEvent({name: "customer_email_submitted", id: "1"}), null);
  assert.equal(convertShopifyEvent({name: "checkout_completed", id: ""}), null);
  const invalid = convertShopifyEvent({
    name: "checkout_completed", id: "test", data: {
      checkout: {totalPrice: {amount: "-100", currencyCode: "USD"}},
    },
  });
  assert.equal(invalid?.currency, undefined);
  assert.equal(invalid?.value, undefined);
});
