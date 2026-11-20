import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { createdTemplateFlowId, templateGraphSteps } from "../src/utils/automationTemplateFlow.ts";

const source = (path: string) =>
  readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8");

test("template-flow response must identify a positive integer flow", () => {
  assert.equal(createdTemplateFlowId({ template_id: "welcome", flow: { id: 42 } }), 42);
  for (const malformed of [
    null,
    undefined,
    {},
    { id: 4 },
    { flow: null },
    { flow: {} },
    { flow: { id: "42" } },
    { flow: { id: 0 } },
    { flow: { id: -1 } },
    { flow: { id: 1.5 } },
    { flow: { id: Number.MAX_SAFE_INTEGER + 1 } },
  ]) {
    assert.throws(() => createdTemplateFlowId(malformed));
  }
});

test("template preview omits malformed nodes and sensitive config values", () => {
  assert.deepEqual(templateGraphSteps({
    nodes: [
      { type: "trigger", config: { secret: "never expose" } },
      null,
      { type: "message", config: { message_template: "private data" } },
      { type: "unknown" },
      { type: 12 },
      { type: "end" },
    ],
  }), ["trigger", "message", "end"]);
  assert.deepEqual(templateGraphSteps({ nodes: null }), []);
  assert.deepEqual(templateGraphSteps({}), []);
});

test("creating a template navigates to the exact created flow, not the general list", () => {
  const templates = source("components/AutomationTemplates.tsx");
  const setup = source("components/AutomationModelSetupDialog.tsx");
  const page = source("pages/AutomationsPage.tsx");
  assert.match(setup, /createdTemplateFlowId\(response\.data\)/);
  assert.match(setup, /onCreated\(createdTemplateFlowId\(response\.data\), activated\)/);
  assert.match(templates, /onFlowCreated\(flowId\)/);
  assert.match(page, /setPendingTemplateFlow\(\{ storeId, flowId \}\)/);
  assert.match(page, /initialFlowId=\{pendingTemplateFlow\?\.storeId === storeId/);
  assert.match(page, /onInitialFlowHandled=\{handleTemplateFlowHandled\}/);
  assert.match(page, /onEditorDirtyChange=\{handleEditorDirtyChange\}/);
});

test("editor flow activation remains explicitly gated by publication and confirmation", () => {
  const flows = source("components/automation-flows/FlowList.tsx");
  assert.match(flows, /publishFlowVersion\(storeId, selectedFlow\.id, version\.id\)/);
  assert.match(flows, /!version\?\.published_at/);
  assert.match(flows, /window\.confirm\(t\("flowEditorConfirmActivate"\)\)/);
  assert.match(flows, /activateFlow\(storeId, selectedFlow\.id\)/);
  assert.match(flows, /disabled=\{saving \|\| publishing \|\| activating \|\| dirty/);
  assert.match(flows, /onEditorDirtyChange\?\.\(view === "builder" && dirty\)/);
  assert.match(flows, /setSavedGraphSignature\(signature\)/);
  assert.doesNotMatch(source("components/AutomationTemplates.tsx"), /activateFlow\(/);
  // The model wizard may activate in one step, but only after the same explicit confirmation.
  const setup = source("components/AutomationModelSetupDialog.tsx");
  assert.doesNotMatch(setup, /activateFlow\(/);
  assert.match(setup, /if \(activate && !window\.confirm\(t\("flowEditorConfirmActivate"\)\)\) return;/);
  assert.match(setup, /useState\(false\);\s*\n\s*const \[submitting/);
});
