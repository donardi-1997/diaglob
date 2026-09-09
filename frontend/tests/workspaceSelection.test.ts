import assert from "node:assert/strict";
import test from "node:test";

import {
  resolveOrganizationId,
  resolveStoreId,
} from "../src/hooks/workspaceSelection.ts";


test("keeps a saved organization when membership still allows it", () => {
  assert.equal(
    resolveOrganizationId([{ id: 1 }, { id: 2 }], "2"),
    "2",
  );
});


test("falls back to the first organization when saved id is stale", () => {
  assert.equal(
    resolveOrganizationId([{ id: 7 }, { id: 8 }], "99"),
    "7",
  );
});


test("returns an empty organization id when the user has no memberships", () => {
  assert.equal(resolveOrganizationId([], "3"), "");
});


test("keeps the selected store only when it is active", () => {
  assert.equal(
    resolveStoreId(
      [
        { id: 10, active: true },
        { id: 11, active: true },
      ],
      "11",
    ),
    "11",
  );
});


test("falls back to the first active store when selection is missing or inactive", () => {
  const stores = [
    { id: 20, active: false },
    { id: 21, active: true },
    { id: 22, active: true },
  ];

  assert.equal(resolveStoreId(stores, "20"), "21");
  assert.equal(resolveStoreId(stores, "999"), "21");
  assert.equal(resolveStoreId(stores, ""), "21");
});


test("returns an empty store id when no active stores exist", () => {
  assert.equal(
    resolveStoreId(
      [
        { id: 30, active: false },
        { id: 31, active: false },
      ],
      "30",
    ),
    "",
  );
});
