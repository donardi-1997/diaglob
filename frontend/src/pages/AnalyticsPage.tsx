import { useTranslation } from "react-i18next";
import { useEffect, useState } from "react";
import {
  BarChart3,
  MessageSquareText,
  ShoppingBag,
  Workflow,
  TrendingUp,
  ShieldCheck,
} from "lucide-react";
import AnalyticsOverview from "../components/AnalyticsOverview";
import AnalyticsConversations from "../components/AnalyticsConversations";
import AnalyticsCommerce from "../components/AnalyticsCommerce";
import AnalyticsAutomations from "../components/AnalyticsAutomations";
import DropshippingOverview from "../components/DropshippingOverview";
import AdminAnalytics from "../components/AdminAnalytics";
import { getAdminStatus } from "../services/adminAnalytics";
import {
  getAnalyticsRangeDates,
  type AnalyticsQuickRange,
} from "../utils/analyticsDateRange";

interface AnalyticsPageProps {
  canWrite: boolean;
  storeId: number;
  currency: string;
}

type AnalyticsTab =
  | "overview"
  | "dropshipping"
  | "conversations"
  | "commerce"
  | "automations"
  | "admin";

const BASE_TABS: {
  key: AnalyticsTab;
  labelKey: string;
  icon: typeof BarChart3;
}[] = [
  {
    key: "overview",
    labelKey: "analyticsTabOverview",
    icon: BarChart3,
  },
  {
    key: "dropshipping",
    labelKey: "analyticsTabDropshipping",
    icon: TrendingUp,
  },
  {
    key: "conversations",
    labelKey: "analyticsTabConversations",
    icon: MessageSquareText,
  },
  {
    key: "commerce",
    labelKey: "analyticsTabCommerce",
    icon: ShoppingBag,
  },
  {
    key: "automations",
    labelKey: "analyticsTabAutomations",
    icon: Workflow,
  },
];

export default function AnalyticsPage({
  canWrite: _canWrite,
  storeId,
  currency,
}: AnalyticsPageProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<AnalyticsTab>("overview");
  const [isPlatformAdmin, setIsPlatformAdmin] = useState(false);
  const [quickRange, setQuickRange] = useState<AnalyticsQuickRange>("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  useEffect(() => {
    let cancelled = false;

    getAdminStatus()
      .then((status) => {
        if (!cancelled) setIsPlatformAdmin(status.platform_admin === true);
      })
      .catch(() => {
        if (!cancelled) setIsPlatformAdmin(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const dates = getAnalyticsRangeDates(quickRange);
  const effectiveFrom = dates.from || dateFrom || undefined;
  const effectiveTo = dates.to || dateTo || undefined;

  const tabs = isPlatformAdmin
    ? [
        ...BASE_TABS,
        {
          key: "admin" as AnalyticsTab,
          labelKey: "Admin Diaglob",
          icon: ShieldCheck,
        },
      ]
    : BASE_TABS;

  function handleQuickRange(range: AnalyticsQuickRange) {
    setQuickRange(range);
    setDateFrom("");
    setDateTo("");
  }

  return (
    <div className="content">
      <section className="page-heading">
        <div>
          <span className="eyebrow">DIAGLOB TECH</span>
          <h1>{t("analytics")}</h1>
        </div>
      </section>

      {activeTab !== "admin" && (
        <div className="analytics-filters">
          <div className="analytics-quick-ranges">
            <button
              className={"analytics-range-btn" + (!quickRange ? " active" : "")}
              onClick={() => handleQuickRange("")}
            >
              {t("analyticsRangeAll")}
            </button>

            <button
              className={
                "analytics-range-btn" + (quickRange === "today" ? " active" : "")
              }
              onClick={() => handleQuickRange("today")}
            >
              {t("analyticsRangeToday")}
            </button>

            <button
              className={
                "analytics-range-btn" + (quickRange === "7d" ? " active" : "")
              }
              onClick={() => handleQuickRange("7d")}
            >
              {t("analyticsRange7d")}
            </button>

            <button
              className={
                "analytics-range-btn" + (quickRange === "30d" ? " active" : "")
              }
              onClick={() => handleQuickRange("30d")}
            >
              {t("analyticsRange30d")}
            </button>

            <button
              className={
                "analytics-range-btn" + (quickRange === "month" ? " active" : "")
              }
              onClick={() => handleQuickRange("month")}
            >
              {t("analyticsRangeMonth")}
            </button>
          </div>

          <div className="analytics-date-inputs">
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => {
                setDateFrom(e.target.value);
                setQuickRange("");
              }}
              placeholder={t("analyticsDateFrom")}
            />

            <span className="analytics-date-sep">—</span>

            <input
              type="date"
              value={dateTo}
              onChange={(e) => {
                setDateTo(e.target.value);
                setQuickRange("");
              }}
              placeholder={t("analyticsDateTo")}
            />
          </div>
        </div>
      )}

      <div className="commerce-tabs">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const label = tab.key === "admin" ? tab.labelKey : t(tab.labelKey);

          return (
            <button
              key={tab.key}
              className={
                "commerce-tab" + (activeTab === tab.key ? " active" : "")
              }
              onClick={() => setActiveTab(tab.key)}
            >
              <Icon size={16} />
              {label}
            </button>
          );
        })}
      </div>

      <div className="commerce-content">
        {activeTab === "overview" && (
          <AnalyticsOverview
            storeId={storeId}
            dateFrom={effectiveFrom}
            dateTo={effectiveTo}
          />
        )}

        {activeTab === "dropshipping" && (
          <DropshippingOverview
            storeId={storeId}
            currency={currency}
            dateFrom={effectiveFrom}
            dateTo={effectiveTo}
          />
        )}

        {activeTab === "conversations" && (
          <AnalyticsConversations
            storeId={storeId}
            dateFrom={effectiveFrom}
            dateTo={effectiveTo}
          />
        )}

        {activeTab === "commerce" && (
          <AnalyticsCommerce
            storeId={storeId}
            dateFrom={effectiveFrom}
            dateTo={effectiveTo}
          />
        )}

        {activeTab === "automations" && (
          <AnalyticsAutomations
            storeId={storeId}
            dateFrom={effectiveFrom}
            dateTo={effectiveTo}
          />
        )}

        {activeTab === "admin" && isPlatformAdmin && <AdminAnalytics />}
      </div>
    </div>
  );
}
