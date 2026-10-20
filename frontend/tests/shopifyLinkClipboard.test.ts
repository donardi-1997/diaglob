import assert from "node:assert/strict";
import test from "node:test";

import { copyShopifyLinkCode } from "../src/utils/shopifyLinkClipboard.ts";

test("copies exactly the current one-time Shopify code", async () => {
  const code = "synthetic-shopify-link-code-do-not-use";
  const copied: string[] = [];
  const result = await copyShopifyLinkCode(code, {
    writeText: async (text: string) => { copied.push(text); },
  });
  assert.equal(result, true);
  assert.deepEqual(copied, [code]);
});

test("fails without clipboard support and never changes the provided code", async () => {
  assert.equal(await copyShopifyLinkCode("synthetic", undefined), false);
  assert.equal(await copyShopifyLinkCode("", {
    writeText: async () => { throw new Error("should not be called"); },
  }), false);
});

test("clipboard rejection returns an error status without leaking code", async () => {
  const code = "synthetic-shopify-sensitive-link-code";
  let attempts = 0;
  assert.equal(await copyShopifyLinkCode(code, {
    writeText: async () => { attempts++; throw new Error("permission denied"); },
  }), false);
  assert.equal(attempts, 1);
});
