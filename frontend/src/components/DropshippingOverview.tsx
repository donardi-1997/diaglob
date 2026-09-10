import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  DollarSign,
  LoaderCircle,
  PackageCheck,
  Percent,
  ShoppingCart,
  Target,
  Truck,
} from "lucide-react";
import {
  getDropshippingOrders,
  getDropshippingOverview,
  getDropshippingProducts,
  getDropshippingProfitability,
  type DropshippingOrders,
  type DropshippingOverview,
  type DropshippingProduct,
  type DropshippingProfitability,
} from "../services/analytics";
import {
  allDropshippingSectionsFailed,
  getFailedDropshippingSections,
  settledValue,
  type DropshippingAnalyticsSection,
} from "../utils/dropshippingAnalyticsState";

interface Props {
  storeId: number;
  currency: string;
  dateFrom?: string;
  dateTo?: string;
}

interface DashboardData {
  overview: DropshippingOverview | null;
  profitability: DropshippingProfitability | null;
  products: DropshippingProduct[] | null;
  orders: DropshippingOrders | null;
}

const SECTION_LABELS: Record<DropshippingAnalyticsSection, string> = {
  overview: "resumen operativo",
  profitability: "rentabilidad",
  products: "productos",
  orders: "embudo de pedidos",
};

function SectionUnavailable() {
  return (
    <div className="commerce-empty">
      Temporalmente no disponible. El resto de las analíticas sigue activo.
    </div>
  );
}

