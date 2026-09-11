import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  BarChart3,
  BrainCircuit,
  CreditCard,
  Megaphone,
  MessageSquareText,
  Package,
  Plug,
  RefreshCw,
  Settings,
  ShoppingBag,
  Workflow,
} from "lucide-react";

import GettingStarted from "../components/GettingStarted";
import {
  getOperationsSummary,
  type OperationsIntegration,
  type OperationsSummary,
} from "../services/operations";
import { type Store } from "../services/stores";
import {
  degradedStatusLabel,
  operationsAlertMessage,
  operationsHealthLabel,
  sortOperationsAlerts,
} from "../utils/operationsStatus";
import "../dashboard-v2.css";
import "../onboarding-activation-polish.css";

interface DashboardPageProps {
  stores: Store[];
  storeId: number | null;
  onNavigateToStores?: () => void;
  onNavigateToCommerce?: () => void;
  onNavigateToWhatsApp?: () => void;
  onNavigateToKnowledge?: () => void;
  onNavigateToAutomations?: () => void;
}

function IntegrationIcon({ category }: { category: string }) {
  if (category === "messaging") return <MessageSquareText size={17} />;
  if (category === "commerce") return <ShoppingBag size={17} />;
  if (category === "supplier") return <Package size={17} />;
  if (category === "knowledge") return <BrainCircuit size={17} />;
  if (category === "ads") return <Megaphone size={17} />;
  if (category === "payments") return <CreditCard size={17} />;
  return <Plug size={17} />;
}

