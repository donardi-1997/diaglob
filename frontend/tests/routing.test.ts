import assert from "node:assert/strict";
import test from "node:test";

import {
  getAppPageFromPath,
  getAppPath,
  isAppPath,
  isAppRoot,
  sanitizeReturnTo,
} from "../src/routing.ts";

test("app page keys map to stable canonical paths", () => {
  assert.equal(getAppPath("overview"), "/app/overview");
  assert.equal(getAppPath("settings"), "/app/stores");
  assert.equal(getAppPath("post-sales"), "/app/post-sales");
  assert.equal(getAppPath("unknown"), "/app");
});

test("canonical app paths resolve back to page keys", () => {
  assert.equal(getAppPageFromPath("/app/overview"), "overview");
  assert.equal(getAppPageFromPath("/app/stores"), "settings");
  assert.equal(getAppPageFromPath("/app/post-sales/"), "post-sales");
  assert.equal(getAppPageFromPath("/app/not-real"), null);
  assert.equal(getAppPageFromPath("/app/analytics/details"), null);
});

test("app root is distinct from nested app routes", () => {
  assert.equal(isAppRoot("/app"), true);
  assert.equal(isAppRoot("/app/"), true);
  assert.equal(isAppRoot("/app/overview"), false);
  assert.equal(isAppPath("/app/overview"), true);
  assert.equal(isAppPath("/application"), false);
});

test("post-auth redirects only allow local app destinations", () => {
  assert.equal(
    sanitizeReturnTo("/app/analytics?range=30d#chart"),
    "/app/analytics?range=30d#chart",
  );
  assert.equal(sanitizeReturnTo("/ecommerce"), "/app");
  assert.equal(sanitizeReturnTo("https://evil.example"), "/app");
  assert.equal(sanitizeReturnTo("//evil.example/app"), "/app");
  assert.equal(sanitizeReturnTo(null), "/app");
});
