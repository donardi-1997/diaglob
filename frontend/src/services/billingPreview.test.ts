import assert from "node:assert/strict";
import test from "node:test";

import {
  getBillingUpgradePayableAmount,
  normalizeBillingUpgradePreview,
} from "./billingPreview.ts";


test("prefers Paddle charge result when present", () => {
  const payable = getBillingUpgradePayableAmount({
    currency_code: "USD",
    amount_due: "1200",
    update_summary: {
      result: {
        action: "charge",
        amount: "875",
        currency_code: "USD",
      },
    },
  });

  assert.deepEqual(payable, {
    amount: "875",
    currencyCode: "USD",
  });
});


test("falls back to amount_due when Paddle result is absent", () => {
  const payable = getBillingUpgradePayableAmount({
    currency_code: "USD",
    amount_due: "640",
  });

  assert.deepEqual(payable, {
    amount: "640",
    currencyCode: "USD",
  });
});


test("falls back to update summary charge when amount_due is absent", () => {
  const payable = getBillingUpgradePayableAmount({
    currency_code: null,
    amount_due: null,
    update_summary: {
      charge: {
        amount: "525",
        currency_code: "EUR",
      },
    },
  });

  assert.deepEqual(payable, {
    amount: "525",
    currencyCode: "EUR",
  });
});


test("returns null for zero or invalid payable amounts", () => {
  assert.equal(
    getBillingUpgradePayableAmount({
      currency_code: "USD",
      amount_due: "0",
    }),
    null,
  );

  assert.equal(
    getBillingUpgradePayableAmount({
      currency_code: "USD",
      amount_due: "not-a-number",
    }),
    null,
  );
});


test("normalizes a payable preview for the PlansPage contract", () => {
  const preview = normalizeBillingUpgradePreview({
    current_plan: "starter",
    target_plan: "growth",
    currency_code: "USD",
    amount_due: "740",
    update_summary: {},
  });

  assert.equal(preview.amount_due, "740");
  assert.deepEqual(preview.update_summary?.result, {
    action: "charge",
    amount: "740",
    currency_code: "USD",
  });
});


test("keeps a preview unchanged when there is nothing to charge", () => {
  const original = {
    currency_code: "USD",
    amount_due: "0",
  };

  const normalized = normalizeBillingUpgradePreview(original);

  assert.equal(normalized, original);
});
