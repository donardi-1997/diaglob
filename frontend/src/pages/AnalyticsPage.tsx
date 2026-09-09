import { useTranslation } from "react-i18next";
import { useState } from "react";
import {
  BarChart3,
  MessageSquareText,
  ShoppingBag,
  Workflow,
  TrendingUp,
} from "lucide-react";
import AnalyticsOverview from "../components/AnalyticsOverview";
import AnalyticsConversations from "../components/AnalyticsConversations";
import AnalyticsCommerce from "../components/AnalyticsCommerce";
import AnalyticsAutomations from "../components/AnalyticsAutomations";
import DropshippingOverview from "../components/DropshippingOverview";


interface AnalyticsPageProps {
  canWrite: boolean;
  storeId: number;
}


type AnalyticsTab =
  | "overview"
  | "dropshipping"
  | "conversations"
  | "commerce"
  | "automations";


const TABS: {
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


type QuickRange =
  | ""
  | "today"
  | "7d"
  | "30d"
  | "month";


function getRangeDates(
  range: QuickRange,
): { from: string; to: string } {
  const now = new Date();

  const today = now.toISOString().split("T")[0];

  if (range === "today") {
    return { from: today, to: today };
  }

  if (range === "7d") {
    const d = new Date(now);

    d.setDate(d.getDate() - 7);

    return {
      from: d.toISOString().split("T")[0],
      to: today,
    };
  }

  if (range === "30d") {
    const d = new Date(now);

    d.setDate(d.getDate() - 30);

    return {
      from: d.toISOString().split("T")[0],
      to: today,
    };
  }

  if (range === "month") {
    const first = new Date(
      now.getFullYear(),
      now.getMonth(),
      1,
    );

    return {
      from: first.toISOString().split("T")[0],
      to: today,
    };
  }

  return { from: "", to: "" };
}


export default function AnalyticsPage({
  canWrite: _canWrite,
  storeId,
}: AnalyticsPageProps) {
  const { t } = useTranslation();

  const [activeTab, setActiveTab] =
    useState<AnalyticsTab>("overview");

  const [quickRange, setQuickRange] =
    useState<QuickRange>("");

  const [dateFrom, setDateFrom] = useState("");

  const [dateTo, setDateTo] = useState("");

  const dates = getRangeDates(quickRange);

  const effectiveFrom = dates.from || dateFrom || undefined;

  const effectiveTo = dates.to || dateTo || undefined;

  function handleQuickRange(
    range: QuickRange,
  ) {
    setQuickRange(range);
    setDateFrom("");
    setDateTo("");
  }

  return (
    <div className="content">
      <section className="page-heading">
        <div>
          <span className="eyebrow">
            DIAGLOB TECH
          </span>
          <h1>{t("analytics")}</h1>
        </div>
      </section>

      <div className="analytics-filters">
        <div className="analytics-quick-ranges">
          <button
            className={
              "analytics-range-btn"
              + (!quickRange ? " active" : "")
            }
            onClick={() =>
              handleQuickRange("")
            }
          >
            {t("analyticsRangeAll")}
          </button>

          <button
            className={
              "analytics-range-btn"
              + (quickRange === "today"
                ? " active"
                : "")
            }
            onClick={() =>
              handleQuickRange("today")
            }
          >
            {t("analyticsRangeToday")}
          </button>

          <button
            className={
              "analytics-range-btn"
              + (quickRange === "7d"
                ? " active"
                : "")
            }
            onClick={() =>
              handleQuickRange("7d")
            }
          >
            {t("analyticsRange7d")}
          </button>

          <button
            className={
              "analytics-range-btn"
              + (quickRange === "30d"
                ? " active"
                : "")
            }
            onClick={() =>
              handleQuickRange("30d")
            }
          >
            {t("analyticsRange30d")}
          </button>

          <button
            className={
              "analytics-range-btn"
              + (quickRange === "month"
                ? " active"
                : "")
            }
            onClick={() =>
              handleQuickRange("month")
            }
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
            placeholder={t(
              "analyticsDateFrom",
            )}
          />

          <span className="analytics-date-sep">
            —
          </span>

          <input
            type="date"
            value={dateTo}
            onChange={(e) => {
              setDateTo(e.target.value);
              setQuickRange("");
            }}
            placeholder={t(
              "analyticsDateTo",
            )}
          />
        </div>
      </div>

      <div className="commerce-tabs">
        {TABS.map((tab) => {
          const Icon = tab.icon;

          return (
            <button
              key={tab.key}
              className={
                "commerce-tab"
                + (activeTab === tab.key
                  ? " active"
                  : "")
              }
              onClick={() =>
                setActiveTab(tab.key)
              }
            >
              <Icon size={16} />
              {t(tab.labelKey)}
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
      </div>
    </div>
  );
}
