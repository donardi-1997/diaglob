import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

/* Guard against regressing to the old indigo / violet brand in migrated screens. */
const migratedPaths = [
  "frontend/src/stores-v2.css",
  "frontend/src/unit-economics-settings.css",
  "frontend/src/unit-economics-analytics.css",
  "frontend/src/post-sales.css",
  "frontend/src/workforce-catalog.css",
  "frontend/src/customer-risk-alert.css",
  "frontend/src/customer-risk-moderation.css",
  "frontend/src/customer-risk-moderation-analytics.css",
  "frontend/src/commerce-order-attribution.css",
  "frontend/src/customer-value-classifications.css",
  "frontend/src/customer-classification-analytics.css",
  "frontend/src/automation-customer-classification.css",
  "frontend/src/marketing.css",
  "frontend/src/design-system.css",
  "frontend/src/App.css",
  "frontend/src/pages/CustomersPage.tsx"
];

test("migrated screens must use semantic brand tokens instead of hardcoded indigo", () => {
  for (const path of migratedPaths) {
    const contents = readFileSync(new URL("../" + path.slice("frontend/".length), import.meta.url), "utf8");
    assert.doesNotMatch(contents, /#(?:6366f1|7c3aed|8b5cf6|a78bfa|a5b4fc|4c39d3|a855f7)\b/i, path);
    assert.doesNotMatch(contents, /(?:99,\s*102,\s*241|139,\s*92,\s*246|79,\s*70,\s*229)/, path);
  }
});

test("primary CTAs use paired accessible brand action colors", () => {
  for (const path of [
    "frontend/src/stores-v2.css",
    "frontend/src/unit-economics-settings.css",
    "frontend/src/commerce-order-attribution.css",
  ]) {
    const contents = readFileSync(new URL("../" + path.slice("frontend/".length), import.meta.url), "utf8");
    assert.match(contents, /var\(--brand-action-fg\)/, path);
    assert.match(contents, /var\(--brand-action\)/, path);
  }
});
