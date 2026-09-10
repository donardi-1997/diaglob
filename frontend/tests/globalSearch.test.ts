import assert from "node:assert/strict";
import test from "node:test";

import {
  globalSearchMatches,
  normalizeGlobalSearchQuery,
} from "../src/services/globalSearchHelpers.ts";


test("normalizes whitespace, case and accents for global search", () => {
  assert.equal(
    normalizeGlobalSearchQuery("  Medellín  "),
    "medellin",
  );
  assert.equal(
    normalizeGlobalSearchQuery("CAMISETA ÁZUL"),
    "camiseta azul",
  );
});


test("matches user queries against searchable entity fields", () => {
  assert.equal(
    globalSearchMatches("guerra", ["Adrián Guerra", "+57 300 000 0000"]),
    true,
  );
  assert.equal(
    globalSearchMatches("a335", ["Sandalia", "SKU-A335"]),
    true,
  );
  assert.equal(
    globalSearchMatches("pedido 999", ["#120", "Sandalia"]),
    false,
  );
});
