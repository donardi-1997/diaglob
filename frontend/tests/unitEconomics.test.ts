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
import {
  getUnitEconomicsContributionValues,
  getUnitEconomicsGrossProfitValue,
  isConfigurableUnitEconomicsReason,
  isMetaIntegrationActionReason,
  unitEconomicsReasonCopy,
  unitEconomicsSourceLabel,
} from "../src/utils/unitEconomics.ts";


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


test("payment method labels longer than backend schema are rejected before submit", () => {
  const result = validateUnitEconomicsConfig({
    ...baseConfig,
    payment_methods: [
      {
        payment_method: "x".repeat(51),
        fee_percent: null,
        fee_fixed: null,
        is_cod: false,
        cod_fee_percent: null,
      },
    ],
  });

  assert.equal(result.valid, false);
  assert.equal(result.error, "payment_method_too_long");
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


test("complete contribution exposes final profit and margin", () => {
  assert.deepEqual(
    getUnitEconomicsContributionValues({
      data_quality: { status: "complete" },
      contribution_profit: 271000,
      contribution_margin: 10.84,
      known_cost_subtotal: 2229000,
    }),
    { profit: 271000, margin: 10.84, complete: true },
  );
});


test("incomplete contribution never substitutes known cost subtotal for final profit", () => {
  assert.deepEqual(
    getUnitEconomicsContributionValues({
      data_quality: { status: "incomplete" },
      contribution_profit: null,
      contribution_margin: null,
      known_cost_subtotal: 2229000,
    }),
    { profit: null, margin: null, complete: false },
  );
});


test("gross profit is withheld when COGS is incomplete", () => {
  assert.equal(
    getUnitEconomicsGrossProfitValue({
      gross_profit: 900000,
      components: { cogs: { status: "missing" } },
    }),
    null,
  );
  assert.equal(
    getUnitEconomicsGrossProfitValue({
      gross_profit: 900000,
      components: { cogs: { status: "available" } },
    }),
    900000,
  );
});


test("source labels localize actual estimated missing and not applicable", () => {
  assert.equal(unitEconomicsSourceLabel("actual", "es"), "Real");
  assert.equal(unitEconomicsSourceLabel("estimated", "en"), "Estimated");
  assert.equal(unitEconomicsSourceLabel("missing", "pt-BR"), "Ausente");
  assert.equal(unitEconomicsSourceLabel("not_applicable", "es"), "No aplica");
});


test("known missing reasons map to safe localized copy", () => {
  assert.match(unitEconomicsReasonCopy("currency_mismatch", "es"), /moneda/i);
  assert.match(unitEconomicsReasonCopy("payment_fee_rule_missing", "en"), /payment/i);
});


test("missing reason shortcuts point only to the remediation that can solve them", () => {
  assert.equal(isMetaIntegrationActionReason("meta_not_connected"), true);
  assert.equal(isMetaIntegrationActionReason("credentials_unavailable"), true);
  assert.equal(isMetaIntegrationActionReason("bounded_date_range_required"), false);
  assert.equal(isConfigurableUnitEconomicsReason("shipping_estimate_missing"), true);
  assert.equal(isConfigurableUnitEconomicsReason("return_cost_missing"), true);
  assert.equal(isConfigurableUnitEconomicsReason("cogs_incomplete"), false);
  assert.equal(isConfigurableUnitEconomicsReason("bounded_date_range_required"), false);
});


test("unknown machine reason keys never leak raw to the UI", () => {
  const unknown = "provider_secret_internal_key";
  const copy = unitEconomicsReasonCopy(unknown, "es");
  assert.notEqual(copy, unknown);
  assert.equal(copy, "Falta información para completar este costo.");
});
