import { useTranslation } from "react-i18next";
import { useState, useEffect } from "react";
import {
  DollarSign,
  ShoppingCart,
  Target,
  Truck,
  LoaderCircle,
} from "lucide-react";
import { getDropshippingOverview, type DropshippingOverview } from "../services/analytics";

interface Props {
  storeId: number;
  currency: string;
  dateFrom?: string;
  dateTo?: string;
}

export default function DropshippingOverview({ storeId, currency, dateFrom, dateTo }: Props) {
  const { t } = useTranslation();
  const [data, setData] = useState<DropshippingOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");

    getDropshippingOverview(storeId, dateFrom, dateTo)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err: any) => {
        if (!cancelled) {
          console.error(err);
          setError(err?.response?.data?.detail || t("analyticsLoadError"));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [storeId, dateFrom, dateTo]);

  if (loading) {
    return <div className="commerce-loading"><LoaderCircle className="spin" size={24} /> {t("analyticsLoading")}</div>;
  }

  if (error) {
    return <div className="commerce-empty">{error}</div>;
  }

  if (!data) {
    return <div className="commerce-empty">{t("analyticsNoData")}</div>;
  }

  const formatCurrency = (value: number | null) => {
    if (value === null || value === undefined) return "—";
    try {
      return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency,
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
      }).format(value);
    } catch {
      return `${value} ${currency}`;
    }
  };

  const formatRate = (value: number | null) => {
    if (value === null || value === undefined) return "—";
    return `${value}%`;
  };

  const formatDelta = (value: number | null, suffix = "%") => {
    if (value === null || value === undefined) return null;
    const sign = value > 0 ? "+" : "";
    return `${sign}${value}${suffix}`;
  };

  const Delta = ({ value, suffix = "%" }: { value: number | null; suffix?: string }) => {
    const formatted = formatDelta(value, suffix);
    if (!formatted) return null;
    return <div className="analytics-stat-delta">{formatted} vs. período anterior</div>;
  };

  return (
    <div className="dropshipping-overview">
      <div className="analytics-stats-grid">
        <div className="analytics-stat-card">
          <div className="analytics-stat-icon"><Truck size={18} /></div>
          <div className="analytics-stat-value">{data.delivered_orders}</div>
          <div className="analytics-stat-label">{t("dsDeliveredOrders")}</div>
          <Delta value={data.comparison?.delivered_orders_pct ?? null} />
        </div>
        <div className="analytics-stat-card">
          <div className="analytics-stat-icon"><DollarSign size={18} /></div>
          <div className="analytics-stat-value">{formatCurrency(data.delivered_revenue)}</div>
          <div className="analytics-stat-label">{t("dsDeliveredRevenue")}</div>
          <Delta value={data.comparison?.delivered_revenue_pct ?? null} />
        </div>
        <div className="analytics-stat-card">
          <div className="analytics-stat-icon"><Target size={18} /></div>
          <div className="analytics-stat-value">{formatRate(data.delivery_rate)}</div>
          <div className="analytics-stat-label">{t("dsDeliveryRate")}</div>
          <Delta value={data.comparison?.delivery_rate_pp ?? null} suffix=" pp" />
        </div>
        <div className="analytics-stat-card">
          <div className="analytics-stat-icon"><ShoppingCart size={18} /></div>
          <div className="analytics-stat-value">{data.total_orders}</div>
          <div className="analytics-stat-label">{t("dsOrdersCreated")}</div>
          <Delta value={data.comparison?.total_orders_pct ?? null} />
        </div>
      </div>

      {data.comparison && (
        <div className="analytics-card">
          <h3>Comparación con período anterior</h3>
          <div className="analytics-metrics-list">
            <div className="analytics-metric-row">
              <span>Ticket promedio entregado</span>
              <span className="analytics-metric-value">{formatDelta(data.comparison.delivered_aov_pct) ?? "—"}</span>
            </div>
            <div className="analytics-metric-row">
              <span>Utilidad bruta</span>
              <span className="analytics-metric-value">{formatDelta(data.comparison.gross_profit_pct) ?? "—"}</span>
            </div>
            <div className="analytics-metric-row">
              <span>Margen bruto</span>
              <span className="analytics-metric-value">{formatDelta(data.comparison.gross_margin_pp, " pp") ?? "—"}</span>
            </div>
            <div className="analytics-metric-row">
              <span>Tasa de cancelación</span>
              <span className="analytics-metric-value">{formatDelta(data.comparison.cancellation_rate_pp, " pp") ?? "—"}</span>
            </div>
          </div>
        </div>
      )}

      <div className="analytics-row">
        <div className="analytics-card">
          <h3>{t("dsFunnel")}</h3>
          <div className="funnel">
            <div className="funnel-step">
              <span className="funnel-value">{data.total_orders}</span>
              <span className="funnel-label">{t("dsCreated")}</span>
            </div>
            <div className="funnel-arrow">→</div>
            <div className="funnel-step">
              <span className="funnel-value">{data.confirmed_orders}</span>
              <span className="funnel-label">{t("dsConfirmed")}</span>
            </div>
            <div className="funnel-arrow">→</div>
            <div className="funnel-step">
              <span className="funnel-value">{data.shipped_orders}</span>
              <span className="funnel-label">{t("dsShipped")}</span>
            </div>
            <div className="funnel-arrow">→</div>
            <div className="funnel-step">
              <span className="funnel-value">{data.delivered_orders}</span>
              <span className="funnel-label">{t("dsDelivered")}</span>
            </div>
          </div>
        </div>

        <div className="analytics-card">
          <h3>{t("dsRates")}</h3>
          <div className="analytics-metrics-list">
            <div className="analytics-metric-row">
              <span>{t("dsConfirmationRate")}</span>
              <span className="analytics-metric-value">{formatRate(data.confirmation_rate)}</span>
            </div>
            <div className="analytics-metric-row">
              <span>{t("dsDeliveryRate")}</span>
              <span className="analytics-metric-value">{formatRate(data.delivery_rate)}</span>
            </div>
            <div className="analytics-metric-row">
              <span>{t("dsCancellationRate")}</span>
              <span className="analytics-metric-value">{formatRate(data.cancellation_rate)}</span>
            </div>
            <div className="analytics-metric-row">
              <span>{t("dsReturnRate")}</span>
              <span className="analytics-metric-value">{formatRate(data.return_rate)}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
