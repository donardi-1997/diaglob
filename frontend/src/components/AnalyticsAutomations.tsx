import { useTranslation } from "react-i18next";
import { useEffect, useState } from "react";
import { LoaderCircle } from "lucide-react";
import {
  getAnalyticsAutomations,
  getAnalyticsTimeseries,
  type AutomationsAnalytics,
  type TimeseriesPoint,
} from "../services/analytics";


interface Props {
  storeId: number;
  dateFrom?: string;
  dateTo?: string;
}


export default function AnalyticsAutomations({
  storeId,
  dateFrom,
  dateTo,
}: Props) {
  const { t } = useTranslation();

  const [data, setData] =
    useState<AutomationsAnalytics | null>(null);

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

      const [autoData, tsData] =
        await Promise.all([
          getAnalyticsAutomations(
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

      setData(autoData);
      setTimeseries(tsData);
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


  if (!data) {
    return (
      <div className="commerce-empty">
        <p>{t("analyticsNoData")}</p>
      </div>
    );
  }


  const maxExec = Math.max(
    1,
    ...timeseries.map((p) => p.executions),
  );

  const totalByStatus = Object.values(
    data.by_status,
  ).reduce((a, b) => a + b, 0);


  return (
    <div className="analytics-automations">
      <div className="analytics-stats-grid">
        <div className="analytics-stat-card">
          <div className="analytics-stat-info">
            <span className="analytics-stat-value">
              {data.total_automations}
            </span>
            <span className="analytics-stat-label">
              {t("analyticsTotalAutomations")}
            </span>
          </div>
        </div>

        <div className="analytics-stat-card">
          <div className="analytics-stat-info">
            <span className="analytics-stat-value">
              {data.active_automations}
            </span>
            <span className="analytics-stat-label">
              {t("analyticsActive")}
            </span>
          </div>
        </div>

        <div className="analytics-stat-card">
          <div className="analytics-stat-info">
            <span className="analytics-stat-value">
              {data.total_executions}
            </span>
            <span className="analytics-stat-label">
              {t("analyticsExecutions")}
            </span>
          </div>
        </div>

        <div className="analytics-stat-card">
          <div className="analytics-stat-info">
            <span className="analytics-stat-value">
              {data.success_rate}%
            </span>
            <span className="analytics-stat-label">
              {t("analyticsSuccessRate")}
            </span>
          </div>
        </div>
      </div>


      <div className="analytics-row">
        <div className="analytics-card">
          <h3>
            {t("analyticsExecutionsPerDay")}
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
                      className="analytics-bar executions"
                      style={{
                        height: `${
                          (p.executions /
                            maxExec) *
                          100
                        }%`,
                      }}
                      title={`${p.date}: ${p.executions}`}
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
            {t("analyticsExecutionsByStatus")}
          </h3>

          <div className="analytics-breakdown">
            {Object.entries(data.by_status).map(
              ([key, val]) => (
                <div
                  key={key}
                  className="analytics-breakdown-item"
                >
                  <span className="analytics-breakdown-label">
                    {key}
                  </span>
                  <span className="analytics-breakdown-value">
                    {val}
                  </span>
                </div>
              ),
            )}
          </div>

          {totalByStatus > 0 && (
            <div className="analytics-progress-bar">
              {Object.entries(data.by_status).map(
                ([key, val]) => (
                  <div
                    key={key}
                    className={
                      "analytics-progress-segment "
                      + key
                    }
                    style={{
                      width: `${
                        (val / totalByStatus) *
                        100
                      }%`,
                    }}
                  />
                ),
              )}
            </div>
          )}
        </div>

        <div className="analytics-card">
          <h3>
            {t("analyticsExecutionsByTrigger")}
          </h3>

          <div className="analytics-breakdown">
            {Object.entries(
              data.by_trigger,
            ).map(([key, val]) => (
              <div
                key={key}
                className="analytics-breakdown-item"
              >
                <span className="analytics-breakdown-label">
                  {key}
                </span>
                <span className="analytics-breakdown-value">
                  {val}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>


      {data.avg_duration_seconds !== null && (
        <div className="analytics-card">
          <h3>
            {t("analyticsAvgDuration")}
          </h3>

          <span className="analytics-stat-value">
            {data.avg_duration_seconds}s
          </span>
        </div>
      )}


      <div className="analytics-row">
        {data.top_by_executions.length > 0 && (
          <div className="analytics-card">
            <h3>
              {t("analyticsTopByExecutions")}
            </h3>

            <div className="analytics-breakdown">
              {data.top_by_executions.map(
                (item) => (
                  <div
                    key={item.name}
                    className="analytics-breakdown-item"
                  >
                    <span className="analytics-breakdown-label">
                      {item.name}
                    </span>
                    <span className="analytics-breakdown-value">
                      {item.execution_count}
                    </span>
                  </div>
                ),
              )}
            </div>
          </div>
        )}

        {data.top_by_failures.length > 0 && (
          <div className="analytics-card">
            <h3>
              {t("analyticsTopByFailures")}
            </h3>

            <div className="analytics-breakdown">
              {data.top_by_failures.map(
                (item) => (
                  <div
                    key={item.name}
                    className="analytics-breakdown-item"
                  >
                    <span className="analytics-breakdown-label">
                      {item.name}
                    </span>
                    <span className="analytics-breakdown-value">
                      {item.failure_count}
                    </span>
                  </div>
                ),
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
