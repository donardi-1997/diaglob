import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

import {
  automationOverviewCounts,
  recentAutomationFlows,
} from "../src/utils/automationOverview.ts";
import type { AutomationFlow } from "../src/services/automationFlows.ts";
import type { Automation, AutomationCampaign } from "../src/services/automations.ts";

function flow(id: number, status: AutomationFlow["status"], date: string | null): AutomationFlow {
  return {
    id, status, name: `Flow ${id}`, description: null,
    current_version_id: null, active_version_id: null, created_by: null,
    created_at: date, updated_at: date,
  };
}

test("overview counts active flows, drafts, campaigns and legacy rules separately", () => {
  const result = automationOverviewCounts({
    flows: [flow(1, "active", null), flow(2, "draft", null), flow(3, "paused", null)],
    campaigns: [{ status: "active" }, { status: "paused" }] as AutomationCampaign[],
    rules: [{ active: true }, { active: false }, { active: true }] as Automation[],
  });
  assert.deepEqual(result, {
    activeFlows: 1, draftFlows: 1, activeCampaigns: 1, activeRules: 2,
  });
});

test("failed endpoints remain unavailable rather than reporting zero", () => {
  const counts = automationOverviewCounts({ flows: null, campaigns: [], rules: null });
  assert.equal(counts.activeFlows, null);
  assert.equal(counts.draftFlows, null);
  assert.equal(counts.activeCampaigns, 0);
  assert.equal(counts.activeRules, null);
});

test("recent flows are immutable, sorted, limited and exclude archived flows", () => {
  const input = [
    flow(1, "draft", "2026-11-10T12:00:00Z"),
    flow(2, "active", "2026-11-13T12:00:00Z"),
    flow(3, "archived", "2026-11-15T12:00:00Z"),
    flow(4, "paused", null),
  ];
  const before = [...input];
  assert.deepEqual(recentAutomationFlows(input, 2).map((item) => item.id), [2, 1]);
  assert.deepEqual(input, before);
  assert.deepEqual(recentAutomationFlows(input, 0), []);
  assert.deepEqual(recentAutomationFlows(null), []);
});

test("navigation keeps campaigns isolated and overview protects store-scoped results", () => {
  const page = readFileSync(new URL("../src/pages/AutomationsPage.tsx", import.meta.url), "utf8");
  const overview = readFileSync(new URL("../src/pages/AutomationsOverview.tsx", import.meta.url), "utf8");
  assert.match(page, /activeTab === "campaigns"/);
  assert.match(page, /activeTab === "overview"/);
  assert.match(overview, /listFlows\(storeId\)/);
  assert.match(overview, /listAutomationCampaigns\(storeId\)/);
  assert.match(overview, /listAutomations\(storeId\)/);
  assert.match(overview, /if \(cancelled\) return/);
  assert.match(overview, /Promise\.allSettled/);
});
