import assert from "node:assert/strict";
import test from "node:test";
import { classifyStoreAvailability } from "../src/services/storeAvailability.ts";

test("visible active stores do not need a second diagnostic", () => {
  assert.equal(classifyStoreAvailability(2, null, null), "available");
});

test("empty organization is different from unassigned memberships", () => {
  assert.equal(classifyStoreAvailability(0, 0, false), "no-active-stores");
  assert.equal(classifyStoreAvailability(0, 3, false), "unassigned");
});

test("unrestricted member with invisible stores requires backend diagnosis", () => {
  assert.equal(classifyStoreAvailability(0, 2, true), "mismatch");
});

test("failed/malformed organization lookup must never assert a root cause", () => {
  assert.equal(classifyStoreAvailability(0, null, false), "unknown");
  assert.equal(classifyStoreAvailability(0, -1, true), "unknown");
  assert.equal(classifyStoreAvailability(0, 1.5, false), "unknown");
  assert.equal(classifyStoreAvailability(0, 4, null), "unknown");
});
