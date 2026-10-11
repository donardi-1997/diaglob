import assert from "node:assert/strict";
import test from "node:test";

import { resolveRequestStoreId } from "../src/services/storeRequestScope.ts";

test("explicit conversation filter overrides stale active store", () => {
  assert.equal(resolveRequestStoreId("10", "20", false), "20");
  assert.equal(resolveRequestStoreId("10", undefined, false), "10");
  assert.equal(resolveRequestStoreId(null, "20", false), "20");
});

test("unified inbox and selected conversation clear active-store header", () => {
  assert.equal(resolveRequestStoreId("10", "20", true), null);
  assert.equal(resolveRequestStoreId("10", undefined, true), null);
  assert.equal(resolveRequestStoreId(null, "20", true), null);
});

test("non-numeric or unsafe stored store IDs never become scope headers", () => {
  assert.equal(resolveRequestStoreId("abc", null, false), null);
  assert.equal(resolveRequestStoreId("-20", "1.5", false), null);
  assert.equal(resolveRequestStoreId("10", "no-store", false), "10");
  assert.equal(resolveRequestStoreId("", "", false), null);
  assert.equal(resolveRequestStoreId("0", "0", false), null);
});
