import assert from "node:assert/strict";
import test from "node:test";

import { resolvePaddleJsEnvironment } from "../src/services/paddleEnvironment.ts";

const sandboxToken = `test_${"a".repeat(27)}`;
const liveToken = `live_${"b".repeat(27)}`;

test("Paddle.js requires an explicit environment for every token", () => {
  assert.equal(resolvePaddleJsEnvironment(sandboxToken, undefined), null);
  assert.equal(resolvePaddleJsEnvironment(sandboxToken, ""), null);
  assert.equal(resolvePaddleJsEnvironment(sandboxToken, "sandbox"), "sandbox");
  assert.equal(resolvePaddleJsEnvironment(liveToken, undefined), null);
  assert.equal(resolvePaddleJsEnvironment(liveToken, "sandbox"), null);
});

test("production Paddle.js requires an explicit production opt-in and live token", () => {
  assert.equal(resolvePaddleJsEnvironment(liveToken, "production"), "production");
  assert.equal(resolvePaddleJsEnvironment(sandboxToken, "production"), null);
  assert.equal(resolvePaddleJsEnvironment(liveToken, "live"), null);
  assert.equal(resolvePaddleJsEnvironment(liveToken, "PRODUCTION"), null);
});

test("no token, invalid credentials or server API keys never initialize Paddle.js", () => {
  assert.equal(resolvePaddleJsEnvironment("", "sandbox"), null);
  assert.equal(resolvePaddleJsEnvironment(undefined, "sandbox"), null);
  assert.equal(resolvePaddleJsEnvironment("pdl_live_secret", "production"), null);
  assert.equal(resolvePaddleJsEnvironment("test_dummy", "sandbox"), null);
  assert.equal(resolvePaddleJsEnvironment("live_dummy", "production"), null);
  assert.equal(resolvePaddleJsEnvironment(sandboxToken, "unknown"), null);
  assert.equal(resolvePaddleJsEnvironment(sandboxToken, true), null);
});
