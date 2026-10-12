import assert from "node:assert/strict";
import test from "node:test";

import { createLatestRequestGuard } from "../src/services/latestRequestGuard.ts";

test("ignores stale store responses after a later reload", () => {
  const guard = createLatestRequestGuard();
  const first = guard.issue();
  const second = guard.issue();

  assert.equal(guard.isCurrent(first), false);
  assert.equal(guard.isCurrent(second), true);
});

test("invalidates a pending conversation response when a filter changes", () => {
  const guard = createLatestRequestGuard();
  const request = guard.issue();

  guard.invalidate();

  assert.equal(guard.isCurrent(request), false);
  assert.equal(guard.isCurrent(guard.issue()), true);
});

test("separate components do not share request generations", () => {
  const stores = createLatestRequestGuard();
  const inbox = createLatestRequestGuard();
  const storesRequest = stores.issue();
  const inboxRequest = inbox.issue();

  stores.invalidate();

  assert.equal(stores.isCurrent(storesRequest), false);
  assert.equal(inbox.isCurrent(inboxRequest), true);
});
