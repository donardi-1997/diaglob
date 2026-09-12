import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Boxes,
  ChevronRight,
  LoaderCircle,
  PackageSearch,
  Search,
  TrendingUp,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  getDropshippingProductDetail,
  type DropshippingProduct,
  type DropshippingProductDetail,
} from "../services/analytics";
import "../product-analytics-v2.css";

type SortKey =
  | "gross_profit"
  | "gross_margin"
  | "delivered_revenue"
  | "delivery_rate"
  | "cancellation_rate"
  | "return_rate"
  | "total_orders";

type LocaleKey = "es" | "en" | "pt-BR";

interface Props {
  storeId: number;
  currency: string;
  products: DropshippingProduct[] | null;
  selectedProductId: number | null;
  onSelectedProductChange: (productId: number | null) => void;
  dateFrom?: string;
  dateTo?: string;
}

const COPY = {
  es: {
    kicker: "PRODUCT ANALYTICS",
    title: "Rendimiento por producto",
    subtitle: "Compara ventas, entrega, devoluciones y rentabilidad. Abre un producto para ver su diagnóstico completo.",
    search: "Buscar por producto o SKU...",
    empty: "No hay productos con pedidos en el período seleccionado.",
    unavailable: "Las analíticas por producto no están disponibles temporalmente.",
    product: "Producto",
    orders: "Pedidos",
    delivered: "Entregados",
    delivery: "Entrega",
    cancelled: "Cancelación",
    returns: "Devolución",
    revenue: "Ingresos",
    profit: "Utilidad",
    margin: "Margen",
    stock: "Stock actual",
    detail: "Ver detalle",
    loading: "Cargando detalle del producto...",
    detailError: "No se pudo cargar el detalle de este producto.",
    close: "Cerrar detalle",
    profitPerUnit: "Utilidad / unidad",
    revenueShare: "Participación ingresos",
    profitShare: "Participación utilidad",
    costCoverage: "Cobertura de costos",
    partialCosts: "La utilidad es parcial porque no todos los ítems entregados tienen costo registrado.",
    funnel: "Lifecycle del producto",
    created: "Creados",
    confirmed: "Confirmados",
    shipped: "Enviados",
    returned: "Devueltos",
    cancelledCount: "Cancelados",
    comparison: "Vs. período anterior",
    noComparison: "Selecciona un rango completo para comparar con el período anterior.",
    trend: "Evolución diaria",
    noTrend: "No hay movimiento diario para este producto en el período.",
    variants: "Rendimiento por variante",
    noVariants: "Este producto no tiene variantes registradas.",
    variant: "Variante",
    units: "Unidades",
    currentInventory: "Inventario",
    sku: "SKU",
    previous: "período anterior",
  },
  en: {
    kicker: "PRODUCT ANALYTICS",
    title: "Product performance",
    subtitle: "Compare sales, delivery, returns and profitability. Open a product for its complete diagnostic.",
    search: "Search product or SKU...",
    empty: "No products with orders in the selected period.",
    unavailable: "Product analytics are temporarily unavailable.",
    product: "Product",
    orders: "Orders",
    delivered: "Delivered",
    delivery: "Delivery",
    cancelled: "Cancellation",
    returns: "Return",
    revenue: "Revenue",
    profit: "Profit",
    margin: "Margin",
    stock: "Current stock",
    detail: "View detail",
    loading: "Loading product detail...",
    detailError: "Could not load this product's detail.",
    close: "Close detail",
    profitPerUnit: "Profit / unit",
    revenueShare: "Revenue share",
    profitShare: "Profit share",
    costCoverage: "Cost coverage",
    partialCosts: "Profitability is partial because not every delivered item has a recorded cost.",
    funnel: "Product lifecycle",
    created: "Created",
    confirmed: "Confirmed",
    shipped: "Shipped",
    returned: "Returned",
    cancelledCount: "Cancelled",
    comparison: "Vs. previous period",
    noComparison: "Select a complete range to compare against the previous period.",
    trend: "Daily trend",
    noTrend: "No daily activity for this product in the selected period.",
    variants: "Performance by variant",
    noVariants: "This product has no registered variants.",
    variant: "Variant",
    units: "Units",
    currentInventory: "Inventory",
    sku: "SKU",
    previous: "previous period",
  },
  "pt-BR": {
    kicker: "PRODUCT ANALYTICS",
    title: "Desempenho por produto",
    subtitle: "Compare vendas, entrega, devoluções e rentabilidade. Abra um produto para ver o diagnóstico completo.",
    search: "Buscar produto ou SKU...",
    empty: "Não há produtos com pedidos no período selecionado.",
    unavailable: "As análises por produto estão temporariamente indisponíveis.",
    product: "Produto",
    orders: "Pedidos",
    delivered: "Entregues",
    delivery: "Entrega",
    cancelled: "Cancelamento",
    returns: "Devolução",
    revenue: "Receita",
    profit: "Lucro",
    margin: "Margem",
    stock: "Estoque atual",
    detail: "Ver detalhe",
    loading: "Carregando detalhe do produto...",
    detailError: "Não foi possível carregar o detalhe deste produto.",
    close: "Fechar detalhe",
    profitPerUnit: "Lucro / unidade",
    revenueShare: "Participação receita",
    profitShare: "Participação lucro",
    costCoverage: "Cobertura de custos",
    partialCosts: "A rentabilidade é parcial porque nem todos os itens entregues têm custo registrado.",
    funnel: "Lifecycle do produto",
    created: "Criados",
    confirmed: "Confirmados",
    shipped: "Enviados",
    returned: "Devolvidos",
    cancelledCount: "Cancelados",
    comparison: "Vs. período anterior",
    noComparison: "Selecione um intervalo completo para comparar com o período anterior.",
    trend: "Evolução diária",
    noTrend: "Não há movimento diário para este produto no período.",
    variants: "Desempenho por variante",
    noVariants: "Este produto não possui variantes registradas.",
    variant: "Variante",
    units: "Unidades",
    currentInventory: "Estoque",
    sku: "SKU",
    previous: "período anterior",
  },
} as const;

