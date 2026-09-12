import assert from "node:assert/strict";
import test from "node:test";

import {
  formatUnitEconomicsMoneyLabel,
  isValidUnitEconomicsMoney,
  isValidUnitEconomicsPercentage,
  normalizeUnitEconomicsPaymentMethod,
  serializeUnitEconomicsConfig,
  validateUnitEconomicsConfig,
  type UnitEconomicsConfig,
} from "../src/services/unitEconomics.ts";


const baseConfig: UnitEconomicsConfig = {
  store_id: 1,
  currency: "COP",
  outbound_shipping_cost: 15000,
  return_logistics_cost: 18000,
  default_payment_fee_percent: 3.5,
  default_payment_fee_fixed: 900,
  default_cod_fee_percent: 4,
  payment_methods: [],
};


test("unit economics money validation accepts null and non-negative finite values", () => {
  assert.equal(isValidUnitEconomicsMoney(null), true);
  assert.equal(isValidUnitEconomicsMoney(0), true);
  assert.equal(isValidUnitEconomicsMoney(15000), true);
  assert.equal(isValidUnitEconomicsMoney(-1), false);
  assert.equal(isValidUnitEconomicsMoney(Number.NaN), false);
  assert.equal(isValidUnitEconomicsMoney(Number.POSITIVE_INFINITY), false);
});


test("unit economics percentages are constrained to 0..100", () => {
  assert.equal(isValidUnitEconomicsPercentage(null), true);
  assert.equal(isValidUnitEconomicsPercentage(0), true);
  assert.equal(isValidUnitEconomicsPercentage(100), true);
  assert.equal(isValidUnitEconomicsPercentage(-0.01), false);
  assert.equal(isValidUnitEconomicsPercentage(100.01), false);
  assert.equal(isValidUnitEconomicsPercentage(Number.NaN), false);
});


test("payment method normalization is stable", () => {
  assert.equal(
    normalizeUnitEconomicsPaymentMethod("  Cash On Delivery  "),
    "cash on delivery",
  );
});


test("duplicate normalized payment methods are rejected before submit", () => {
  const result = validateUnitEconomicsConfig({
    ...baseConfig,
    payment_methods: [
      {
        payment_method: "COD",
        fee_percent: 2,
        fee_fixed: 500,
        is_cod: true,
        cod_fee_percent: 4,
      },
      {
        payment_method: " cod ",
        fee_percent: 3,
        fee_fixed: 0,
        is_cod: true,
        cod_fee_percent: 5,
      },
    ],
  });

  assert.equal(result.valid, false);
  assert.equal(result.error, "duplicate_payment_method");
});


test("fixed amount labels always expose the store currency", () => {
  assert.equal(
    formatUnitEconomicsMoneyLabel("Outbound shipping", "COP"),
    "Outbound shipping (COP)",
  );
});


test("serialization normalizes methods and strips COD percent when is_cod is false", () => {
  const payload = serializeUnitEconomicsConfig({
    ...baseConfig,
    payment_methods: [
      {
        payment_method: "  Card  ",
        fee_percent: 2.9,
        fee_fixed: 700,
        is_cod: false,
        cod_fee_percent: 9,
      },
    ],
  });

  assert.equal(payload.payment_methods[0].payment_method, "card");
  assert.equal(payload.payment_methods[0].cod_fee_percent, null);
});
