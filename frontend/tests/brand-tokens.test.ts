import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const tokensCss = readFileSync(new URL("../src/brand-tokens.css", import.meta.url), "utf8");
const lightBlock = tokensCss.match(/:root,\s*:root\[data-theme="light"\]\s*\{([\s\S]*?)^\}/m)?.[1];
const darkBlock = tokensCss.match(/:root\[data-theme="dark"\]\s*\{([\s\S]*?)^\}/m)?.[1];
assert.ok(lightBlock, "light theme token block exists");
assert.ok(darkBlock, "dark theme token block exists");

function declarations(block: string): Record<string, string> {
  return Object.fromEntries(
    Array.from(block.matchAll(/^\s*(--[\w-]+):\s*([^;]+);/gm), ([, key, value]) => [key, value.trim()]),
  );
}

const light = declarations(lightBlock);
const dark = { ...light, ...declarations(darkBlock) };

function color(values: Record<string, string>, name: string, seen = new Set<string>()): string {
  assert.ok(!seen.has(name), `circular color alias: ${name}`);
  seen.add(name);
  const value = values[name];
  assert.ok(value, `missing token: ${name}`);
  if (value.startsWith("var(")) {
    const match = value.match(/^var\((--[\w-]+)\)$/);
    assert.ok(match, `unsupported alias: ${name}`);
    return color(values, match[1], seen);
  }
  assert.match(value, /^#[0-9a-fA-F]{6}$/, `expected hex token: ${name}`);
  return value;
}

function luminance(hex: string): number {
  const components = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const [red, green, blue] = components.map((value) =>
    value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4,
  );
  return red * 0.2126 + green * 0.7152 + blue * 0.0722;
}

function contrast(a: string, b: string): number {
  const [lighter, darker] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (lighter + 0.05) / (darker + 0.05);
}

for (const [theme, values] of [["light", light], ["dark", dark]] as const) {
  test(`${theme}: key text and CTA pairs meet WCAG AA (4.5:1)`, () => {
    for (const [foreground, background] of [
      ["--text-primary", "--bg-surface"],
      ["--text-secondary-strong", "--bg-surface"],
      ["--brand-text-accent", "--bg-surface"],
      ["--brand-action-fg", "--brand-action"],
    ]) {
      const ratio = contrast(color(values, foreground), color(values, background));
      assert.ok(ratio >= 4.5, `${theme} ${foreground}/${background}: ${ratio.toFixed(2)}:1`);
    }
  });
  test(`${theme}: visible focus outline meets non-text contrast (3:1)`, () => {
    const ratio = contrast(color(values, "--focus-ring"), color(values, "--bg-surface"));
    assert.ok(ratio >= 3, `${theme} focus: ${ratio.toFixed(2)}:1`);
  });
}

test("all seven automation node types use semantic color tokens", () => {
  const nodeCode = readFileSync(
    new URL("../src/components/automation-flows/FlowNode.tsx", import.meta.url), "utf8",
  );
  const canvasCode = readFileSync(
    new URL("../src/components/automation-flows/FlowCanvas.tsx", import.meta.url), "utf8",
  );
  for (const semantic of ["trigger", "condition", "action", "wait", "ai", "human", "neutral"]) {
    assert.ok(tokensCss.includes(`--flow-${semantic}:`), semantic);
    assert.ok(nodeCode.includes(`var(--flow-${semantic})`), semantic);
    assert.ok(canvasCode.includes(`var(--flow-${semantic})`), semantic);
  }
});
