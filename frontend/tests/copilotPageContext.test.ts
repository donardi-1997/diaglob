import test from "node:test";
import assert from "node:assert/strict";

import {
  buildCopilotPageContext,
  normalizeCopilotPageText,
} from "../src/services/copilotPageContext.ts";

test("normalizeCopilotPageText collapses whitespace and limits payload size", () => {
  assert.equal(
    normalizeCopilotPageText("  Clientes   activos\n\n\n  12 pedidos  "),
    "Clientes activos\n\n 12 pedidos",
  );
  assert.equal(normalizeCopilotPageText("abcdef", 4), "abcd");
});

test("buildCopilotPageContext keeps structured page metadata", () => {
  assert.deepEqual(
    buildCopilotPageContext(
      {
        page: "customers",
        pageLabel: "Clientes",
        entityType: "customer",
        entityId: 42,
        searchQuery: "ana",
      },
      "Cliente Ana\n3 pedidos",
    ),
    {
      page: "customers",
      page_label: "Clientes",
      entity_type: "customer",
      entity_id: 42,
      search_query: "ana",
      page_text: "Cliente Ana\n3 pedidos",
      context_source: "current_view",
      context_version: 1,
    },
  );
});
