import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function read(path: string): string {
  return readFileSync(new URL("../" + path, import.meta.url), "utf8");
}

const light = read("public/brand/diaglob-mark.svg");
const dark = read("public/brand/diaglob-mark-dark.svg");
const horizontal = read("public/brand/diaglob-logo-horizontal.svg");
const horizontalDark = read("public/brand/diaglob-logo-horizontal-dark.svg");

const geometry = (source: string): string[] =>
  Array.from(source.matchAll(/<path d="([^"]+)"/g), (match) => match[1]);

test("brand emblem preserves exact geometry across light and dark assets", () => {
  assert.deepEqual(geometry(light), geometry(dark));
  assert.equal(geometry(light).length, 2);
  assert.deepEqual(geometry(horizontal), geometry(horizontalDark));
});

test("new mark and horizontal logotypes no longer use blue or turquoise", () => {
  for (const svg of [light, dark, horizontal, horizontalDark]) {
    assert.doesNotMatch(svg, /#(?:06152f|123f8f|00e6c7|09bceb|165af5|64748b)\b/i);
    assert.match(svg, /#(?:F06B45|F67C5A)\b/i);
  }
  assert.match(light, /#191B19/);
  assert.match(dark, /#F7F4EE/);
});

test("theme-aware logo is used on all visible app surfaces", () => {
  const component = read("src/components/DiaglobBrandMark.tsx");
  assert.match(component, /diaglob-brand-mark-light/);
  assert.match(component, /diaglob-brand-mark-dark/);
  for (const path of [
    "src/components/AppShellV2.tsx",
    "src/components/FloatingCopilotButton.tsx",
    "src/pages/PublicLandingPage.tsx",
    "src/pages/LoginPage.tsx",
    "src/pages/SupportPage.tsx",
  ]) {
    const source = read(path);
    assert.match(source, /<DiaglobBrandMark\b/, path);
    assert.doesNotMatch(source, /src="\/brand\/diaglob-mark\.svg"/, path);
  }
});

test("favicon follows theme changes rather than only system preference", () => {
  const helper = read("src/services/brandFavicon.ts");
  const entry = read("src/main.tsx");
  assert.match(helper, /MutationObserver/);
  assert.match(helper, /diaglob-mark-dark\.svg/);
  assert.match(entry, /initializeBrandFavicon\(\)/);
  assert.match(read("index.html"), /data-diaglob-favicon/);
});