function DashboardSkeleton() {
  return (
    <div className="dg-dashboard">
      <div className="dg-dashboard-hero">
        <div>
          <span className="dg-dashboard-kicker">DIAGLOB</span>
          <h1>Centro de operaciones</h1>
          <p>Cargando el estado de tu negocio...</p>
        </div>
      </div>
      <div className="dg-dashboard-loading-grid">
        {Array.from({ length: 4 }).map((_, index) => (
          <div className="dg-dashboard-skeleton" key={index} />
        ))}
      </div>
    </div>
  );
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
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const requestIdRef = useRef(0);

  const loadSummary = useCallback(
    async (targetStoreId: number, initial: boolean) => {
      const requestId = ++requestIdRef.current;

      if (initial) {
        setLoading(true);
        setError("");
      } else {
        setRefreshing(true);
      }

      try {
        const summary = await getOperationsSummary(targetStoreId);
        if (requestId !== requestIdRef.current) return;
        setData(summary);
        setError("");
      } catch (err: any) {
        if (requestId !== requestIdRef.current) return;
        if (initial) {
          setError(
            err?.response?.data?.detail ||
              err?.message ||
              "Unable to load operations data",
          );
        }
      } finally {
        if (requestId === requestIdRef.current) {
          if (initial) setLoading(false);
          else setRefreshing(false);
        }
      }
    },
    [],
  );

  useEffect(() => {
    if (!storeId) {
      requestIdRef.current += 1;
      setLoading(false);
      return;
    }

    void loadSummary(storeId, true);
    const intervalId = window.setInterval(() => {
      void loadSummary(storeId, false);
    }, 30_000);

    return () => {
      requestIdRef.current += 1;
      window.clearInterval(intervalId);
    };
  }, [loadSummary, storeId]);

  const language = i18n.resolvedLanguage || i18n.language;
  const locale = language === "pt-BR" ? "pt-BR" : language === "en" ? "en" : "es";
  const selectedStore = stores.find((store) => store.id === storeId);

  const copy = useMemo(() => {
    if (locale === "en") {
      return {
        kicker: "Operations center",
        title: "Your business, under control.",
        subtitle: "Monitor conversations, orders, automations and integrations from one operational view.",
        quickCommerce: "View commerce",
        quickKnowledge: "Knowledge",
        quickAutomations: "Automations",
        refresh: "Refresh",
        activityTitle: "Recent activity",
        activityHelp: "Latest events from the active store",
        integrationsTitle: "Integration health",
        integrationsHelp: "Connection status for your operating stack",
        noActivity: "No recent activity yet.",
        noIntegrations: "No integrations available yet.",
        conversationsMeta: "active in the last 24h",
        ordersMeta: "orders in the last 24h",
        automationMeta: "active automations",
        productMeta: "product variants",
        aiMessageShare: "AI message share",
        orderValue: "order value",
        executions: "executions today",
        connected: "connected",
      };
    }

    if (locale === "pt-BR") {
      return {
        kicker: "Centro de operações",
        title: "Seu negócio, sob controle.",
        subtitle: "Monitore conversas, pedidos, automações e integrações em uma única visão operacional.",
        quickCommerce: "Ver comércio",
        quickKnowledge: "Knowledge",
        quickAutomations: "Automações",
        refresh: "Atualizar",
        activityTitle: "Atividade recente",
        activityHelp: "Últimos eventos da loja ativa",
        integrationsTitle: "Saúde das integrações",
        integrationsHelp: "Estado das conexões do seu stack operacional",
        noActivity: "Ainda não há atividade recente.",
        noIntegrations: "Ainda não há integrações disponíveis.",
        conversationsMeta: "ativas nas últimas 24h",
        ordersMeta: "pedidos nas últimas 24h",
        automationMeta: "automações ativas",
        productMeta: "variantes de produto",
        aiMessageShare: "mensagens enviadas por IA",
        orderValue: "valor em pedidos",
        executions: "execuções hoje",
        connected: "conectadas",
      };
    }

    return {
      kicker: "Centro de operaciones",
      title: "Tu negocio, bajo control.",
      subtitle: "Monitorea conversaciones, pedidos, automatizaciones e integraciones desde una sola vista operativa.",
      quickCommerce: "Ver comercio",
      quickKnowledge: "Knowledge",
      quickAutomations: "Automatizaciones",
      refresh: "Actualizar",
      activityTitle: "Actividad reciente",
      activityHelp: "Últimos eventos de la tienda activa",
      integrationsTitle: "Salud de integraciones",
      integrationsHelp: "Estado de conexión de tu stack operativo",
      noActivity: "Todavía no hay actividad reciente.",
      noIntegrations: "Todavía no hay integraciones disponibles.",
      conversationsMeta: "activas en las últimas 24h",
      ordersMeta: "pedidos en las últimas 24h",
      automationMeta: "automatizaciones activas",
      productMeta: "variantes de producto",
      aiMessageShare: "mensajes enviados por IA",
      orderValue: "valor en pedidos",
      executions: "ejecuciones hoy",
      connected: "conectadas",
    };
  }, [locale]);

  const firstStoreCopy = useMemo(() => {
    if (locale === "en") {
      return {
        title: "Start with your operating base",
        help: "Your first store defines the market, currency, and scope used by integrations and analytics.",
        guideTitle: "What comes next",
        guideHelp: "Diaglob will guide you through the rest of activation after the store exists.",
        steps: [
          ["Create the store", "Choose market, currency, language, and operating context."],
          ["Connect your channels", "Connect commerce and messaging so products, orders, and conversations can flow in."],
          ["Activate intelligence", "Add Knowledge and your first automation so AI and analytics can work with real context."],
        ],
      };
    }
    if (locale === "pt-BR") {
      return {
        title: "Comece pela base da sua operação",
        help: "Sua primeira loja define mercado, moeda e escopo usados pelas integrações e pelo Analytics.",
        guideTitle: "O que vem depois",
        guideHelp: "A Diaglob vai orientar o restante da ativação assim que a loja existir.",
        steps: [
          ["Crie a loja", "Defina mercado, moeda, idioma e contexto operacional."],
          ["Conecte seus canais", "Conecte comércio e mensagens para receber produtos, pedidos e conversas."],
          ["Ative a inteligência", "Adicione Knowledge e sua primeira automação para usar IA e Analytics com contexto real."],
        ],
      };
    }
    return {
      title: "Empieza por la base de tu operación",
      help: "Tu primera tienda define mercado, moneda y alcance para integraciones y analítica.",
      guideTitle: "Qué viene después",
      guideHelp: "Diaglob te irá guiando por el resto de la activación apenas exista la tienda.",
      steps: [
        ["Crea la tienda", "Define mercado, moneda, idioma y contexto operativo."],
        ["Conecta tus canales", "Conecta comercio y mensajería para recibir productos, pedidos y conversaciones."],
        ["Activa la inteligencia", "Agrega Knowledge y tu primera automatización para usar IA y analítica con contexto real."],
      ],
    };
  }, [locale]);

  if (!storeId) {
    return (
      <div className="dg-dashboard">
        <section className="dg-dashboard-hero">
          <div>
            <span className="dg-dashboard-kicker">GETTING STARTED</span>
            <h1>{t("emptyNoStoreTitle") || firstStoreCopy.title}</h1>
            <p>{firstStoreCopy.help}</p>
          </div>
          <div className="dg-dashboard-hero-actions">
            {onNavigateToStores && (
              <button className="dg-dashboard-action is-primary" onClick={onNavigateToStores}>
                <Settings size={16} />
                {t("emptyNoStoreAction") || "Crear tienda"}
              </button>
            )}
          </div>
        </section>

        <section className="dg-dashboard-first-store">
          <div className="dg-dashboard-first-store-header">
            <span>ACTIVATION</span>
            <h2>{firstStoreCopy.guideTitle}</h2>
            <p>{firstStoreCopy.guideHelp}</p>
          </div>
          <div className="dg-dashboard-first-store-grid">
            {firstStoreCopy.steps.map(([title, help], index) => (
              <article className="dg-dashboard-first-store-step" key={title}>
                <span className="dg-dashboard-first-store-step-number">{index + 1}</span>
                <strong>{title}</strong>
                <p>{help}</p>
              </article>
            ))}
          </div>
        </section>
      </div>
    );
  }

  if (loading) return <DashboardSkeleton />;

  if (error) {
    return (
      <div className="dg-dashboard">
        <section className="dg-dashboard-hero">
          <div>
            <span className="dg-dashboard-kicker">DIAGLOB</span>
            <h1>{t("dashboardError") || "No pudimos cargar el resumen."}</h1>
            <p>{error}</p>
          </div>
        </section>
      </div>
    );
  }

  const conv = data?.conversations;
  const orders = data?.orders;
  const autos = data?.automations;
  const integrations = data?.integrations || [];
  const products = data?.products;
  const alerts = sortOperationsAlerts(data?.alerts || []);
  const activity = data?.activity || [];
  const degradedLabel = degradedStatusLabel(language);
  const healthLabel = operationsHealthLabel(
    data?.health?.status || "operational",
    language,
  );
  const connectedCount = integrations.filter((integration) => integration.connected).length;

  const formatTimeAgo = (timestamp: string) => {
    const diffMs = Date.now() - new Date(timestamp).getTime();
    const diffMin = Math.floor(diffMs / 60000);
    const diffHr = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHr / 24);

    if (diffMin < 1) return "now";
    if (diffMin < 60) return `${diffMin}m`;
    if (diffHr < 24) return `${diffHr}h`;
    return `${diffDay}d`;
  };

  const formatMoney = (value: number) => {
    try {
      return new Intl.NumberFormat(locale, {
        style: "currency",
        currency: selectedStore?.currency || "COP",
        maximumFractionDigits: 0,
      }).format(value || 0);
    } catch {
      return String(value || 0);
    }
  };

  const metricCards = [
    {
      icon: MessageSquareText,
      value: conv?.total || 0,
      label: t("conversations") || "Conversaciones",
      trend: `${conv?.active_24h || 0} ${copy.conversationsMeta}`,
      meta: `${Math.round(conv?.ai_message_share_pct || 0)}% ${copy.aiMessageShare}`,
    },
    {
      icon: ShoppingBag,
      value: orders?.total || 0,
      label: t("commerce") || "Pedidos",
      trend: `${orders?.last_24h || 0} ${copy.ordersMeta}`,
      meta: `${formatMoney(orders?.total_value || 0)} ${copy.orderValue}`,
    },
    {
      icon: Workflow,
      value: autos?.total || 0,
      label: t("automations") || "Automatizaciones",
      trend: `${autos?.active || 0} ${copy.automationMeta}`,
      meta: `${autos?.executions_24h || 0} ${copy.executions}`,
    },
    {
      icon: BarChart3,
      value: products?.total || 0,
      label: t("products") || "Productos",
      trend: `${products?.variants || 0} ${copy.productMeta}`,
      meta: `${connectedCount}/${integrations.length} ${copy.connected}`,
    },
  ];

  return (
    <div className="dg-dashboard">
      <section className="dg-dashboard-hero">
        <div>
          <span className="dg-dashboard-kicker">
            <span className="dg-dashboard-kicker-dot" />
            {copy.kicker} · {healthLabel}
          </span>
          <h1>{selectedStore?.name ? `${selectedStore.name}: ${copy.title}` : copy.title}</h1>
          <p>{copy.subtitle}</p>
        </div>

        <div className="dg-dashboard-hero-actions">
          <button
            className="dg-dashboard-action"
            onClick={() => void loadSummary(storeId, false)}
            disabled={refreshing}
          >
            <RefreshCw size={15} />
            {copy.refresh}
          </button>
          {onNavigateToCommerce && (
            <button className="dg-dashboard-action is-primary" onClick={onNavigateToCommerce}>
              <ShoppingBag size={15} />
              {copy.quickCommerce}
              <ArrowUpRight size={14} />
            </button>
          )}
          {onNavigateToKnowledge && (
            <button className="dg-dashboard-action" onClick={onNavigateToKnowledge}>
              <BrainCircuit size={15} />
              {copy.quickKnowledge}
            </button>
          )}
          {onNavigateToAutomations && (
            <button className="dg-dashboard-action" onClick={onNavigateToAutomations}>
              <Workflow size={15} />
              {copy.quickAutomations}
            </button>
          )}
        </div>
      </section>

      <div className="dg-dashboard-getting-started">
        <GettingStarted
          stores={stores}
          selectedStoreId={storeId}
          onNavigateToStores={onNavigateToStores || (() => {})}
          onNavigateToCommerce={onNavigateToCommerce || (() => {})}
          onNavigateToWhatsApp={onNavigateToWhatsApp || (() => {})}
          onNavigateToKnowledge={onNavigateToKnowledge || (() => {})}
          onNavigateToAutomations={onNavigateToAutomations || (() => {})}
        />
      </div>

      <section className="dg-dashboard-metrics">
        {metricCards.map(({ icon: Icon, value, label, trend, meta }) => (
          <article className="dg-metric-card" key={label}>
            <div className="dg-metric-top">
              <div className="dg-metric-icon"><Icon size={19} /></div>
              <span className="dg-metric-trend">{trend}</span>
            </div>
            <div>
              <div className="dg-metric-value">{value.toLocaleString(locale)}</div>
              <div className="dg-metric-label">{label}</div>
              <div className="dg-metric-meta">{meta}</div>
            </div>
          </article>
        ))}
      </section>

      {alerts.length > 0 && (
        <section className="dg-dashboard-alert-stack">
          {alerts.map((alert, index) => (
            <div key={`${alert.type}-${index}`} className="dg-dashboard-alert-v2">
              <AlertTriangle size={16} />
              <span>{operationsAlertMessage(language, alert, integrations)}</span>
            </div>
          ))}
        </section>
      )}

      <section className="dg-dashboard-content-grid">
        <article className="dg-dashboard-panel">
          <header className="dg-dashboard-panel-header">
            <div className="dg-dashboard-panel-title">
              <h2>{copy.activityTitle}</h2>
              <p>{copy.activityHelp}</p>
            </div>
            <span className="dg-dashboard-panel-badge">{activity.length}</span>
          </header>

          {activity.length === 0 ? (
            <div className="dg-dashboard-empty">{copy.noActivity}</div>
          ) : (
            <div className="dg-activity-v2">
              {activity.slice(0, 7).map((item, index) => (
                <div className="dg-activity-row" key={`${item.timestamp || "activity"}-${index}`}>
                  <div className="dg-activity-icon"><Activity size={16} /></div>
                  <div className="dg-activity-copy">
                    <strong>{item.title}</strong>
                    <span>{item.detail}</span>
                  </div>
                  <span className="dg-activity-time">
                    {item.timestamp ? formatTimeAgo(item.timestamp) : ""}
                  </span>
                </div>
              ))}
            </div>
          )}
        </article>

        <article className="dg-dashboard-panel">
          <header className="dg-dashboard-panel-header">
            <div className="dg-dashboard-panel-title">
              <h2>{copy.integrationsTitle}</h2>
              <p>{copy.integrationsHelp}</p>
            </div>
            <span className="dg-dashboard-panel-badge">{connectedCount}/{integrations.length}</span>
          </header>

          {integrations.length === 0 ? (
            <div className="dg-dashboard-empty">{copy.noIntegrations}</div>
          ) : (
            <div className="dg-integration-list">
              {integrations.map((integration: OperationsIntegration) => (
                <div
                  className={`dg-integration-row ${integration.connected ? "is-connected" : ""}`}
                  key={integration.key}
                >
                  <div className="dg-integration-icon">
                    <IntegrationIcon category={integration.category} />
                  </div>
                  <div className="dg-integration-copy">
                    <strong>{integration.name}</strong>
                    <span>
                      {integration.connected
                        ? t("connected") || "Conectado"
                        : integration.degraded || integration.status === "degraded"
                          ? degradedLabel
                          : integration.status === "disconnected"
                            ? t("notConnected") || "No conectado"
                            : integration.status}
                    </span>
                  </div>
                  <span className={`dg-integration-status ${integration.connected ? "is-connected" : ""}`} />
                </div>
              ))}
            </div>
          )}
        </article>
      </section>
    </div>
  );
}