function normalizeLocale(language: string): LocaleKey {
  if (language.toLowerCase().startsWith("pt")) return "pt-BR";
  if (language.toLowerCase().startsWith("en")) return "en";
  return "es";
}

function numericValue(product: DropshippingProduct, key: SortKey): number {
  const value = product[key];
  return typeof value === "number" ? value : Number.NEGATIVE_INFINITY;
}

export default function ProductPerformanceAnalytics({
  storeId,
  currency,
  products,
  selectedProductId,
  onSelectedProductChange,
  dateFrom,
  dateTo,
}: Props) {
  const { i18n } = useTranslation();
  const locale = normalizeLocale(i18n.resolvedLanguage || i18n.language || "es");
  const copy = COPY[locale];
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("gross_profit");
  const [descending, setDescending] = useState(true);
  const [detail, setDetail] = useState<DropshippingProductDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");

  useEffect(() => {
    if (selectedProductId === null) {
      setDetail(null);
      setDetailError("");
      return;
    }

    let cancelled = false;
    setDetailLoading(true);
    setDetailError("");

    getDropshippingProductDetail(
      storeId,
      selectedProductId,
      dateFrom,
      dateTo,
    )
      .then((result) => {
        if (!cancelled) setDetail(result);
      })
      .catch(() => {
        if (!cancelled) {
          setDetail(null);
          setDetailError(copy.detailError);
        }
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedProductId, storeId, dateFrom, dateTo, copy.detailError]);

  const visibleProducts = useMemo(() => {
    if (!products) return [];
    const normalized = search.trim().toLowerCase();
    const filtered = normalized
      ? products.filter((product) =>
          `${product.title} ${product.sku || ""}`.toLowerCase().includes(normalized),
        )
      : [...products];

    return filtered.sort((a, b) => {
      const delta = numericValue(a, sortKey) - numericValue(b, sortKey);
      if (delta !== 0) return descending ? -delta : delta;
      return a.title.localeCompare(b.title);
    });
  }, [products, search, sortKey, descending]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setDescending((current) => !current);
      return;
    }
    setSortKey(key);
    setDescending(true);
  }

  function formatCurrency(value: number | null) {
    if (value === null || value === undefined) return "—";
    try {
      return new Intl.NumberFormat(locale === "es" ? "es-CO" : locale, {
        style: "currency",
        currency,
        maximumFractionDigits: 0,
      }).format(value);
    } catch {
      return `${value.toLocaleString()} ${currency}`;
    }
  }

  function formatRate(value: number | null) {
    return value === null || value === undefined ? "—" : `${value}%`;
  }

  function sortHeader(label: string, key: SortKey) {
    const active = sortKey === key;
    return (
      <button
        type="button"
        className={`product-analytics-sort ${active ? "is-active" : ""}`}
        onClick={() => toggleSort(key)}
      >
        {label}
        {active && (descending ? <ArrowDown size={12} /> : <ArrowUp size={12} />)}
      </button>
    );
  }

  if (products === null) {
    return (
      <section className="product-analytics-shell">
        <div className="product-analytics-empty">
          <AlertTriangle size={20} />
          <span>{copy.unavailable}</span>
        </div>
      </section>
    );
  }

  return (
    <section className="product-analytics-shell">
      <div className="product-analytics-heading">
        <div>
          <span>{copy.kicker}</span>
          <h3><PackageSearch size={19} /> {copy.title}</h3>
          <p>{copy.subtitle}</p>
        </div>
        <div className="product-analytics-search">
          <Search size={15} />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={copy.search}
          />
        </div>
      </div>

      {visibleProducts.length === 0 ? (
        <div className="product-analytics-empty">
          <PackageSearch size={22} />
          <span>{copy.empty}</span>
        </div>
      ) : (
        <div className="product-analytics-table-wrap">
          <table className="product-analytics-table">
            <thead>
              <tr>
                <th>{copy.product}</th>
                <th>{sortHeader(copy.orders, "total_orders")}</th>
                <th>{copy.delivered}</th>
                <th>{sortHeader(copy.delivery, "delivery_rate")}</th>
                <th>{sortHeader(copy.cancelled, "cancellation_rate")}</th>
                <th>{sortHeader(copy.returns, "return_rate")}</th>
                <th>{sortHeader(copy.revenue, "delivered_revenue")}</th>
                <th>{sortHeader(copy.profit, "gross_profit")}</th>
                <th>{sortHeader(copy.margin, "gross_margin")}</th>
              </tr>
            </thead>
            <tbody>
              {visibleProducts.map((product) => {
                const selected = selectedProductId === product.product_id;
                return (
                  <tr key={product.product_id} className={selected ? "is-selected" : ""}>
                    <td>
                      <button
                        type="button"
                        className="product-analytics-product-button"
                        onClick={() => onSelectedProductChange(selected ? null : product.product_id)}
                      >
                        <span className="product-analytics-product-icon"><Boxes size={15} /></span>
                        <span>
                          <strong>{product.title}</strong>
                          <small>{product.sku || copy.sku} · {copy.stock}: {product.inventory_quantity}</small>
                        </span>
                        <ChevronRight size={14} className={selected ? "is-open" : ""} />
                      </button>
                    </td>
                    <td>{product.total_orders}</td>
                    <td>{product.delivered_orders}</td>
                    <td><RateBadge value={product.delivery_rate} /></td>
                    <td><RateBadge value={product.cancellation_rate} inverse /></td>
                    <td><RateBadge value={product.return_rate} inverse /></td>
                    <td>{formatCurrency(product.delivered_revenue)}</td>
                    <td className={product.gross_profit < 0 ? "is-negative" : "is-positive"}>
                      {formatCurrency(product.gross_profit)}
                    </td>
                    <td>{formatRate(product.gross_margin)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {selectedProductId !== null && (
        <div className="product-analytics-detail">
          {detailLoading ? (
            <div className="product-analytics-detail-loading">
              <LoaderCircle className="spin" size={20} /> {copy.loading}
            </div>
          ) : detailError ? (
            <div className="product-analytics-empty">
              <AlertTriangle size={18} /> {detailError}
            </div>
          ) : detail ? (
            <ProductDetail
              detail={detail}
              copy={copy}
              formatCurrency={formatCurrency}
              formatRate={formatRate}
              onClose={() => onSelectedProductChange(null)}
            />
          ) : null}
        </div>
      )}
    </section>
  );
}

function RateBadge({ value, inverse = false }: { value: number | null; inverse?: boolean }) {
  if (value === null || value === undefined) return <span className="product-rate is-muted">—</span>;
  const good = inverse ? value <= 10 : value >= 70;
  const warning = inverse ? value > 10 && value <= 25 : value >= 45 && value < 70;
  const tone = good ? "is-good" : warning ? "is-warning" : "is-risk";
  return <span className={`product-rate ${tone}`}>{value}%</span>;
}

function ProductDetail({
  detail,
  copy,
  formatCurrency,
  formatRate,
  onClose,
}: {
  detail: DropshippingProductDetail;
  copy: (typeof COPY)[LocaleKey];
  formatCurrency: (value: number | null) => string;
  formatRate: (value: number | null) => string;
  onClose: () => void;
}) {
  const metrics = detail.metrics;
  const comparison = detail.comparison;
  const maxRevenue = Math.max(1, ...detail.timeseries.map((point) => point.delivered_revenue));

  const delta = (value: number | null, suffix = "%") => {
    if (value === null || value === undefined) return "—";
    return `${value > 0 ? "+" : ""}${value}${suffix}`;
  };

  return (
    <div className="product-detail-card">
      <div className="product-detail-header">
        <div>
          <span>{copy.detail}</span>
          <h4>{detail.product.title}</h4>
          <p>{metrics.sku || "—"} · {copy.stock}: {metrics.inventory_quantity}</p>
        </div>
        <button type="button" onClick={onClose} aria-label={copy.close}>
          <X size={17} />
        </button>
      </div>

      {!metrics.profitability_complete && metrics.delivered_orders > 0 && (
        <div className="product-detail-warning">
          <AlertTriangle size={15} />
          <span>{copy.partialCosts} {copy.costCoverage}: {formatRate(metrics.cost_completeness_pct)}</span>
        </div>
      )}

      <div className="product-detail-kpis">
        <Metric label={copy.revenue} value={formatCurrency(metrics.delivered_revenue)} />
        <Metric label={copy.profit} value={formatCurrency(metrics.gross_profit)} tone={metrics.gross_profit < 0 ? "negative" : "positive"} />
        <Metric label={copy.margin} value={formatRate(metrics.gross_margin)} />
        <Metric label={copy.profitPerUnit} value={formatCurrency(metrics.profit_per_unit)} />
        <Metric label={copy.revenueShare} value={formatRate(metrics.revenue_share_pct)} />
        <Metric label={copy.profitShare} value={formatRate(metrics.profit_share_pct)} />
      </div>

      <div className="product-detail-grid">
        <article className="product-detail-section">
          <h5><Boxes size={15} /> {copy.funnel}</h5>
          <div className="product-lifecycle-grid">
            <Metric label={copy.created} value={String(metrics.total_orders)} compact />
            <Metric label={copy.confirmed} value={String(metrics.confirmed_orders)} compact />
            <Metric label={copy.shipped} value={String(metrics.shipped_orders)} compact />
            <Metric label={copy.delivered} value={String(metrics.delivered_orders)} compact />
            <Metric label={copy.cancelledCount} value={String(metrics.cancelled_orders)} compact />
            <Metric label={copy.returned} value={String(metrics.returned_orders)} compact />
          </div>
          <div className="product-rate-summary">
            <div><span>{copy.delivery}</span><strong>{formatRate(metrics.delivery_rate)}</strong></div>
            <div><span>{copy.cancelled}</span><strong>{formatRate(metrics.cancellation_rate)}</strong></div>
            <div><span>{copy.returns}</span><strong>{formatRate(metrics.return_rate)}</strong></div>
          </div>
        </article>

        <article className="product-detail-section">
          <h5><TrendingUp size={15} /> {copy.comparison}</h5>
          {comparison ? (
            <div className="product-comparison-list">
              <div><span>{copy.orders}</span><strong>{delta(comparison.total_orders_pct)}</strong></div>
              <div><span>{copy.delivered}</span><strong>{delta(comparison.delivered_orders_pct)}</strong></div>
              <div><span>{copy.revenue}</span><strong>{delta(comparison.delivered_revenue_pct)}</strong></div>
              <div><span>{copy.profit}</span><strong>{delta(comparison.gross_profit_pct)}</strong></div>
              <div><span>{copy.margin}</span><strong>{delta(comparison.gross_margin_pp, " pp")}</strong></div>
              <div><span>{copy.delivery}</span><strong>{delta(comparison.delivery_rate_pp, " pp")}</strong></div>
            </div>
          ) : (
            <p className="product-detail-note">{copy.noComparison}</p>
          )}
        </article>
      </div>

      <article className="product-detail-section product-detail-trend">
        <h5><TrendingUp size={15} /> {copy.trend}</h5>
        {detail.timeseries.length === 0 ? (
          <p className="product-detail-note">{copy.noTrend}</p>
        ) : (
          <div className="product-timeseries">
            {detail.timeseries.map((point) => (
              <div className="product-timeseries-point" key={point.date}>
                <div className="product-timeseries-bars">
                  <span style={{ height: `${Math.max(4, (point.delivered_revenue / maxRevenue) * 100)}%` }} />
                </div>
                <strong>{formatCurrency(point.delivered_revenue)}</strong>
                <small>{point.date.slice(5)} · {point.units_delivered} {copy.units.toLowerCase()}</small>
              </div>
            ))}
          </div>
        )}
      </article>

      <article className="product-detail-section">
        <h5><Boxes size={15} /> {copy.variants}</h5>
        {detail.variants.length === 0 ? (
          <p className="product-detail-note">{copy.noVariants}</p>
        ) : (
          <div className="product-variant-table-wrap">
            <table className="product-variant-table">
              <thead>
                <tr>
                  <th>{copy.variant}</th>
                  <th>{copy.currentInventory}</th>
                  <th>{copy.orders}</th>
                  <th>{copy.units}</th>
                  <th>{copy.revenue}</th>
                  <th>{copy.profit}</th>
                </tr>
              </thead>
              <tbody>
                {detail.variants.map((variant) => (
                  <tr key={variant.variant_id ?? `sku-${variant.sku || "none"}`}>
                    <td><strong>{variant.title}</strong><small>{variant.sku || "—"}</small></td>
                    <td>{variant.inventory_quantity}</td>
                    <td>{variant.total_orders}</td>
                    <td>{variant.units_delivered}</td>
                    <td>{formatCurrency(variant.delivered_revenue)}</td>
                    <td>{formatCurrency(variant.gross_profit)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </article>
    </div>
  );
}

function Metric({
  label,
  value,
  tone,
  compact = false,
}: {
  label: string;
  value: string;
  tone?: "positive" | "negative";
  compact?: boolean;
}) {
  return (
    <div className={`product-metric ${compact ? "is-compact" : ""}`}>
      <span>{label}</span>
      <strong className={tone ? `is-${tone}` : ""}>{value}</strong>
    </div>
  );
}
