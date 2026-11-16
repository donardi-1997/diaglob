import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { createdTemplateFlowId } from "../src/utils/automationTemplateFlow.ts";

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

test("creating a template navigates to the exact created flow, not the general list", () => {
  const templates = source("components/AutomationTemplates.tsx");
  const page = source("pages/AutomationsPage.tsx");
  assert.match(templates, /createdTemplateFlowId\(response\.data\)/);
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
});