export default function DropshippingOverview({
  storeId,
  currency,
  dateFrom,
  dateTo,
}: Props) {
  const { t } = useTranslation();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [unavailableSections, setUnavailableSections] = useState<
    DropshippingAnalyticsSection[]
  >([]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    setData(null);
    setUnavailableSections([]);

    Promise.allSettled([
      getDropshippingOverview(storeId, dateFrom, dateTo),
      getDropshippingProfitability(storeId, dateFrom, dateTo),
      getDropshippingProducts(storeId, dateFrom, dateTo),
      getDropshippingOrders(storeId, dateFrom, dateTo),
    ])
      .then((results) => {
        if (cancelled) return;

        const failedSections = getFailedDropshippingSections(results);
        setUnavailableSections(failedSections);

        if (allDropshippingSectionsFailed(failedSections)) {
          setError(t("analyticsLoadError"));
          return;
        }

        setData({
          overview: settledValue(results[0]),
          profitability: settledValue(results[1]),
          products: settledValue(results[2]),
          orders: settledValue(results[3]),
        });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [storeId, dateFrom, dateTo, t]);

  const topProducts = useMemo(
    () => data?.products?.slice(0, 10) ?? [],
    [data],
  );

  if (loading) {
    return (
      <div className="commerce-loading">
        <LoaderCircle className="spin" size={24} /> {t("analyticsLoading")}
      </div>
    );
  }

  if (error) {
    return <div className="commerce-empty">{error}</div>;
  }

  if (!data) {
    return <div className="commerce-empty">{t("analyticsNoData")}</div>;
  }

  const { overview, profitability, products, orders } = data;
  const effectiveCurrency = overview?.currency || currency;
  const unavailableLabels = unavailableSections.map(
    (section) => SECTION_LABELS[section],
  );

  const formatCurrency = (value: number | null) => {
    if (value === null || value === undefined) return "—";
    try {
      return new Intl.NumberFormat("es-CO", {
        style: "currency",
        currency: effectiveCurrency,
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
      }).format(value);
    } catch {
      return `${value} ${effectiveCurrency}`;
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
      {unavailableLabels.length > 0 && (
        <div className="stores-alert" style={{ marginBottom: 16 }}>
          <AlertTriangle size={16} />
          <span>
            Algunas analíticas no están disponibles temporalmente: {unavailableLabels.join(", ")}.
            Los demás datos continúan visibles.
          </span>
        </div>
      )}

      {(overview || profitability) && (
        <div className="analytics-stats-grid">
          {overview && (
            <>
              <div className="analytics-stat-card">
                <div className="analytics-stat-icon"><Truck size={18} /></div>
                <div className="analytics-stat-value">{overview.delivered_orders}</div>
                <div className="analytics-stat-label">{t("dsDeliveredOrders")}</div>
                <Delta value={overview.comparison?.delivered_orders_pct ?? null} />
              </div>

              <div className="analytics-stat-card">
                <div className="analytics-stat-icon"><DollarSign size={18} /></div>
                <div className="analytics-stat-value">{formatCurrency(overview.delivered_revenue)}</div>
                <div className="analytics-stat-label">{t("dsDeliveredRevenue")}</div>
                <Delta value={overview.comparison?.delivered_revenue_pct ?? null} />
              </div>

              <div className="analytics-stat-card">
                <div className="analytics-stat-icon"><Target size={18} /></div>
                <div className="analytics-stat-value">{formatRate(overview.delivery_rate)}</div>
                <div className="analytics-stat-label">{t("dsDeliveryRate")}</div>
                <Delta value={overview.comparison?.delivery_rate_pp ?? null} suffix=" pp" />
              </div>
            </>
          )}

          {profitability && (
            <div className="analytics-stat-card">
              <div className="analytics-stat-icon"><DollarSign size={18} /></div>
              <div className="analytics-stat-value">{formatCurrency(profitability.gross_profit)}</div>
              <div className="analytics-stat-label">Utilidad bruta</div>
              <Delta value={overview?.comparison?.gross_profit_pct ?? null} />
            </div>
          )}
        </div>
      )}

      {!overview && (
        <div className="analytics-card">
          <h3><Target size={17} /> Resumen operativo</h3>
          <SectionUnavailable />
        </div>
      )}

      {profitability && !profitability.profitability_complete && (
        <div className="stores-alert" style={{ marginBottom: 16 }}>
          <AlertTriangle size={16} />
          <span>
            Rentabilidad parcial: {formatRate(profitability.cost_completeness_pct)} de los ítems entregados tienen costo registrado.
            Completa los costos para obtener utilidad y margen confiables.
          </span>
        </div>
      )}

      <div className="analytics-row">
        <div className="analytics-card">
          <h3><DollarSign size={17} /> Rentabilidad entregada</h3>
          {profitability ? (
            <div className="analytics-metrics-list">
              <div className="analytics-metric-row">
                <span>Ingresos entregados</span>
                <span className="analytics-metric-value">{formatCurrency(profitability.delivered_revenue)}</span>
              </div>
              <div className="analytics-metric-row">
                <span>COGS</span>
                <span className="analytics-metric-value">{formatCurrency(profitability.total_cogs)}</span>
              </div>
              <div className="analytics-metric-row">
                <span>Utilidad bruta</span>
                <span className="analytics-metric-value">{formatCurrency(profitability.gross_profit)}</span>
              </div>
              <div className="analytics-metric-row">
                <span>Margen bruto</span>
                <span className="analytics-metric-value">{formatRate(profitability.gross_margin)}</span>
              </div>
              <div className="analytics-metric-row">
                <span>Utilidad por pedido entregado</span>
                <span className="analytics-metric-value">{formatCurrency(profitability.profit_per_delivered_order)}</span>
              </div>
            </div>
          ) : (
            <SectionUnavailable />
          )}
        </div>

        <div className="analytics-card">
          <h3><Percent size={17} /> Calidad operativa</h3>
          {overview || profitability ? (
            <div className="analytics-metrics-list">
              {overview && (
                <>
                  <div className="analytics-metric-row">
                    <span>{t("dsConfirmationRate")}</span>
                    <span className="analytics-metric-value">{formatRate(overview.confirmation_rate)}</span>
                  </div>
                  <div className="analytics-metric-row">
                    <span>{t("dsDeliveryRate")}</span>
                    <span className="analytics-metric-value">{formatRate(overview.delivery_rate)}</span>
                  </div>
                  <div className="analytics-metric-row">
                    <span>{t("dsCancellationRate")}</span>
                    <span className="analytics-metric-value">{formatRate(overview.cancellation_rate)}</span>
                  </div>
                  <div className="analytics-metric-row">
                    <span>{t("dsReturnRate")}</span>
                    <span className="analytics-metric-value">{formatRate(overview.return_rate)}</span>
                  </div>
                </>
              )}
              {profitability && (
                <div className="analytics-metric-row">
                  <span>Completitud de costos</span>
                  <span className="analytics-metric-value">{formatRate(profitability.cost_completeness_pct)}</span>
                </div>
              )}
            </div>
          ) : (
            <SectionUnavailable />
          )}
        </div>
      </div>

      <div className="analytics-card">
        <h3><ShoppingCart size={17} /> {t("dsFunnel")}</h3>
        {orders ? (
          <>
            <div className="funnel">
              <div className="funnel-step">
                <span className="funnel-value">{orders.total}</span>
                <span className="funnel-label">{t("dsCreated")}</span>
              </div>
              <div className="funnel-arrow">→</div>
              <div className="funnel-step">
                <span className="funnel-value">{orders.confirmed}</span>
                <span className="funnel-label">{t("dsConfirmed")}</span>
              </div>
              <div className="funnel-arrow">→</div>
              <div className="funnel-step">
                <span className="funnel-value">{orders.shipped}</span>
                <span className="funnel-label">{t("dsShipped")}</span>
              </div>
              <div className="funnel-arrow">→</div>
              <div className="funnel-step">
                <span className="funnel-value">{orders.delivered}</span>
                <span className="funnel-label">{t("dsDelivered")}</span>
              </div>
            </div>
            <div className="analytics-metrics-list" style={{ marginTop: 16 }}>
              <div className="analytics-metric-row">
                <span>Cancelados</span>
                <span className="analytics-metric-value">{orders.cancelled}</span>
              </div>
              <div className="analytics-metric-row">
                <span>Devueltos</span>
                <span className="analytics-metric-value">{orders.returned}</span>
              </div>
              {orders.unknown > 0 && (
                <div className="analytics-metric-row">
                  <span>Estado desconocido</span>
                  <span className="analytics-metric-value">{orders.unknown}</span>
                </div>
              )}
            </div>
          </>
        ) : (
          <SectionUnavailable />
        )}
      </div>

      {overview?.comparison && (
        <div className="analytics-card">
          <h3>Comparación con período anterior</h3>
          <div className="analytics-metrics-list">
            <div className="analytics-metric-row">
              <span>Pedidos creados</span>
              <span className="analytics-metric-value">{formatDelta(overview.comparison.total_orders_pct) ?? "—"}</span>
            </div>
            <div className="analytics-metric-row">
              <span>Ticket promedio entregado</span>
              <span className="analytics-metric-value">{formatDelta(overview.comparison.delivered_aov_pct) ?? "—"}</span>
            </div>
            <div className="analytics-metric-row">
              <span>Utilidad bruta</span>
              <span className="analytics-metric-value">{formatDelta(overview.comparison.gross_profit_pct) ?? "—"}</span>
            </div>
            <div className="analytics-metric-row">
              <span>Margen bruto</span>
              <span className="analytics-metric-value">{formatDelta(overview.comparison.gross_margin_pp, " pp") ?? "—"}</span>
            </div>
            <div className="analytics-metric-row">
              <span>Tasa de cancelación</span>
              <span className="analytics-metric-value">{formatDelta(overview.comparison.cancellation_rate_pp, " pp") ?? "—"}</span>
            </div>
          </div>
        </div>
      )}

      <div className="analytics-card">
        <h3><PackageCheck size={17} /> Productos más rentables · entregados</h3>
        {products === null ? (
          <SectionUnavailable />
        ) : topProducts.length === 0 ? (
          <div className="commerce-empty">No hay productos entregados en el período seleccionado.</div>
        ) : (
          <div className="analytics-metrics-list">
            {topProducts.map((product, index) => (
              <div className="analytics-metric-row" key={product.product_id}>
                <span>
                  <strong>#{index + 1} {product.title}</strong>
                  <small style={{ display: "block", opacity: 0.7 }}>
                    {product.units_delivered} unidades · {product.sku || "Sin SKU"} · costo {formatRate(product.cost_completeness_pct)}
                  </small>
                </span>
                <span style={{ textAlign: "right" }}>
                  <strong className="analytics-metric-value">{formatCurrency(product.gross_profit)}</strong>
                  <small style={{ display: "block", opacity: 0.7 }}>
                    margen {formatRate(product.gross_margin)} · ingresos {formatCurrency(product.delivered_revenue)}
                  </small>
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
