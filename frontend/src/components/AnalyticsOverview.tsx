import { useTranslation } from "react-i18next";
import { useEffect, useState } from "react";
import {
  LoaderCircle,
  MessageSquareText,
  Package,
  ShoppingBag,
  TrendingUp,
  Workflow,
} from "lucide-react";
import {
  getAnalyticsSummary,
  getAnalyticsTimeseries,
  type AnalyticsSummary,
  type TimeseriesPoint,
} from "../services/analytics";


interface Props {
  storeId: number;
  dateFrom?: string;
  dateTo?: string;
}


export default function AnalyticsOverview({
  storeId,
  dateFrom,
  dateTo,
}: Props) {
  const { t } = useTranslation();

  const [summary, setSummary] =
    useState<AnalyticsSummary | null>(null);

  const [timeseries, setTimeseries] =
    useState<TimeseriesPoint[]>([]);

  const [loading, setLoading] =
    useState(true);

  const [error, setError] =
    useState("");


  useEffect(() => {
    loadData();
  }, [storeId, dateFrom, dateTo]);


  async function loadData() {
    try {
      setLoading(true);
      setError("");

      const [s, ts] = await Promise.all([
        getAnalyticsSummary(
          storeId,
          dateFrom,
          dateTo,
        ),
        getAnalyticsTimeseries(
          storeId,
          dateFrom,
          dateTo,
        ),
      ]);

      setSummary(s);
      setTimeseries(ts);
    } catch {
      setError(t("analyticsLoadError"));
    } finally {
      setLoading(false);
    }
  }


  if (loading) {
    return (
      <div className="commerce-loading">
        <LoaderCircle
          className="spin"
          size={24}
        />
      </div>
    );
  }


  if (error) {
    return (
      <div className="commerce-empty">
        <p>{error}</p>
      </div>
    );
  }


  if (!summary) {
    return (
      <div className="commerce-empty">
        <p>{t("analyticsNoData")}</p>
      </div>
    );
  }


  const maxMessages = Math.max(
    1,
    ...timeseries.map((p) => p.messages),
  );

  const maxOrders = Math.max(
    1,
    ...timeseries.map((p) => p.orders),
  );


  return (
    <div className="analytics-overview">
      <div className="analytics-stats-grid">
        <div className="analytics-stat-card">
          <div className="analytics-stat-icon">
            <MessageSquareText size={20} />
          </div>
          <div className="analytics-stat-info">
            <span className="analytics-stat-value">
              {summary.total_conversations.toLocaleString()}
            </span>
            <span className="analytics-stat-label">
              {t(
                "analyticsStatConversations",
              )}
            </span>
          </div>
        </div>

        <div className="analytics-stat-card">
          <div className="analytics-stat-icon">
            <MessageSquareText size={20} />
          </div>
          <div className="analytics-stat-info">
            <span className="analytics-stat-value">
              {summary.total_messages.toLocaleString()}
            </span>
            <span className="analytics-stat-label">
              {t("analyticsStatMessages")}
            </span>
          </div>
        </div>

        <div className="analytics-stat-card">
          <div className="analytics-stat-icon">
            <Package size={20} />
          </div>
          <div className="analytics-stat-info">
            <span className="analytics-stat-value">
              {summary.total_products}
            </span>
            <span className="analytics-stat-label">
              {t("analyticsStatProducts")}
            </span>
          </div>
        </div>

        <div className="analytics-stat-card">
          <div className="analytics-stat-icon">
            <ShoppingBag size={20} />
          </div>
          <div className="analytics-stat-info">
            <span className="analytics-stat-value">
              {summary.total_orders}
            </span>
            <span className="analytics-stat-label">
              {t("analyticsStatOrders")}
            </span>
          </div>
        </div>

        <div className="analytics-stat-card">
          <div className="analytics-stat-icon">
            <TrendingUp size={20} />
          </div>
          <div className="analytics-stat-info">
            <span className="analytics-stat-value">
              {summary.total_order_value.toLocaleString(
                undefined,
                {
                  minimumFractionDigits: 0,
                  maximumFractionDigits: 0,
                },
              )}
            </span>
            <span className="analytics-stat-label">
              {t("analyticsStatOrderValue")}
            </span>
          </div>
        </div>

        <div className="analytics-stat-card">
          <div className="analytics-stat-icon">
            <Workflow size={20} />
          </div>
          <div className="analytics-stat-info">
            <span className="analytics-stat-value">
              {summary.active_automations}
            </span>
            <span className="analytics-stat-label">
              {t(
                "analyticsStatActiveAutomations",
              )}
            </span>
          </div>
        </div>
      </div>


      <div className="analytics-row">
        <div className="analytics-card">
          <h3>
            {t("analyticsMessagesPerDay")}
          </h3>

          {timeseries.length === 0 ? (
            <div className="analytics-empty-chart">
              {t("analyticsNoTimeseries")}
            </div>
          ) : (
            <div className="analytics-bar-chart">
              {timeseries.map((p) => (
                <div
                  key={p.date}
                  className="analytics-bar-col"
                >
                  <div className="analytics-bar-wrapper">
                    <div
                      className="analytics-bar messages"
                      style={{
                        height: `${
                          (p.messages /
                            maxMessages) *
                          100
                        }%`,
                      }}
                      title={`${p.date}: ${p.messages}`}
                    />
                  </div>
                  <span className="analytics-bar-label">
                    {p.date.slice(5)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="analytics-card">
          <h3>
            {t("analyticsOrdersPerDay")}
          </h3>

          {timeseries.length === 0 ? (
            <div className="analytics-empty-chart">
              {t("analyticsNoTimeseries")}
            </div>
          ) : (
            <div className="analytics-bar-chart">
              {timeseries.map((p) => (
                <div
                  key={p.date}
                  className="analytics-bar-col"
                >
                  <div className="analytics-bar-wrapper">
                    <div
                      className="analytics-bar orders"
                      style={{
                        height: `${
                          (p.orders /
                            maxOrders) *
                          100
                        }%`,
                      }}
                      title={`${p.date}: ${p.orders}`}
                    />
                  </div>
                  <span className="analytics-bar-label">
                    {p.date.slice(5)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>


      <div className="analytics-row">
        <div className="analytics-card">
          <h3>
            {t("analyticsAvgMetrics")}
          </h3>

          <div className="analytics-metrics-list">
            <div className="analytics-metric-item">
              <span className="analytics-metric-label">
                {t(
                  "analyticsAvgMessagesPerConv",
                )}
              </span>
              <span className="analytics-metric-value">
                {
                  summary.avg_messages_per_conversation
                }
              </span>
            </div>

            <div className="analytics-metric-item">
              <span className="analytics-metric-label">
                {t("analyticsAvgOrderValue")}
              </span>
              <span className="analytics-metric-value">
                {summary.avg_order_value.toLocaleString()}
              </span>
            </div>
          </div>
        </div>

        <div className="analytics-card">
          <h3>
            {t("analyticsAutomationRate")}
          </h3>

          <div className="analytics-metrics-list">
            <div className="analytics-metric-item">
              <span className="analytics-metric-label">
                {t("analyticsExecutions")}
              </span>
              <span className="analytics-metric-value">
                {summary.total_executions}
              </span>
            </div>

            <div className="analytics-metric-item">
              <span className="analytics-metric-label">
                {t("analyticsSuccessRate")}
              </span>
              <span className="analytics-metric-value">
                {summary.automation_success_rate}
                %
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
