import { useTranslation } from "react-i18next";
import { useEffect, useState } from "react";
import {
  LoaderCircle,
  Package,
  ShoppingBag,
  TrendingUp,
} from "lucide-react";
import {
  getCommerceSummary,
  type CommerceSummary as SummaryType,
} from "../services/integrations";


interface CommerceSummaryProps {
  storeId: number;
  canWrite: boolean;
}


export default function CommerceSummary({
  storeId,
  canWrite: _canWrite,
}: CommerceSummaryProps) {
  const { t } = useTranslation();

  const [summary, setSummary] =
    useState<SummaryType | null>(null);

  const [loading, setLoading] =
    useState(true);

  const [error, setError] =
    useState("");


  useEffect(() => {
    loadSummary();
  }, [storeId]);


  async function loadSummary() {
    try {
      setLoading(true);
      setError("");

      const data =
        await getCommerceSummary(storeId);

      setSummary(data);
    } catch {
      setError(
        t("commerceSummaryError")
      );
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
        <p>{t("commerceNoData")}</p>
      </div>
    );
  }


  return (
    <div className="commerce-summary">
      <div className="commerce-stats-grid">
        <div className="commerce-stat-card">
          <div className="commerce-stat-icon">
            <Package size={20} />
          </div>
          <div className="commerce-stat-info">
            <span className="commerce-stat-value">
              {summary.total_products}
            </span>
            <span className="commerce-stat-label">
              {t("commerceStatProducts")}
            </span>
          </div>
        </div>

        <div className="commerce-stat-card">
          <div className="commerce-stat-icon">
            <ShoppingBag size={20} />
          </div>
          <div className="commerce-stat-info">
            <span className="commerce-stat-value">
              {summary.total_orders}
            </span>
            <span className="commerce-stat-label">
              {t("commerceStatOrders")}
            </span>
          </div>
        </div>

        <div className="commerce-stat-card">
          <div className="commerce-stat-icon">
            <TrendingUp size={20} />
          </div>
          <div className="commerce-stat-info">
            <span className="commerce-stat-value">
              {summary.currency}{" "}
              {summary.total_order_value.toFixed(
                2,
              )}
            </span>
            <span className="commerce-stat-label">
              {t(
                "commerceStatTotalValue",
              )}
            </span>
          </div>
        </div>
      </div>

      {summary.orders_by_status && (
        <div className="commerce-status-grid">
          <div className="commerce-status-item">
            <span className="commerce-status-dot pending" />
            <span className="commerce-status-count">
              {summary.orders_by_status.pending}
            </span>
            <span className="commerce-status-text">
              {t(
                "commerceStatusPending",
              )}
            </span>
          </div>

          <div className="commerce-status-item">
            <span className="commerce-status-dot created" />
            <span className="commerce-status-count">
              {summary.orders_by_status.created}
            </span>
            <span className="commerce-status-text">
              {t(
                "commerceStatusCreated",
              )}
            </span>
          </div>

          <div className="commerce-status-item">
            <span className="commerce-status-dot failed" />
            <span className="commerce-status-count">
              {summary.orders_by_status.failed}
            </span>
            <span className="commerce-status-text">
              {t(
                "commerceStatusFailed",
              )}
            </span>
          </div>

          <div className="commerce-status-item">
            <span className="commerce-status-dot unknown" />
            <span className="commerce-status-count">
              {summary.orders_by_status.unknown}
            </span>
            <span className="commerce-status-text">
              {t(
                "commerceStatusUnknown",
              )}
            </span>
          </div>
        </div>
      )}

      {summary.recent_orders.length > 0 && (
        <div className="commerce-section">
          <h3>
            {t(
              "commerceRecentOrders",
            )}
          </h3>
          <div className="commerce-recent-list">
            {summary.recent_orders.map(
              (order) => (
                <div
                  key={order.id}
                  className="commerce-recent-item"
                >
                  <span className="commerce-recent-title">
                    #{order.order_number}
                  </span>
                  <span className="commerce-recent-value">
                    {order.currency}{" "}
                    {order.total_amount.toFixed(
                      2,
                    )}
                  </span>
                  <span
                    className={
                      "commerce-recent-badge"
                      + " "
                      + (order.external_creation_status
                        ?? "unknown")
                    }
                  >
                    {order.external_creation_status
                      ?? "—"}
                  </span>
                </div>
              ),
            )}
          </div>
        </div>
      )}

      {summary.recent_products.length > 0 && (
        <div className="commerce-section">
          <h3>
            {t(
              "commerceRecentProducts",
            )}
          </h3>
          <div className="commerce-recent-list">
            {summary.recent_products.map(
              (product) => (
                <div
                  key={product.id}
                  className="commerce-recent-item"
                >
                  <span className="commerce-recent-title">
                    {product.title}
                  </span>
                  <span
                    className={
                      "commerce-recent-badge"
                      + " "
                      + (product.active
                        ? "created"
                        : "failed")
                    }
                  >
                    {product.active
                      ? t(
                          "commerceActive",
                        )
                      : t(
                          "commerceInactive",
                        )}
                  </span>
                </div>
              ),
            )}
          </div>
        </div>
      )}
    </div>
  );
}
