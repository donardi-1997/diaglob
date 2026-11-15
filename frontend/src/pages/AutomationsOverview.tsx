import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowRight, GitBranch, LayoutTemplate, RefreshCw, Send, Workflow } from "lucide-react";
import { listFlows, type AutomationFlow } from "../services/automationFlows";
import {
  listAutomationCampaigns,
  listAutomations,
  type Automation,
  type AutomationCampaign,
} from "../services/automations";
import { automationOverviewCounts, recentAutomationFlows } from "../utils/automationOverview";
import "./automations-overview.css";

type Destination = "flows" | "templates" | "campaigns";

interface Props {
  storeId: number;
  onNavigate: (destination: Destination) => void;
}

interface OverviewData {
  flows: AutomationFlow[] | null;
  campaigns: AutomationCampaign[] | null;
  rules: Automation[] | null;
}

const EMPTY_DATA: OverviewData = { flows: null, campaigns: null, rules: null };

export default function AutomationsOverview({ storeId, onNavigate }: Props) {
  const { t } = useTranslation();
  const [data, setData] = useState<OverviewData>(EMPTY_DATA);
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setData(EMPTY_DATA);

    // Each endpoint is store-scoped. One unavailable legacy API must not hide
    // healthy flow/campaign data or accidentally turn missing data into zero.
    void Promise.allSettled([
      listFlows(storeId),
      listAutomationCampaigns(storeId),
      listAutomations(storeId),
    ]).then(([flowResult, campaignResult, ruleResult]) => {
      if (cancelled) return;
      setData({
        flows: flowResult.status === "fulfilled" ? flowResult.value : null,
        campaigns: campaignResult.status === "fulfilled" ? campaignResult.value.items : null,
        rules: ruleResult.status === "fulfilled" ? ruleResult.value.items : null,
      });
      setLoading(false);
    });

    // Prevent an older store request from rendering data in a new store.
    return () => { cancelled = true; };
  }, [storeId, refreshKey]);

  const counts = automationOverviewCounts(data);
  const recentFlows = recentAutomationFlows(data.flows, 5);
  const hasPartialFailure = !loading && Object.values(data).some((value) => value === null);

  const metrics = [
    { key: "activeFlows", label: t("autoOverviewActiveFlows"), icon: GitBranch },
    { key: "draftFlows", label: t("autoOverviewDraftFlows"), icon: Workflow },
    { key: "activeCampaigns", label: t("autoOverviewActiveCampaigns"), icon: Send },
    { key: "activeRules", label: t("autoOverviewActiveRules"), icon: LayoutTemplate },
  ] as const;

  return (
    <section className="auto-overview" aria-busy={loading}>
      <div className="auto-overview-hero">
        <div>
          <span className="auto-overview-eyebrow">DIAGLOB · AUTOMATIONS</span>
          <h2>{t("autoOverviewTitle")}</h2>
          <p>{t("autoOverviewIntro")}</p>
          <div className="auto-overview-actions">
            <button className="primary-button" type="button" onClick={() => onNavigate("flows")}>
              <GitBranch size={16} aria-hidden="true" />
              {t("autoOverviewOpenFlows")}
            </button>
            <button className="secondary-button" type="button" onClick={() => onNavigate("templates")}>
              <LayoutTemplate size={16} aria-hidden="true" />
              {t("autoOverviewBrowseTemplates")}
            </button>
          </div>
        </div>
        <button
          className="auto-overview-refresh"
          type="button"
          disabled={loading}
          onClick={() => setRefreshKey((key) => key + 1)}
        >
          <RefreshCw size={16} aria-hidden="true" />
          {t("autoOverviewRefresh")}
        </button>
      </div>

      {hasPartialFailure && (
        <p className="auto-overview-warning" role="alert">
          {t("autoOverviewPartialError")}
        </p>
      )}

      <div className="auto-overview-metrics" aria-label={t("autoOverviewMetrics")}>
        {metrics.map(({ key, label, icon: Icon }) => (
          <article className="auto-overview-metric" key={key}>
            <span className="auto-overview-metric-icon"><Icon size={20} aria-hidden="true" /></span>
            <strong aria-label={counts[key] === null ? t("autoOverviewUnavailable") : undefined}>
              {loading || counts[key] === null ? "—" : counts[key]}
            </strong>
            <span>{label}</span>
          </article>
        ))}
      </div>

      <div className="auto-overview-panels">
        <section className="auto-overview-panel" aria-labelledby="auto-overview-recent-heading">
          <div className="auto-overview-panel-header">
            <div>
              <h3 id="auto-overview-recent-heading">{t("autoOverviewRecentFlows")}</h3>
              <p>{t("autoOverviewRecentSubtitle")}</p>
            </div>
            <button type="button" className="auto-overview-link" onClick={() => onNavigate("flows")}>
              {t("autoOverviewViewAll")} <ArrowRight size={16} aria-hidden="true" />
            </button>
          </div>
          {loading ? (
            <p className="auto-overview-empty" role="status">{t("commonLoading")}</p>
          ) : data.flows === null ? (
            <p className="auto-overview-empty">{t("autoOverviewUnavailable")}</p>
          ) : recentFlows.length === 0 ? (
            <p className="auto-overview-empty">{t("autoOverviewEmpty")}</p>
          ) : (
            <ul className="auto-overview-flow-list">
              {recentFlows.map((flow) => (
                <li key={flow.id}>
                  <div className="auto-overview-flow-info">
                    <strong>{flow.name}</strong>
                    <span>{flow.updated_at || flow.created_at
                      ? new Date(flow.updated_at || flow.created_at!).toLocaleDateString()
                      : t("autoOverviewNoDate")}</span>
                  </div>
                  <span className={`auto-overview-status auto-overview-status--${flow.status}`}>
                    {t(`flowStatus_${flow.status}`)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="auto-overview-panel auto-overview-start" aria-labelledby="auto-overview-start-heading">
          <h3 id="auto-overview-start-heading">{t("autoOverviewGetStarted")}</h3>
          <p>{t("autoOverviewStartIntro")}</p>
          <button type="button" className="auto-overview-start-link" onClick={() => onNavigate("templates")}>
            <LayoutTemplate size={20} aria-hidden="true" />
            <span>{t("autoOverviewBrowseTemplates")}</span>
            <ArrowRight size={16} aria-hidden="true" />
          </button>
          <button type="button" className="auto-overview-start-link" onClick={() => onNavigate("campaigns")}>
            <Send size={20} aria-hidden="true" />
            <span>{t("autoOverviewSeeCampaigns")}</span>
            <ArrowRight size={16} aria-hidden="true" />
          </button>
        </section>
      </div>
    </section>
  );
}
