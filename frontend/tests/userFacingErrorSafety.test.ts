import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";


const protectedSources = [
  "../src/pages/TeamPage.tsx",
  "../src/pages/StoresPage.tsx",
  "../src/components/AiUsagePackagesSection.tsx",
  "../src/components/AutomationRunExplorer.tsx",
  "../src/components/AutomationTemplates.tsx",
];


test("high-impact screens never render raw API error details", () => {
  for (const relativePath of protectedSources) {
    const source = readFileSync(new URL(relativePath, import.meta.url), "utf8");
    assert.equal(
      /(?:response\?\.|response\.)data\?\.detail|\.detail\s*\|\|/.test(source),
      false,
      `${relativePath} must use a safe, translated fallback`,
    );
  }
});
