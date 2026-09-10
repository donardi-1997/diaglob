import { useTranslation } from "react-i18next";
import { useState, useEffect } from "react";
import {
  MessageSquareText,
  ShoppingBag,
  Workflow,
  BarChart3,
  AlertTriangle,
  Settings,
  BrainCircuit,
  CreditCard,
  Megaphone,
  Package,
  Plug,
} from "lucide-react";
import {
  getOperationsSummary,
  type OperationsIntegration,
  type OperationsSummary,
} from "../services/operations";
import { type Store } from "../services/stores";
import {
  degradedAlertMessage,
  degradedStatusLabel,
} from "../utils/operationsStatus";
import GettingStarted from "../components/GettingStarted";

interface DashboardPageProps {
  stores: Store[];
  storeId: number | null;
  onNavigateToStores?: () => void;
  onNavigateToCommerce?: () => void;
  onNavigateToWhatsApp?: () => void;
  onNavigateToKnowledge?: () => void;
  onNavigateToAutomations?: () => void;
}

function IntegrationIcon({
  category,
}: {
  category: OperationsIntegration["category"];
}) {
  if (category === "messaging") return <MessageSquareText size={18} />;
  if (category === "commerce") return <ShoppingBag size={18} />;
  if (category === "supplier") return <Package size={18} />;
  if (category === "knowledge") return <BrainCircuit size={18} />;
  if (category === "ads") return <Megaphone size={18} />;
  if (category === "payments") return <CreditCard size={18} />;
  return <Plug size={18} />;
}

