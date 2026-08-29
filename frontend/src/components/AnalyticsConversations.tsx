import { useTranslation } from "react-i18next";
import { useEffect, useState } from "react";
import { LoaderCircle } from "lucide-react";
import {
  getAnalyticsConversations,
  getAnalyticsTimeseries,
  type ConversationsAnalytics,
  type TimeseriesPoint,
} from "../services/analytics";


interface Props {
  storeId: number;
  dateFrom?: string;
  dateTo?: string;
}


export default function AnalyticsConversations({
  storeId,
  dateFrom,
  dateTo,
}: Props) {
  const { t } = useTranslation();

  const [data, setData] =
    useState<ConversationsAnalytics | null>(null);

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

      const [convData, tsData] =
        await Promise.all([
          getAnalyticsConversations(
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

      setData(convData);
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


  const maxConv = Math.max(
    1,
    ...timeseries.map((p) => p.conversations),
  );

  const maxMsg = Math.max(
    1,
    ...timeseries.map((p) => p.messages),
  );


  return (
    <div className="analytics-conversations">
      <div className="analytics-stats-grid">
        <div className="analytics-stat-card">
          <div className="analytics-stat-info">
            <span className="analytics-stat-value">
              {data.total_conversations.toLocaleString()}
            </span>
            <span className="analytics-stat-label">
              {t(
                "analyticsStatConversations",
              )}
            </span>
          </div>
        </div>

        <div className="analytics-stat-card">
          <div className="analytics-stat-info">
            <span className="analytics-stat-value">
              {data.total_messages.toLocaleString()}
            </span>
            <span className="analytics-stat-label">
              {t("analyticsStatMessages")}
            </span>
          </div>
        </div>

        <div className="analytics-stat-card">
          <div className="analytics-stat-info">
            <span className="analytics-stat-value">
              {
                data.avg_messages_per_conversation
              }
            </span>
            <span className="analytics-stat-label">
              {t(
                "analyticsAvgMessagesPerConv",
              )}
            </span>
          </div>
        </div>
      </div>


      <div className="analytics-row">
        <div className="analytics-card">
          <h3>
            {t("analyticsConversationsPerDay")}
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
                          (p.conversations /
                            maxConv) *
                          100
                        }%`,
                      }}
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
                            maxMsg) *
                          100
                        }%`,
                      }}
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
            {t("analyticsByChannel")}
          </h3>

          <div className="analytics-breakdown">
            {Object.entries(
              data.by_channel,
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

            {Object.keys(data.by_channel)
              .length === 0
              && (
                <p className="analytics-empty-note">
                  {t("analyticsNoData")}
                </p>
              )}
          </div>
        </div>

        <div className="analytics-card">
          <h3>
            {t("analyticsByMode")}
          </h3>

          <div className="analytics-breakdown">
            {Object.entries(data.by_mode).map(
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
        </div>

        <div className="analytics-card">
          <h3>
            {t("analyticsSenderDistribution")}
          </h3>

          <div className="analytics-breakdown">
            {Object.entries(
              data.sender_distribution,
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
    </div>
  );
}
