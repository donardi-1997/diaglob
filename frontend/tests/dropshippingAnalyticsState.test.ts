import assert from "node:assert/strict";
import test from "node:test";

import {
  DROPSHIPPING_ANALYTICS_SECTIONS,
  allDropshippingSectionsFailed,
  getFailedDropshippingSections,
  settledValue,
} from "../src/utils/dropshippingAnalyticsState.ts";


test("dropshipping analytics exposes six isolated sections", () => {
  assert.deepEqual(DROPSHIPPING_ANALYTICS_SECTIONS, [
    "overview",
    "profitability",
    "products",
    "orders",
    "insights",
    "unitEconomics",
  ]);
});


test("settledValue returns fulfilled data and hides rejected reasons", () => {
  const fulfilled: PromiseFulfilledResult<number> = {
    status: "fulfilled",
    value: 42,
  };
  const rejected: PromiseRejectedResult = {
    status: "rejected",
    reason: new Error("sensitive backend detail"),
  };

  assert.equal(settledValue(fulfilled), 42);
  assert.equal(settledValue(rejected), null);
});


test("partial failures identify only unavailable sections including unit economics", () => {
  const results: PromiseSettledResult<unknown>[] = [
    { status: "fulfilled", value: { total_orders: 10 } },
    { status: "rejected", reason: new Error("profitability failed") },
    { status: "fulfilled", value: [] },
    { status: "rejected", reason: new Error("orders failed") },
    { status: "fulfilled", value: { insights: [] } },
    { status: "rejected", reason: new Error("unit economics failed") },
  ];

  assert.deepEqual(getFailedDropshippingSections(results), [
    "profitability",
    "orders",
    "unitEconomics",
  ]);
  assert.equal(
    allDropshippingSectionsFailed(getFailedDropshippingSections(results)),
    false,
  );
});


test("unit economics can fail without hiding established analytics sections", () => {
  const results: PromiseSettledResult<unknown>[] = [
    { status: "fulfilled", value: {} },
    { status: "fulfilled", value: {} },
    { status: "fulfilled", value: [] },
    { status: "fulfilled", value: {} },
    { status: "fulfilled", value: { insights: [] } },
    { status: "rejected", reason: new Error("unit economics failed") },
  ];

  const failed = getFailedDropshippingSections(results);
  assert.deepEqual(failed, ["unitEconomics"]);
  assert.equal(allDropshippingSectionsFailed(failed), false);
});


test("insights can fail without hiding the other five analytics sections", () => {
  const results: PromiseSettledResult<unknown>[] = [
    { status: "fulfilled", value: {} },
    { status: "fulfilled", value: {} },
    { status: "fulfilled", value: [] },
    { status: "fulfilled", value: {} },
    { status: "rejected", reason: new Error("decision intelligence failed") },
    { status: "fulfilled", value: {} },
  ];

  const failed = getFailedDropshippingSections(results);
  assert.deepEqual(failed, ["insights"]);
  assert.equal(allDropshippingSectionsFailed(failed), false);
});


test("healthy results report no failed sections", () => {
  const results: PromiseSettledResult<unknown>[] = [
    { status: "fulfilled", value: {} },
    { status: "fulfilled", value: {} },
    { status: "fulfilled", value: [] },
    { status: "fulfilled", value: {} },
    { status: "fulfilled", value: { insights: [] } },
    { status: "fulfilled", value: {} },
  ];

  assert.deepEqual(getFailedDropshippingSections(results), []);
  assert.equal(allDropshippingSectionsFailed([]), false);
});


test("all six rejected results are recognized as a global failure", () => {
  const results: PromiseSettledResult<unknown>[] = [
    { status: "rejected", reason: "overview" },
    { status: "rejected", reason: "profitability" },
    { status: "rejected", reason: "products" },
    { status: "rejected", reason: "orders" },
    { status: "rejected", reason: "insights" },
    { status: "rejected", reason: "unitEconomics" },
  ];
  const failed = getFailedDropshippingSections(results);

  assert.deepEqual(failed, [
    "overview",
    "profitability",
    "products",
    "orders",
    "insights",
    "unitEconomics",
  ]);
  assert.equal(allDropshippingSectionsFailed(failed), true);
});
