import { useTranslation } from "react-i18next";
import { useEffect, useState } from "react";
import { LoaderCircle } from "lucide-react";
import {
  getAnalyticsCommerce,
  getAnalyticsTimeseries,
  type CommerceAnalytics,
  type TimeseriesPoint,
} from "../services/analytics";


interface Props {
  storeId: number;
  dateFrom?: string;
  dateTo?: string;
}


export default function AnalyticsCommerce({
  storeId,
  dateFrom,
  dateTo,
}: Props) {
  const { t } = useTranslation();

  const [data, setData] =
    useState<CommerceAnalytics | null>(null);

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

      const [commData, tsData] =
        await Promise.all([
          getAnalyticsCommerce(
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

      setData(commData);
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


  const maxOrders = Math.max(
    1,
    ...timeseries.map((p) => p.orders),
  );


  return (
    <div className="analytics-commerce">
      <div className="analytics-stats-grid">
        <div className="analytics-stat-card">
          <div className="analytics-stat-info">
            <span className="analytics-stat-value">
              {data.total_orders}
            </span>
            <span className="analytics-stat-label">
              {t("analyticsStatOrders")}
            </span>
          </div>
        </div>

        <div className="analytics-stat-card">
          <div className="analytics-stat-info">
            <span className="analytics-stat-value">
              {data.total_value.toLocaleString()}
            </span>
            <span className="analytics-stat-label">
              {t("analyticsStatOrderValue")}
            </span>
          </div>
        </div>

        <div className="analytics-stat-card">
          <div className="analytics-stat-info">
            <span className="analytics-stat-value">
              {data.avg_ticket.toLocaleString()}
            </span>
            <span className="analytics-stat-label">
              {t("analyticsAvgTicket")}
            </span>
          </div>
        </div>
      </div>


      <div className="analytics-row">
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
            {t("analyticsOrdersByStatus")}
          </h3>

          <div className="analytics-breakdown">
            {Object.entries(data.by_status).map(
              ([key, val]) => (
                <div
                  key={key ?? "null"}
                  className="analytics-breakdown-item"
                >
                  <span className="analytics-breakdown-label">
                    {key ?? t("analyticsHistorical")}
                  </span>
                  <span className="analytics-breakdown-value">
                    {val}
                  </span>
                </div>
              ),
            )}

            {Object.keys(data.by_status)
              .length === 0
              && (
                <p className="analytics-empty-note">
                  {t("analyticsNoOrders")}
                </p>
              )}
          </div>
        </div>

        <div className="analytics-card">
          <h3>
            {t("analyticsOrdersBySource")}
          </h3>

          <div className="analytics-breakdown">
            {Object.entries(data.by_source).map(
              ([key, val]) => (
                <div
                  key={key ?? "null"}
                  className="analytics-breakdown-item"
                >
                  <span className="analytics-breakdown-label">
                    {key ?? t("analyticsLocal")}
                  </span>
                  <span className="analytics-breakdown-value">
                    {val}
                  </span>
                </div>
              ),
            )}
          </div>
        </div>
      </div>


      {data.top_products.length > 0 && (
        <div className="analytics-card">
          <h3>
            {t("analyticsTopProducts")}
          </h3>

          <div className="analytics-table-wrapper">
            <table className="analytics-table">
              <thead>
                <tr>
                  <th>
                    {t("analyticsProduct")}
                  </th>
                  <th>
                    {t("analyticsUnits")}
                  </th>
                  <th>
                    {t("analyticsOrders")}
                  </th>
                  <th>
                    {t("analyticsValue")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.top_products.map(
                  (p, i) => (
                    <tr key={i}>
                      <td>{p.title}</td>
                      <td>{p.total_units}</td>
                      <td>{p.order_count}</td>
                      <td>
                        {p.total_value.toLocaleString()}
                      </td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