export default function DashboardPage({
  stores,
  storeId,
  onNavigateToStores,
  onNavigateToCommerce,
  onNavigateToWhatsApp,
  onNavigateToKnowledge,
  onNavigateToAutomations,
}: DashboardPageProps) {
  const { t, i18n } = useTranslation();
  const [data, setData] = useState<OperationsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!storeId) {
      setLoading(false);
      return;
    }

    let mounted = true;

    async function load() {
      try {
        const summary = await getOperationsSummary(storeId!);
        if (mounted) {
          setData(summary);
          setError("");
        }
      } catch (err: any) {
        if (mounted) {
          setError(
            err?.response?.data?.detail ||
              err?.message ||
              "Unable to load operations data"
          );
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }

    load();

    return () => {
      mounted = false;
    };
  }, [storeId]);

  if (!storeId) {
    return (
      <div className="content">
        <section className="page-heading">
          <div>
            <span className="eyebrow">DIAGLOB</span>
            <h1>{t("overview")}</h1>
          </div>
        </section>
        <div className="empty-state">
          <Settings size={48} />
          <h3>{t("emptyNoStoreTitle") || "Crea tu primera tienda"}</h3>
          <p>{t("emptyNoStoreHelp") || "Una tienda te permite gestionar productos, pedidos y conversaciones."}</p>
          {onNavigateToStores && (
            <button className="primary-button" onClick={onNavigateToStores}>
              {t("emptyNoStoreAction") || "Crear tienda"}
            </button>
          )}
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="content">
        <section className="page-heading">
          <div>
            <span className="eyebrow">DIAGLOB</span>
            <h1>{t("overview")}</h1>
          </div>
        </section>
        <div className="loading-state">
          <p>{t("dashboardLoading") || "Cargando resumen..."}</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="content">
        <section className="page-heading">
          <div>
            <span className="eyebrow">DIAGLOB</span>
            <h1>{t("overview")}</h1>
          </div>
        </section>
        <div className="error-state">
          <AlertTriangle size={32} />
          <h3>{t("dashboardError") || "No pudimos cargar el resumen."}</h3>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  const conv = data?.conversations;
  const orders = data?.orders;
  const autos = data?.automations;
  const integrations = data?.integrations || [];
  const products = data?.products;
  const alerts = data?.alerts || [];
  const activity = data?.activity || [];
  const language = i18n.resolvedLanguage || i18n.language;
  const degradedLabel = degradedStatusLabel(language);

  const formatTimeAgo = (timestamp: string) => {
    const now = Date.now();
    const then = new Date(timestamp).getTime();
    const diffMs = now - then;
    const diffMin = Math.floor(diffMs / 60000);
    const diffHr = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHr / 24);

    if (diffMin < 1) return "now";
    if (diffMin < 60) return `${diffMin}m`;
    if (diffHr < 24) return `${diffHr}h`;
    return `${diffDay}d`;
  };

  return (
    <div className="content">
      <section className="page-heading">
        <div>
          <span className="eyebrow">DIAGLOB</span>
          <h1>{t("overview")}</h1>
          <p>{t("brandTagline")}</p>
        </div>
      </section>

      <GettingStarted
        stores={stores}
        selectedStoreId={storeId}
        onNavigateToStores={onNavigateToStores || (() => {})}
        onNavigateToCommerce={onNavigateToCommerce || (() => {})}
        onNavigateToWhatsApp={onNavigateToWhatsApp || (() => {})}
        onNavigateToKnowledge={onNavigateToKnowledge || (() => {})}
        onNavigateToAutomations={onNavigateToAutomations || (() => {})}
      />

      <section className="stats-grid">
        <div className="stat-card">
          <div className="stat-icon">
            <MessageSquareText size={20} />
          </div>
          <div className="stat-value">{conv?.total || 0}</div>
          <div className="stat-label">{t("conversations")}</div>
        </div>

        <div className="stat-card">
          <div className="stat-icon">
            <ShoppingBag size={20} />
          </div>
          <div className="stat-value">{orders?.total || 0}</div>
          <div className="stat-label">{t("commerce")}</div>
        </div>

        <div className="stat-card">
          <div className="stat-icon">
            <Workflow size={20} />
          </div>
          <div className="stat-value">{autos?.total || 0}</div>
          <div className="stat-label">{t("automations")}</div>
        </div>

        <div className="stat-card">
          <div className="stat-icon">
            <BarChart3 size={20} />
          </div>
          <div className="stat-value">{products?.total || 0}</div>
          <div className="stat-label">{t("products") || "Productos"}</div>
        </div>
      </section>

      {alerts.length > 0 && (
        <section className="dashboard-alerts">
          {alerts.map((alert, i) => (
            <div key={i} className="dashboard-alert-item">
              <AlertTriangle size={16} />
              <span>
                {alert.type === "integration_status_degraded"
                  ? degradedAlertMessage(language, integrations)
                  : alert.message}
              </span>
            </div>
          ))}
        </section>
      )}

      <div className="dashboard-grid">
        <div className="panel">
          <div className="panel-header">
            <h2>{t("activity")}</h2>
          </div>

          <div className="activity-list">
            {activity.length === 0 && (
              <div className="empty-activity">
                {t("dashboardNoActivity") || "Sin actividad reciente."}
              </div>
            )}
            {activity.slice(0, 5).map((a, i) => (
              <div key={i} className="activity-item">
                <div className="activity-icon">
                  <MessageSquareText size={16} />
                </div>
                <div className="activity-copy">
                  <strong>{a.title}</strong>
                  <span>{a.detail}</span>
                </div>
                <span className="activity-time">
                  {a.timestamp ? formatTimeAgo(a.timestamp) : ""}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="right-column">
          <div className="panel">
            <div className="panel-header">
              <h2>{t("integrations") || "Integraciones"}</h2>
            </div>

            <div className="agent-list">
              {integrations.length === 0 && (
                <div className="empty-activity">
                  {t("notConnected") || "No conectado"}
                </div>
              )}

              {integrations.map((integration) => (
                <div className="agent-item" key={integration.key}>
                  <div className="agent-icon">
                    <IntegrationIcon category={integration.category} />
                  </div>
                  <div className="agent-copy">
                    <strong>{integration.name}</strong>
                    <span>
                      <span
                        className={`mini-status ${
                          integration.connected ? "connected" : ""
                        }`}
                      />
                      {integration.connected
                        ? t("connected") || "Conectado"
                        : integration.degraded || integration.status === "degraded"
                          ? degradedLabel
                          : integration.status === "disconnected"
                            ? t("notConnected") || "No conectado"
                            : integration.status}
                      {integration.payment_methods?.length
                        ? ` · ${integration.payment_methods
                            .map((method) => method.toUpperCase())
                            .join(", ")}`
                        : ""}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
