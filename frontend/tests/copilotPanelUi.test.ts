import test from "node:test";
import assert from "node:assert/strict";

import {
  COPILOT_PANEL_DEFAULT_WIDTH,
  clampCopilotPanelWidth,
  nextTypewriterLength,
} from "../src/services/copilotPanelUi.ts";

test("clampCopilotPanelWidth respects desktop limits and viewport", () => {
  assert.equal(clampCopilotPanelWidth(100, 1600), 360);
  assert.equal(clampCopilotPanelWidth(500, 1600), 500);
  assert.equal(clampCopilotPanelWidth(1200, 1600), 820);
  assert.equal(clampCopilotPanelWidth(700, 500), 476);
  assert.equal(COPILOT_PANEL_DEFAULT_WIDTH, 460);
});

test("nextTypewriterLength reveals text progressively", () => {
  assert.equal(nextTypewriterLength(0, 100), 2);
  assert.equal(nextTypewriterLength(0, 300), 3);
  assert.equal(nextTypewriterLength(0, 1000), 4);
  assert.equal(nextTypewriterLength(99, 100), 100);
  assert.equal(nextTypewriterLength(100, 100), 100);
});
