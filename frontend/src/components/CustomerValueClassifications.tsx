import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  BarChart3,
  RotateCcw,
  Search,
  ShoppingBag,
  Sparkles,
  Users,
} from "lucide-react";

import {
  getCustomerClassifications,
  type CustomerClassificationPage,
} from "../services/customerClassifications";
import {
  CLASSIFICATION_KEYS,
  VALUE_TIER_KEYS,
  classificationLabel,
  classificationLocale,
  valueTierLabel,
} from "../utils/customerClassification";
import "../customer-value-classifications.css";

interface Props {
  storeId: number;
}

const COPY = {
  es: {
    eyebrow: "CLASIFICACIÓN COMERCIAL",
    title: "Clasificaciones por valor",
    subtitle: "Entiende quién genera valor, quién repite y quién necesita reactivación con RFM basado únicamente en pedidos entregados.",
    customers: "Clientes clasificados",
    buyers: "Compradores",
    repeatRate: "Tasa de recompra",
    deliveredValue: "Valor entregado",
    search: "Buscar cliente",
    allClasses: "Todas las clasificaciones",
    allValues: "Todos los niveles de valor",
    value: "Valor",
    frequency: "Frecuencia",
    recency: "Recencia",
    score: "RFM",
    classification: "Clasificación",
    customer: "Cliente",
    days: "días",
    never: "Sin compra",
    loading: "Calculando clasificaciones...",
    empty: "No hay clientes que coincidan con estos filtros.",
    error: "No pudimos calcular las clasificaciones de clientes.",
    previous: "Anterior",
    next: "Siguiente",
    reset: "Limpiar filtros",
    basis: "La clasificación es actual y usa recencia, frecuencia y valor de pedidos entregados. No cuenta pedidos cancelados, devueltos o aún en tránsito.",
  },
  en: {
    eyebrow: "COMMERCIAL CLASSIFICATION",
    title: "Value classifications",
    subtitle: "Understand who creates value, who repeats and who needs reactivation with RFM based only on delivered orders.",
    customers: "Classified customers",
    buyers: "Buyers",
    repeatRate: "Repeat rate",
    deliveredValue: "Delivered value",
    search: "Search customer",
    allClasses: "All classifications",
    allValues: "All value tiers",
    value: "Value",
    frequency: "Frequency",
    recency: "Recency",
    score: "RFM",
    classification: "Classification",
    customer: "Customer",
    days: "days",
    never: "No purchase",
    loading: "Calculating classifications...",
    empty: "No customers match these filters.",
    error: "We could not calculate customer classifications.",
    previous: "Previous",
    next: "Next",
    reset: "Clear filters",
    basis: "Classification is current and uses recency, frequency and value from delivered orders. Cancelled, returned or in-transit orders do not count.",
  },
  "pt-BR": {
    eyebrow: "CLASSIFICAÇÃO COMERCIAL",
    title: "Classificações por valor",
    subtitle: "Entenda quem gera valor, quem recompra e quem precisa de reativação com RFM baseado apenas em pedidos entregues.",
    customers: "Clientes classificados",
    buyers: "Compradores",
    repeatRate: "Taxa de recompra",
    deliveredValue: "Valor entregue",
    search: "Buscar cliente",
    allClasses: "Todas as classificações",
    allValues: "Todos os níveis de valor",
    value: "Valor",
    frequency: "Frequência",
    recency: "Recência",
    score: "RFM",
    classification: "Classificação",
    customer: "Cliente",
    days: "dias",
    never: "Sem compra",
    loading: "Calculando classificações...",
    empty: "Nenhum cliente corresponde a estes filtros.",
    error: "Não foi possível calcular as classificações de clientes.",
    previous: "Anterior",
    next: "Próxima",
    reset: "Limpar filtros",
    basis: "A classificação é atual e usa recência, frequência e valor de pedidos entregues. Pedidos cancelados, devolvidos ou em trânsito não contam.",
  },
};

