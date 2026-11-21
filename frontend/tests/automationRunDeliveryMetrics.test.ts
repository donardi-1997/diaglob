import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";


test("campaign run explorer renders existing WhatsApp delivery metrics", () => {
  const source = readFileSync(
    new URL("../src/components/AutomationRunExplorer.tsx", import.meta.url),
    "utf8",
  );

  for (const key of [
    "delivery_metrics",
    "autoDelivered",
    "autoRead",
    "autoDeliveryRate",
    "autoReadRate",
  ]) {
    assert.match(source, new RegExp(key));
  }
});
