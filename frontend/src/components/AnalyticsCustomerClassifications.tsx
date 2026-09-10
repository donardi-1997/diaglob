import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { BarChart3, RotateCcw, ShoppingBag, Users } from "lucide-react";

import {
  getCustomerClassificationAnalytics,
  type CustomerClassificationAnalytics,
} from "../services/customerClassifications";
import {
  classificationLabel,
  classificationLocale,
  valueTierLabel,
} from "../utils/customerClassification";
import "../customer-classification-analytics.css";

interface Props {
  storeId: number;
  dateFrom?: string;
  dateTo?: string;
}

const COPY = {
  es: {
    customers: "Clientes",
    buyers: "Con compra entregada",
    repeatRate: "Tasa de recompra",
    revenue: "Ingresos entregados",
    distribution: "Distribución por clasificación",
    distributionHelp: "La clasificación es actual; pedidos e ingresos respetan el período seleccionado.",
    customer: "Cliente",
    share: "Clientes",
    orders: "Pedidos entregados",
    revenueShare: "Participación ingresos",
    aov: "Ticket promedio",
    top: "Clientes destacados del período",
    classification: "Clasificación",
    valueTier: "Nivel de valor",
    rfm: "RFM",
    lifetime: "Valor histórico entregado",
    periodRevenue: "Ingresos del período",
    loading: "Calculando inteligencia de clientes...",
    error: "No pudimos cargar las clasificaciones de clientes.",
    empty: "Todavía no hay clientes clasificados en esta tienda.",
  },
  en: {
    customers: "Customers",
    buyers: "With delivered purchase",
    repeatRate: "Repeat purchase rate",
    revenue: "Delivered revenue",
    distribution: "Classification distribution",
    distributionHelp: "Classification is current; orders and revenue respect the selected period.",
    customer: "Customer",
    share: "Customers",
    orders: "Delivered orders",
    revenueShare: "Revenue share",
    aov: "Average order value",
    top: "Top customers in period",
    classification: "Classification",
    valueTier: "Value tier",
    rfm: "RFM",
    lifetime: "Lifetime delivered value",
    periodRevenue: "Period revenue",
    loading: "Calculating customer intelligence...",
    error: "We could not load customer classifications.",
    empty: "There are no classified customers in this store yet.",
  },
  "pt-BR": {
    customers: "Clientes",
    buyers: "Com compra entregue",
    repeatRate: "Taxa de recompra",
    revenue: "Receita entregue",
    distribution: "Distribuição por classificação",
    distributionHelp: "A classificação é atual; pedidos e receita respeitam o período selecionado.",
    customer: "Cliente",
    share: "Clientes",
    orders: "Pedidos entregues",
    revenueShare: "Participação na receita",
    aov: "Ticket médio",
    top: "Clientes em destaque no período",
    classification: "Classificação",
    valueTier: "Nível de valor",
    rfm: "RFM",
    lifetime: "Valor histórico entregue",
    periodRevenue: "Receita do período",
    loading: "Calculando inteligência de clientes...",
    error: "Não foi possível carregar as classificações de clientes.",
    empty: "Ainda não há clientes classificados nesta loja.",
  },
};

export default function AnalyticsCustomerClassifications({ storeId, dateFrom, dateTo }: Props) {
  const { i18n } = useTranslation();
  const locale = classificationLocale(i18n.resolvedLanguage || i18n.language || "es");
  const copy = COPY[locale];
  const [data, setData] = useState<CustomerClassificationAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!storeId) {
      setData(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setFailed(false);
    getCustomerClassificationAnalytics(storeId, dateFrom, dateTo)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [storeId, dateFrom, dateTo]);

  const money = useMemo(
    () => new Intl.NumberFormat(locale, {
      style: "currency",
      currency: data?.currency || "COP",
      maximumFractionDigits: 0,
    }),
    [data?.currency, locale],
  );

  if (failed) return <div className="cca-state is-error">{copy.error}</div>;
  if (loading && !data) return <div className="cca-state">{copy.loading}</div>;
  if (!data || data.total_customers === 0) return <div className="cca-state">{copy.empty}</div>;

  const visibleDistribution = data.classification_distribution.filter((item) => item.customers > 0);

  return (
    <div className={`customer-classification-analytics ${loading ? "is-loading" : ""}`}>
      <section className="cca-kpis">
        <article><Users size={19} /><div><strong>{data.total_customers}</strong><span>{copy.customers}</span></div></article>
        <article><ShoppingBag size={19} /><div><strong>{data.customers_with_delivered_orders}</strong><span>{copy.buyers}</span></div></article>
        <article><RotateCcw size={19} /><div><strong>{data.repeat_customer_rate ?? 0}%</strong><span>{copy.repeatRate}</span></div></article>
        <article><BarChart3 size={19} /><div><strong>{money.format(data.period_delivered_revenue)}</strong><span>{copy.revenue}</span></div></article>
      </section>

      <section className="cca-panel">
        <header><div><h3>{copy.distribution}</h3><p>{copy.distributionHelp}</p></div></header>
        <div className="cca-distribution">
          {visibleDistribution.map((item) => (
            <article key={item.classification}>
              <div className="cca-distribution-top">
                <span className={`cvc-classification is-${item.classification}`}>{classificationLabel(item.classification, locale)}</span>
                <strong>{item.customers}</strong>
              </div>
              <div className="cca-bar"><span style={{ width: `${Math.max(item.customer_share_pct, 2)}%` }} /></div>
              <div className="cca-distribution-meta">
                <span>{item.customer_share_pct}% {copy.share.toLowerCase()}</span>
                <span>{money.format(item.period_delivered_revenue)} · {item.revenue_share_pct}% {copy.revenueShare.toLowerCase()}</span>
              </div>
              <div className="cca-distribution-stats"><span>{copy.orders}<strong>{item.period_delivered_orders}</strong></span><span>{copy.aov}<strong>{item.avg_order_value === null ? "—" : money.format(item.avg_order_value)}</strong></span></div>
            </article>
          ))}
        </div>
      </section>

      <section className="cca-panel">
        <header><div><h3>{copy.top}</h3><p>{copy.distributionHelp}</p></div></header>
        <div className="cca-table-wrap">
          <table className="cca-table">
            <thead><tr><th>{copy.customer}</th><th>{copy.classification}</th><th>{copy.valueTier}</th><th>{copy.rfm}</th><th>{copy.lifetime}</th><th>{copy.orders}</th><th>{copy.periodRevenue}</th></tr></thead>
            <tbody>
              {data.top_customers.map((item) => (
                <tr key={item.customer_id}>
                  <td><strong>{item.name}</strong><small>{item.email || item.phone}</small></td>
                  <td><span className={`cvc-classification is-${item.commercial_classification}`}>{classificationLabel(item.commercial_classification, locale)}</span></td>
                  <td>{valueTierLabel(item.value_tier, locale)}</td>
                  <td><strong>{item.rfm_score}/15</strong><small>R {item.rfm_recency_score} · F {item.rfm_frequency_score} · M {item.rfm_monetary_score}</small></td>
                  <td>{money.format(item.rfm_monetary_value)}</td>
                  <td>{item.period_delivered_orders}</td>
                  <td><strong>{money.format(item.period_delivered_revenue)}</strong></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
