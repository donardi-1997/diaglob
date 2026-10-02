import assert from "node:assert/strict";
import test from "node:test";

import { getMarketingCopy } from "../src/marketingCopy.ts";

const locales = ["es", "en", "pt-BR"] as const;

test("public marketing copy stays customer-facing in every supported language", () => {
  const developerJargon = [
    "rag",
    "runtime",
    "rbac",
    "tool node",
    "knowledge base",
    "trigger",
    "stack",
    "workspace",
  ];

  for (const locale of locales) {
    const copy = getMarketingCopy(locale);
    const visibleText = JSON.stringify({
      nav: copy.nav,
      hero: copy.hero,
      problem: copy.problem,
      outcomes: copy.outcomes,
      product: copy.product,
      integrations: copy.integrations,
      workflow: copy.workflow,
      pricing: copy.pricing,
      faq: copy.faq,
      final: copy.final,
      footer: copy.footer,
    }).toLowerCase();

    for (const jargon of developerJargon) {
      assert.equal(
        visibleText.includes(jargon),
        false,
        `${locale} marketing copy should not expose developer jargon: ${jargon}`,
      );
    }
  }
});

test("landing product story keeps six concrete customer jobs", () => {
  for (const locale of locales) {
    const copy = getMarketingCopy(locale);

    assert.equal(copy.product.cards.length, 6);
    assert.ok(copy.hero.primary.length > 0);
    assert.ok(copy.workflow.steps.length === 3);
  }
});
