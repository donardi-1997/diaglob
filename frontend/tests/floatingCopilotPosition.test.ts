import test from "node:test";
import assert from "node:assert/strict";

import {
  clampFloatingPosition,
  defaultFloatingPosition,
  parseFloatingPosition,
} from "../src/services/floatingCopilotPosition.ts";

test("floating copilot stays inside the viewport", () => {
  assert.deepEqual(
    clampFloatingPosition({ x: -100, y: -50 }, 1200, 800),
    { x: 14, y: 14 },
  );
  assert.deepEqual(
    clampFloatingPosition({ x: 5000, y: 5000 }, 1200, 800),
    { x: 1130, y: 730 },
  );
});

test("floating copilot gets a safe default near the lower right", () => {
  assert.deepEqual(
    defaultFloatingPosition(1200, 800),
    { x: 1120, y: 612 },
  );
});

test("saved floating positions fail closed when malformed", () => {
  assert.equal(parseFloatingPosition(null), null);
  assert.equal(parseFloatingPosition("nope"), null);
  assert.equal(parseFloatingPosition('{"x":"1","y":2}'), null);
  assert.deepEqual(
    parseFloatingPosition('{"x":100,"y":200}'),
    { x: 100, y: 200 },
  );
});
