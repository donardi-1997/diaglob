import type { Automation, AutomationCampaign } from "../services/automations";
import type { AutomationFlow } from "../services/automationFlows";

interface Sources {
  flows: AutomationFlow[] | null;
  campaigns: AutomationCampaign[] | null;
  rules: Automation[] | null;
}

export interface AutomationOverviewCounts {
  activeFlows: number | null;
  draftFlows: number | null;
  activeCampaigns: number | null;
  activeRules: number | null;
}

/** Null represents unavailable data, which must not be reported as zero. */
export function automationOverviewCounts(sources: Sources): AutomationOverviewCounts {
  return {
    activeFlows: sources.flows?.filter((flow) => flow.status === "active").length ?? null,
    draftFlows: sources.flows?.filter((flow) => flow.status === "draft").length ?? null,
    activeCampaigns: sources.campaigns?.filter((campaign) => campaign.status === "active").length ?? null,
    activeRules: sources.rules?.filter((rule) => rule.active).length ?? null,
  };
}

export function recentAutomationFlows(
  flows: AutomationFlow[] | null,
  limit = 5,
): AutomationFlow[] {
  if (!flows || limit <= 0) return [];
  const timestamp = (flow: AutomationFlow) => {
    const value = flow.updated_at || flow.created_at;
    const parsed = value ? Date.parse(value) : NaN;
    return Number.isFinite(parsed) ? parsed : 0;
  };
  // Sort a copy: callers may also render the original array in a flow list.
  return [...flows]
    .filter((flow) => flow.status !== "archived")
    .sort((a, b) => timestamp(b) - timestamp(a) || b.id - a.id)
    .slice(0, limit);
}
