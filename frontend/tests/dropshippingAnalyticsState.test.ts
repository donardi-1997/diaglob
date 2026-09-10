import assert from "node:assert/strict";
import test from "node:test";

import {
  allDropshippingSectionsFailed,
  getFailedDropshippingSections,
  settledValue,
} from "../src/utils/dropshippingAnalyticsState.ts";


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


test("partial failures identify only unavailable sections", () => {
  const results: PromiseSettledResult<unknown>[] = [
    { status: "fulfilled", value: { total_orders: 10 } },
    { status: "rejected", reason: new Error("profitability failed") },
    { status: "fulfilled", value: [] },
    { status: "rejected", reason: new Error("orders failed") },
  ];

  assert.deepEqual(getFailedDropshippingSections(results), [
    "profitability",
    "orders",
  ]);
  assert.equal(
    allDropshippingSectionsFailed(getFailedDropshippingSections(results)),
    false,
  );
});


test("healthy results report no failed sections", () => {
  const results: PromiseSettledResult<unknown>[] = [
    { status: "fulfilled", value: {} },
    { status: "fulfilled", value: {} },
    { status: "fulfilled", value: [] },
    { status: "fulfilled", value: {} },
  ];

  assert.deepEqual(getFailedDropshippingSections(results), []);
  assert.equal(allDropshippingSectionsFailed([]), false);
});


test("all rejected results are recognized as a global failure", () => {
  const results: PromiseSettledResult<unknown>[] = [
    { status: "rejected", reason: "overview" },
    { status: "rejected", reason: "profitability" },
    { status: "rejected", reason: "products" },
    { status: "rejected", reason: "orders" },
  ];
  const failed = getFailedDropshippingSections(results);

  assert.deepEqual(failed, [
    "overview",
    "profitability",
    "products",
    "orders",
  ]);
  assert.equal(allDropshippingSectionsFailed(failed), true);
});