export default function CustomerValueClassifications({ storeId }: Props) {
  const { i18n } = useTranslation();
  const locale = classificationLocale(i18n.resolvedLanguage || i18n.language || "es");
  const copy = COPY[locale];
  const [data, setData] = useState<CustomerClassificationPage | null>(null);
  const [classification, setClassification] = useState("");
  const [valueTier, setValueTier] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setPage(1);
  }, [storeId, classification, valueTier, search]);

  useEffect(() => {
    if (!storeId) {
      setData(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        setLoading(true);
        setFailed(false);
        const result = await getCustomerClassifications(storeId, {
          classification,
          valueTier,
          search,
          page,
          pageSize: 25,
          sort: "value_desc",
        });
        if (!cancelled) setData(result);
      } catch {
        if (!cancelled) setFailed(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, search ? 250 : 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [storeId, classification, valueTier, search, page]);

  const currency = data?.items[0]?.currency || "COP";
  const money = useMemo(
    () => new Intl.NumberFormat(locale, {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    }),
    [currency, locale],
  );

  const reset = () => {
    setClassification("");
    setValueTier("");
    setSearch("");
    setPage(1);
  };

  return (
    <section className="customer-value-classifications">
      <header className="cvc-hero">
        <div>
          <span className="cvc-eyebrow"><Sparkles size={14} />{copy.eyebrow}</span>
          <h2>{copy.title}</h2>
          <p>{copy.subtitle}</p>
        </div>
        <div className="cvc-basis"><BarChart3 size={16} /><span>{copy.basis}</span></div>
      </header>

      {data && (
        <div className="cvc-kpis">
          <article><Users size={18} /><div><strong>{data.summary.total_customers}</strong><span>{copy.customers}</span></div></article>
          <article><ShoppingBag size={18} /><div><strong>{data.summary.buyers}</strong><span>{copy.buyers}</span></div></article>
          <article><RotateCcw size={18} /><div><strong>{data.summary.repeat_buyer_rate ?? 0}%</strong><span>{copy.repeatRate}</span></div></article>
          <article><BarChart3 size={18} /><div><strong>{money.format(data.summary.lifetime_delivered_revenue)}</strong><span>{copy.deliveredValue}</span></div></article>
        </div>
      )}

      <div className="cvc-filters">
        <label className="cvc-search"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={copy.search} /></label>
        <select value={classification} onChange={(event) => setClassification(event.target.value)}>
          <option value="">{copy.allClasses}</option>
          {CLASSIFICATION_KEYS.map((key) => <option key={key} value={key}>{classificationLabel(key, locale)}</option>)}
        </select>
        <select value={valueTier} onChange={(event) => setValueTier(event.target.value)}>
          <option value="">{copy.allValues}</option>
          {VALUE_TIER_KEYS.map((key) => <option key={key} value={key}>{valueTierLabel(key, locale)}</option>)}
        </select>
        {(classification || valueTier || search) && <button type="button" className="cvc-reset" onClick={reset}>{copy.reset}</button>}
      </div>

      {failed ? (
        <div className="cvc-state is-error">{copy.error}</div>
      ) : loading && !data ? (
        <div className="cvc-state">{copy.loading}</div>
      ) : data ? (
        <>
          <div className={`cvc-table-wrap ${loading ? "is-loading" : ""}`}>
            <table className="cvc-table">
              <thead><tr><th>{copy.customer}</th><th>{copy.classification}</th><th>{copy.value}</th><th>{copy.recency}</th><th>{copy.frequency}</th><th>{copy.score}</th></tr></thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.customer_id}>
                    <td><strong>{item.name}</strong><small>{item.email || item.phone}</small></td>
                    <td><span className={`cvc-classification is-${item.commercial_classification}`}>{classificationLabel(item.commercial_classification, locale)}</span><small>{valueTierLabel(item.value_tier, locale)}</small></td>
                    <td><strong>{money.format(item.rfm_monetary_value)}</strong><small>{item.rfm_monetary_score}/5</small></td>
                    <td><strong>{item.rfm_recency_days === null ? copy.never : `${item.rfm_recency_days} ${copy.days}`}</strong><small>{item.rfm_recency_score}/5</small></td>
                    <td><strong>{item.rfm_frequency}</strong><small>{item.rfm_frequency_score}/5</small></td>
                    <td><span className="cvc-rfm-score">{item.rfm_score}/15</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!data.items.length && <div className="cvc-state">{copy.empty}</div>}
          </div>
          <footer className="cvc-pagination">
            <span>{data.total} · {data.page}/{data.total_pages}</span>
            <div><button type="button" disabled={data.page <= 1 || loading} onClick={() => setPage((current) => current - 1)}>{copy.previous}</button><button type="button" disabled={data.page >= data.total_pages || loading} onClick={() => setPage((current) => current + 1)}>{copy.next}</button></div>
          </footer>
        </>
      ) : null}
    </section>
  );
}
