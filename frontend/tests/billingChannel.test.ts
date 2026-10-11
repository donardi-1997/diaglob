import assert from "node:assert/strict";
import test from "node:test";
import { billingChannel } from "../src/services/billingChannel.ts";

test("Shopify organizations never default to Paddle payment flow", () => {
  for (const channel of ["shopify", "SHOPIFY", " Shopify "]) {
    assert.equal(billingChannel(channel), "shopify");
    assert.notEqual(billingChannel(channel), "paddle");
  }
});

test("Paddle organizations retain existing payment flow", () => {
  assert.equal(billingChannel("paddle"), "paddle");
  assert.equal(billingChannel("PADDLE"), "paddle");
});

test("unknown, absent, malformed or future channels deny all payment UI", () => {
  for (const provider of [
    null, undefined, "", "unknown", "stripe", "shopify+Paddle",
    "paddle ", "none", "0",
  ]) {
    // Whitespace trimming is deliberately accepted for a valid Paddle value.
    if (provider === "paddle ") {
      assert.equal(billingChannel(provider), "paddle");
    } else {
      assert.equal(billingChannel(provider), "unverified");
    }
  }
});
