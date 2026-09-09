import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Bot,
  Building2,
  DollarSign,
  MessageSquareText,
  ShoppingBag,
  Store,
  Users,
  Workflow,
  LoaderCircle,
} from "lucide-react";
import {
  getAdminAttention,
  getAdminOverview,
  type AdminAttentionItem,
  type AdminOverview,
} from "../services/adminAnalytics";

export default function AdminAnalytics() {
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [attention, setAttention] = useState<AdminAttentionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    Promise.all([getAdminOverview(), getAdminAttention()])
      .then(([overviewData, attentionData]) => {
        if (cancelled) return;
        setOverview(overviewData);
        setAttention(attentionData);
      })
      .catch((err: any) => {
        if (cancelled) return;
        setError(err?.response?.data?.detail || "No fue posible cargar las analíticas del administrador.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <div className="commerce-loading">
        <LoaderCircle className="spin" size={24} /> Cargando analíticas de Diaglob...
      </div>
    );
  }

  if (error || !overview) {
    return <div className="commerce-empty">{error || "Sin datos disponibles."}</div>;
  }

  const formatMoney = (value: string, currency: string) => {
    const amount = Number(value);
    try {
      return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency,
        maximumFractionDigits: 0,
      }).format(amount);
    } catch {
      return `${amount} ${currency}`;
    }
  };

  const planRows = Object.entries(overview.organizations.by_plan)
    .sort(([, a], [, b]) => b - a);

  return (
    <div className="dropshipping-overview">
      <section className="page-heading">
        <div>
          <span className="eyebrow">PLATFORM ADMIN</span>
          <h2>Analíticas globales de Diaglob</h2>
          <p>Visión interna del crecimiento, uso e integraciones de toda la plataforma.</p>
        </div>
      </section>

      <div className="analytics-stats-grid">
        <div className="analytics-stat-card">
          <div className="analytics-stat-icon"><DollarSign size={18} /></div>
          <div className="analytics-stat-value">
            {formatMoney(overview.revenue.mrr, overview.revenue.currency)}
          </div>
          <div className="analytics-stat-label">MRR estimado</div>
        </div>

        <div className="analytics-stat-card">
          <div className="analytics-stat-icon"><Building2 size={18} /></div>
          <div className="analytics-stat-value">{overview.organizations.total}</div>
          <div className="analytics-stat-label">Organizaciones</div>
        </div>

        <div className="analytics-stat-card">
          <div className="analytics-stat-icon"><Users size={18} /></div>
          <div className="analytics-stat-value">{overview.users.total}</div>
          <div className="analytics-stat-label">Usuarios</div>
        </div>

        <div className="analytics-stat-card">
          <div className="analytics-stat-icon"><Store size={18} /></div>
          <div className="analytics-stat-value">{overview.stores.active}</div>
          <div className="analytics-stat-label">Tiendas activas</div>
        </div>
      </div>

      <div className="analytics-row">
        <div className="analytics-card">
          <h3>Actividad de plataforma</h3>
          <div className="analytics-metrics-list">
            <div className="analytics-metric-row">
              <span><MessageSquareText size={15} /> Conversaciones</span>
              <span className="analytics-metric-value">{overview.conversations.total}</span>
            </div>
            <div className="analytics-metric-row">
              <span><Bot size={15} /> Respuestas IA</span>
              <span className="analytics-metric-value">{overview.conversations.ai_messages}</span>
            </div>
            <div className="analytics-metric-row">
              <span><ShoppingBag size={15} /> Pedidos</span>
              <span className="analytics-metric-value">{overview.orders.total}</span>
            </div>
            <div className="analytics-metric-row">
              <span><Workflow size={15} /> Automatizaciones</span>
              <span className="analytics-metric-value">{overview.automations.total}</span>
            </div>
          </div>
        </div>

        <div className="analytics-card">
          <h3>Ingresos y planes</h3>
          <div className="analytics-metrics-list">
            <div className="analytics-metric-row">
              <span>ARR estimado</span>
              <span className="analytics-metric-value">
                {formatMoney(overview.revenue.arr, overview.revenue.currency)}
              </span>
            </div>
            {planRows.map(([plan, count]) => (
              <div className="analytics-metric-row" key={plan}>
                <span>{plan}</span>
                <span className="analytics-metric-value">{count}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="analytics-row">
        <div className="analytics-card">
          <h3>Integraciones activas</h3>
          <div className="analytics-metrics-list">
            <div className="analytics-metric-row">
              <span>Shopify</span>
              <span className="analytics-metric-value">{overview.integrations.shopify_connected}</span>
            </div>
            <div className="analytics-metric-row">
              <span>WhatsApp</span>
              <span className="analytics-metric-value">{overview.integrations.whatsapp_connected}</span>
            </div>
            <div className="analytics-metric-row">
              <span>Meta Ads</span>
              <span className="analytics-metric-value">{overview.integrations.meta_ads_connected}</span>
            </div>
            <div className="analytics-metric-row">
              <span>Knowledge Bases</span>
              <span className="analytics-metric-value">{overview.integrations.knowledge_bases}</span>
            </div>
          </div>
        </div>

        <div className="analytics-card">
          <h3><AlertTriangle size={17} /> Requieren atención</h3>
          {attention.length === 0 ? (
            <div className="commerce-empty">No hay organizaciones con alertas de consumo de IA.</div>
          ) : (
            <div className="analytics-metrics-list">
              {attention.slice(0, 10).map((item) => (
                <div className="analytics-metric-row" key={item.organization_id}>
                  <span>
                    <strong>{item.organization_name}</strong>
                    <small style={{ display: "block", opacity: 0.7 }}>
                      {item.plan} · {item.issue}
                    </small>
                  </span>
                  <span className="analytics-metric-value">{item.severity}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
