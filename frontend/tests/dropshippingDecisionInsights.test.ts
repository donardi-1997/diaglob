import assert from "node:assert/strict";
import test from "node:test";

import {
  getDecisionInsightPresentation,
  nextSelectedProductId,
  normalizeDecisionInsightLocale,
  selectedProductIdFromInsight,
} from "../src/utils/dropshippingDecisionInsights.ts";

const baseInsight = {
  id: "stock_runway:123",
  type: "stock_runway",
  severity: "critical",
  product_id: 123,
  product_title: "Producto ganador",
  title_key: "stock_runway_critical",
  reason_key: "stock_runway_below_threshold",
  action_key: "replenish_stock",
  evidence: {
    inventory_quantity: 2,
    units_delivered: 10,
    units_per_day: 1,
    stock_runway_days: 2,
  },
} as const;

const knownContracts = [
  ["negative_margin", "gross_profit_below_zero", "review_price_and_cost"],
  ["low_margin", "gross_margin_below_threshold", "improve_unit_economics"],
  ["cost_incomplete", "cost_coverage_incomplete", "complete_product_costs"],
  ["delivery_risk", "delivery_rate_below_threshold", "review_fulfillment_quality"],
  ["cancellation_risk", "cancellation_rate_above_threshold", "review_confirmation_and_offer"],
  ["return_risk", "return_rate_above_threshold", "review_product_expectations"],
  ["stockout", "inventory_zero_with_sales", "replenish_stock"],
  ["revenue_concentration", "revenue_share_above_threshold", "diversify_product_mix"],
  ["profit_concentration", "profit_share_above_threshold", "diversify_profit_sources"],
  ["winner", "winner_quality_thresholds_met", "consider_scaling"],
  ["opportunity", "opportunity_quality_thresholds_met", "test_more_volume"],
] as const;

const locales = ["es", "en", "pt-BR"] as const;


test("normalizes supported analytics locales and falls back to Spanish", () => {
  assert.equal(normalizeDecisionInsightLocale("es-CO"), "es");
  assert.equal(normalizeDecisionInsightLocale("en-US"), "en");
  assert.equal(normalizeDecisionInsightLocale("pt-BR"), "pt-BR");
  assert.equal(normalizeDecisionInsightLocale("pt-PT"), "pt-BR");
  assert.equal(normalizeDecisionInsightLocale("fr-FR"), "es");
});


test("maps a critical stock insight without leaking backend keys", () => {
  const presentation = getDecisionInsightPresentation(baseInsight, "es");

  assert.equal(presentation.title, "Stock crítico");
  assert.equal(presentation.action, "Reponer inventario");
  assert.equal(presentation.severityLabel, "Crítico");
  assert.equal(presentation.title.includes("stock_runway"), false);
  assert.equal(presentation.reason.includes("stock_runway"), false);
  assert.equal(presentation.action.includes("replenish_stock"), false);
  assert.ok(presentation.evidence.length > 0);
  assert.ok(presentation.evidence.length <= 3);
});


test("all stable backend title, reason, and action keys have copy in every locale", () => {
  for (const locale of locales) {
    for (const [titleKey, reasonKey, actionKey] of knownContracts) {
      const presentation = getDecisionInsightPresentation(
        {
          ...baseInsight,
          id: `${titleKey}:123`,
          type: titleKey === "stockout" ? "stockout" : titleKey,
          severity: titleKey === "winner" ? "positive" : titleKey === "opportunity" ? "opportunity" : "warning",
          title_key: titleKey,
          reason_key: reasonKey,
          action_key: actionKey,
        },
        locale,
      );

      assert.ok(presentation.title.length > 0, `${locale}:${titleKey}`);
      assert.ok(presentation.reason.length > 0, `${locale}:${reasonKey}`);
      assert.ok(presentation.action.length > 0, `${locale}:${actionKey}`);
      assert.notEqual(presentation.title, titleKey);
      assert.notEqual(presentation.reason, reasonKey);
      assert.notEqual(presentation.action, actionKey);
    }
  }
});


test("both stock runway title variants have localized copy", () => {
  for (const locale of locales) {
    for (const titleKey of ["stock_runway_critical", "stock_runway_warning"] as const) {
      const presentation = getDecisionInsightPresentation(
        { ...baseInsight, title_key: titleKey, severity: titleKey.endsWith("critical") ? "critical" : "warning" },
        locale,
      );
      assert.notEqual(presentation.title, titleKey);
      assert.ok(presentation.title.length > 0);
    }
  }
});


test("unknown backend copy keys fail closed instead of leaking machine keys", () => {
  assert.throws(
    () => getDecisionInsightPresentation(
      { ...baseInsight, title_key: "unknown_backend_key" },
      "es",
    ),
    /Unknown decision insight copy key/,
  );
});


test("product selection helpers use explicit React state semantics", () => {
  assert.equal(selectedProductIdFromInsight(baseInsight), 123);
  assert.equal(selectedProductIdFromInsight({ ...baseInsight, product_id: null }), null);
  assert.equal(nextSelectedProductId(null, 123), 123);
  assert.equal(nextSelectedProductId(123, 123), null);
  assert.equal(nextSelectedProductId(456, 123), 123);
});
