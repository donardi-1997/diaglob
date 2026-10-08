import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const entry = readFileSync(new URL("../src/main.tsx", import.meta.url), "utf8");
const styles = readFileSync(new URL("../src/design-system.css", import.meta.url), "utf8");

test("the shared Diaglob design layer is included by App", () => {
  assert.match(app, /import "\.\/design-system\.css";/);
  assert.match(app, /diaglob-theme"\) \|\| "light"/);
});

test("initial theme uses persisted preference without a dark flash", () => {
  assert.match(entry, /getItem\('diaglob-theme'\)/);
  assert.match(entry, /setAttribute\('data-theme', storedTheme === 'dark' \? 'dark' : 'light'\)/);
});

test("design layer supports responsive, focus and reduced-motion states", () => {
  assert.match(styles, /\[data-theme="light"\]/);
  assert.match(styles, /\[data-theme="dark"\]/);
  assert.match(styles, /:focus-visible/);
  assert.match(styles, /max-width: 560px/);
  assert.match(styles, /prefers-reduced-motion: reduce/);
});

test("visual refinements cover core product workspaces", () => {
  for (const selector of [
    ".dg-nav-item.is-active",
    ".dg-dashboard-hero",
    ".dg-metric-card",
    ".landing-hero-title",
    ".flow-canvas-container",
    ".copilot-composer-box",
    ".integrations-hub-card",
  ]) {
    assert.ok(styles.includes(selector), `Missing design coverage for ${selector}`);
  }
});
