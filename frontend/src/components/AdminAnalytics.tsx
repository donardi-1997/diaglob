import { useEffect, useMemo, useState } from "react";
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
  TrendingUp,
  RefreshCw,
} from "lucide-react";
import {
  getAdminAttention,
  getAdminOverview,
  type AdminAttentionItem,
  type AdminOverview,
  type AdminRankingItem,
} from "../services/adminAnalytics";

function RankingList({
  title,
  items,
  metric,
}: {
  title: string;
  items: AdminRankingItem[];
  metric: "ai_responses" | "orders" | "conversations";
}) {
  return (
    <div className="analytics-card">
      <h3>{title}</h3>
      {items.length === 0 ? (
        <div className="commerce-empty">Sin actividad en los últimos 30 días.</div>
      ) : (
        <div className="analytics-metrics-list">
          {items.slice(0, 10).map((item, index) => (
            <div className="analytics-metric-row" key={item.organization_id}>
              <span>
                <strong>#{index + 1} {item.organization_name}</strong>
                <small style={{ display: "block", opacity: 0.7 }}>
                  Plan {item.plan}
                </small>
              </span>
              <span className="analytics-metric-value">{item[metric] ?? 0}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

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

  const recentDaily = useMemo(
    () => overview?.growth.daily.slice(-14) ?? [],
    [overview],
  );

  const maxAiResponses = useMemo(
    () => Math.max(1, ...recentDaily.map((point) => point.ai_responses)),
    [recentDaily],
  );

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

  const billingStatuses = Object.entries(overview.growth.billing_health.subscription_statuses)
    .sort(([, a], [, b]) => b - a);

  return (
    <div className="dropshipping-overview">
      <section className="page-heading">
        <div>
          <span className="eyebrow">PLATFORM ADMIN</span>
          <h2>Analíticas globales de Diaglob</h2>
          <p>Visión interna de crecimiento, uso, ingresos e integraciones de toda la plataforma.</p>
        </div>
      </section>

      <div className="analytics-stats-grid">
        <div className="analytics-stat-card">
          <div className="analytics-stat-icon"><DollarSign size={18} /></div>
          <div className="analytics-stat-value">
            {formatMoney(overview.revenue.mrr, overview.revenue.currency)}
          </div>
          <div className="analytics-stat-label">MRR actual estimado</div>
        </div>

        <div className="analytics-stat-card">
          <div className="analytics-stat-icon"><Building2 size={18} /></div>
          <div className="analytics-stat-value">{overview.growth.totals.new_organizations}</div>
          <div className="analytics-stat-label">Nuevas organizaciones · 30d</div>
        </div>

        <div className="analytics-stat-card">
          <div className="analytics-stat-icon"><Users size={18} /></div>
          <div className="analytics-stat-value">{overview.growth.totals.new_users}</div>
          <div className="analytics-stat-label">Nuevos usuarios · 30d</div>
        </div>

        <div className="analytics-stat-card">
          <div className="analytics-stat-icon"><Bot size={18} /></div>
          <div className="analytics-stat-value">{overview.growth.totals.ai_responses}</div>
          <div className="analytics-stat-label">Respuestas IA · 30d</div>
        </div>
      </div>

      <div className="analytics-row">
        <div className="analytics-card">
          <h3><TrendingUp size={17} /> Crecimiento reciente</h3>
          <div className="analytics-metrics-list">
            <div className="analytics-metric-row">
              <span>Organizaciones totales</span>
              <span className="analytics-metric-value">{overview.organizations.total}</span>
            </div>
            <div className="analytics-metric-row">
              <span>Usuarios totales</span>
              <span className="analytics-metric-value">{overview.users.total}</span>
            </div>
            <div className="analytics-metric-row">
              <span>Pedidos últimos 30 días</span>
              <span className="analytics-metric-value">{overview.growth.totals.orders}</span>
            </div>
            <div className="analytics-metric-row">
              <span>Tiendas activas</span>
              <span className="analytics-metric-value">{overview.stores.active}</span>
            </div>
          </div>
        </div>

        <div className="analytics-card">
          <h3>Ingresos y planes</h3>
          <div className="analytics-metrics-list">
            <div className="analytics-metric-row">
              <span>ARR actual estimado</span>
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

      <div className="analytics-card">
        <h3>Actividad diaria · últimos 14 días</h3>
        <div className="analytics-metrics-list">
          {recentDaily.map((point) => (
            <div className="analytics-metric-row" key={point.date}>
              <span style={{ minWidth: 110 }}>
                <strong>{point.date}</strong>
                <small style={{ display: "block", opacity: 0.7 }}>
                  +{point.organizations} org · +{point.users} usuarios · {point.orders} pedidos
                </small>
              </span>
              <span style={{ minWidth: 180, flex: 1 }}>
                <span
                  style={{
                    display: "block",
                    width: `${Math.max(4, (point.ai_responses / maxAiResponses) * 100)}%`,
                    height: 8,
                    borderRadius: 999,
                    background: "currentColor",
                    opacity: 0.45,
                  }}
                />
              </span>
              <span className="analytics-metric-value">{point.ai_responses} IA</span>
            </div>
          ))}
        </div>
      </div>

      <div className="analytics-row">
        <div className="analytics-card">
          <h3><RefreshCw size={17} /> Salud de billing</h3>
          <div className="analytics-metrics-list">
            <div className="analytics-metric-row">
              <span>Cambios de plan pendientes</span>
              <span className="analytics-metric-value">
                {overview.growth.billing_health.pending_plan_changes}
              </span>
            </div>
            <div className="analytics-metric-row">
              <span>Renovación automática desactivada</span>
              <span className="analytics-metric-value">
                {overview.growth.billing_health.auto_renew_disabled}
              </span>
            </div>
            {billingStatuses.map(([status, count]) => (
              <div className="analytics-metric-row" key={status}>
                <span>Estado: {status}</span>
                <span className="analytics-metric-value">{count}</span>
              </div>
            ))}
          </div>
          {!overview.growth.billing_health.historical_billing_available && (
            <div className="commerce-empty" style={{ marginTop: 12 }}>
              MRR histórico, churn, upgrades y downgrades todavía no se muestran porque la base actual
              no conserva un ledger histórico de eventos de billing. El MRR mostrado arriba es un snapshot actual.
            </div>
          )}
        </div>

        <div className="analytics-card">
          <h3>Actividad de plataforma</h3>
          <div className="analytics-metrics-list">
            <div className="analytics-metric-row">
              <span><MessageSquareText size={15} /> Conversaciones</span>
              <span className="analytics-metric-value">{overview.conversations.total}</span>
            </div>
            <div className="analytics-metric-row">
              <span><Bot size={15} /> Respuestas IA totales</span>
              <span className="analytics-metric-value">{overview.conversations.ai_messages}</span>
            </div>
            <div className="analytics-metric-row">
              <span><ShoppingBag size={15} /> Pedidos totales</span>
              <span className="analytics-metric-value">{overview.orders.total}</span>
            </div>
            <div className="analytics-metric-row">
              <span><Workflow size={15} /> Automatizaciones</span>
              <span className="analytics-metric-value">{overview.automations.total}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="analytics-row">
        <RankingList
          title="Top organizaciones por uso de IA · 30d"
          items={overview.growth.rankings.top_ai_usage}
          metric="ai_responses"
        />
        <RankingList
          title="Top organizaciones por pedidos · 30d"
          items={overview.growth.rankings.top_orders}
          metric="orders"
        />
      </div>

      <div className="analytics-row">
        <RankingList
          title="Top organizaciones por conversaciones · 30d"
          items={overview.growth.rankings.top_conversations}
          metric="conversations"
        />

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
      </div>

      <div className="analytics-card">
        <h3><AlertTriangle size={17} /> Organizaciones que requieren atención</h3>
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
  );
}
