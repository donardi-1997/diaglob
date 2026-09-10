import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BrainCircuit,
  Check,
  CreditCard,
  MessageSquareText,
  Package,
  Plug,
  RefreshCw,
  ShoppingBag,
  Sparkles,
  Store as StoreIcon,
} from "lucide-react";

import StoreIntegrations from "../components/StoreIntegrations";
import {
  getOperationsSummary,
  type OperationsIntegration,
  type OperationsSummary,
} from "../services/operations";
import "../integrations-hub-v2.css";

interface IntegrationsHubPageProps {
  storeId: number;
  storeName?: string;
  shopDomain?: string | null;
  canWrite: boolean;
  onNavigateToKnowledge: () => void;
  onNavigateToStores: () => void;
}

type LocaleKey = "es" | "en" | "pt-BR";

const COPY: Record<
  LocaleKey,
  {
    eyebrow: string;
    title: string;
    subtitle: string;
    activeStore: string;
    refresh: string;
    connected: string;
    attention: string;
    available: string;
    healthTitle: string;
    healthSubtitle: string;
    managedTitle: string;
    managedSubtitle: string;
    knowledgeTitle: string;
    knowledgeSubtitle: string;
    knowledgeAction: string;
    noStoreTitle: string;
    noStoreSubtitle: string;
    noStoreAction: string;
    loading: string;
    unavailable: string;
    statusConnected: string;
    statusDisconnected: string;
    statusDegraded: string;
    categories: Record<string, string>;
  }
> = {
  es: {
    eyebrow: "ECOSISTEMA CONECTADO",
    title: "Integraciones",
    subtitle:
      "Conecta los canales que mueven tu operación y mantén comercio, mensajería, proveedores y pagos bajo control desde un solo lugar.",
    activeStore: "Tienda activa",
    refresh: "Actualizar estado",
    connected: "Conectadas",
    attention: "Requieren atención",
    available: "Integraciones visibles",
    healthTitle: "Salud de conexiones",
    healthSubtitle: "Estado operativo reportado por Diaglob para la tienda activa.",
    managedTitle: "Administrar conexiones",
    managedSubtitle: "Conecta, prueba, sincroniza o desconecta los proveedores disponibles para esta tienda.",
    knowledgeTitle: "Google & Knowledge",
    knowledgeSubtitle:
      "Drive, Sheets y Docs se administran dentro de Knowledge para mantener OAuth, fuentes e ingestión en el mismo flujo.",
    knowledgeAction: "Abrir Knowledge",
    noStoreTitle: "Crea una tienda antes de conectar tu stack",
    noStoreSubtitle:
      "Las integraciones operativas pertenecen a una tienda. Crea o activa una para comenzar.",
    noStoreAction: "Ir a Tiendas",
    loading: "Leyendo el estado de tus conexiones...",
    unavailable: "No pudimos leer la salud general. Puedes seguir administrando las conexiones debajo.",
    statusConnected: "Conectado",
    statusDisconnected: "Sin conectar",
    statusDegraded: "Atención requerida",
    categories: {
      commerce: "Comercio",
      messaging: "Mensajería",
      supplier: "Proveedor",
      payments: "Pagos",
      payment: "Pagos",
      knowledge: "Knowledge",
      ads: "Publicidad",
    },
  },
  en: {
    eyebrow: "CONNECTED ECOSYSTEM",
    title: "Integrations",
    subtitle:
      "Connect the channels that run your operation and keep commerce, messaging, suppliers and payments under control in one place.",
    activeStore: "Active store",
    refresh: "Refresh status",
    connected: "Connected",
    attention: "Need attention",
    available: "Visible integrations",
    healthTitle: "Connection health",
    healthSubtitle: "Operational status reported by Diaglob for the active store.",
    managedTitle: "Manage connections",
    managedSubtitle: "Connect, test, sync or disconnect the providers available for this store.",
    knowledgeTitle: "Google & Knowledge",
    knowledgeSubtitle:
      "Drive, Sheets and Docs are managed inside Knowledge so OAuth, sources and ingestion stay in one workflow.",
    knowledgeAction: "Open Knowledge",
    noStoreTitle: "Create a store before connecting your stack",
    noStoreSubtitle:
      "Operational integrations belong to a store. Create or activate one to get started.",
    noStoreAction: "Go to Stores",
    loading: "Reading the status of your connections...",
    unavailable: "We could not read overall health. You can still manage the connections below.",
    statusConnected: "Connected",
    statusDisconnected: "Not connected",
    statusDegraded: "Needs attention",
    categories: {
      commerce: "Commerce",
      messaging: "Messaging",
      supplier: "Supplier",
      payments: "Payments",
      payment: "Payments",
      knowledge: "Knowledge",
      ads: "Advertising",
    },
  },
  "pt-BR": {
    eyebrow: "ECOSSISTEMA CONECTADO",
    title: "Integrações",
    subtitle:
      "Conecte os canais que movem sua operação e mantenha comércio, mensagens, fornecedores e pagamentos sob controle em um só lugar.",
    activeStore: "Loja ativa",
    refresh: "Atualizar status",
    connected: "Conectadas",
    attention: "Precisam de atenção",
    available: "Integrações visíveis",
    healthTitle: "Saúde das conexões",
    healthSubtitle: "Status operacional reportado pela Diaglob para a loja ativa.",
    managedTitle: "Gerenciar conexões",
    managedSubtitle: "Conecte, teste, sincronize ou desconecte os provedores disponíveis para esta loja.",
    knowledgeTitle: "Google & Knowledge",
    knowledgeSubtitle:
      "Drive, Sheets e Docs são gerenciados dentro de Knowledge para manter OAuth, fontes e ingestão no mesmo fluxo.",
    knowledgeAction: "Abrir Knowledge",
    noStoreTitle: "Crie uma loja antes de conectar seu stack",
    noStoreSubtitle:
      "As integrações operacionais pertencem a uma loja. Crie ou ative uma para começar.",
    noStoreAction: "Ir para Lojas",
    loading: "Lendo o status das suas conexões...",
    unavailable: "Não foi possível ler a saúde geral. Você ainda pode gerenciar as conexões abaixo.",
    statusConnected: "Conectado",
    statusDisconnected: "Não conectado",
    statusDegraded: "Requer atenção",
    categories: {
      commerce: "Comércio",
      messaging: "Mensagens",
      supplier: "Fornecedor",
      payments: "Pagamentos",
      payment: "Pagamentos",
      knowledge: "Knowledge",
      ads: "Publicidade",
    },
  },
};

function normalizeLocale(language: string): LocaleKey {
  if (language.toLowerCase().startsWith("pt")) return "pt-BR";
  if (language.toLowerCase().startsWith("en")) return "en";
  return "es";
}

function IntegrationIcon({ category }: { category: string }) {
  if (category === "commerce") return <ShoppingBag size={17} />;
  if (category === "messaging") return <MessageSquareText size={17} />;
  if (category === "supplier") return <Package size={17} />;
  if (category === "payments" || category === "payment") return <CreditCard size={17} />;
  if (category === "knowledge") return <BrainCircuit size={17} />;
  return <Plug size={17} />;
}

export default function IntegrationsHubPage({
  storeId,
  storeName,
  shopDomain,
  canWrite,
  onNavigateToKnowledge,
  onNavigateToStores,
}: IntegrationsHubPageProps) {
  const { i18n } = useTranslation();
  const locale = normalizeLocale(i18n.resolvedLanguage || i18n.language || "es");
  const copy = COPY[locale];
  const [summary, setSummary] = useState<OperationsSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [summaryError, setSummaryError] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const loadSummary = useCallback(async () => {
    if (!storeId) {
      setSummary(null);
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setSummaryError(false);
      const result = await getOperationsSummary(storeId);
      setSummary(result);
    } catch (error) {
      console.error("Unable to load integration health", error);
      setSummaryError(true);
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => {
    void loadSummary();
  }, [loadSummary]);

  useEffect(() => {
    const handleFocus = () => {
      setRefreshKey((current) => current + 1);
      void loadSummary();
    };

    window.addEventListener("focus", handleFocus);
    return () => window.removeEventListener("focus", handleFocus);
  }, [loadSummary]);

  const integrations = summary?.integrations || [];
  const connectedCount = integrations.filter((integration) => integration.connected).length;
  const attentionCount = integrations.filter(
    (integration) => integration.degraded || integration.status === "degraded",
  ).length;

  const categoryCount = useMemo(
    () => new Set(integrations.map((integration) => integration.category)).size,
    [integrations],
  );

  const refresh = () => {
    setRefreshKey((current) => current + 1);
    void loadSummary();
  };

  if (!storeId) {
    return (
      <div className="integrations-hub-v2">
        <section className="integrations-hub-empty">
          <div className="integrations-hub-empty-icon">
            <StoreIcon size={28} />
          </div>
          <h1>{copy.noStoreTitle}</h1>
          <p>{copy.noStoreSubtitle}</p>
          <button type="button" onClick={onNavigateToStores}>
            <StoreIcon size={16} />
            {copy.noStoreAction}
          </button>
        </section>
      </div>
    );
  }

  return (
    <div className="integrations-hub-v2">
      <section className="integrations-hub-hero">
        <div>
          <div className="integrations-hub-eyebrow">
            <Sparkles size={14} />
            <span>{copy.eyebrow}</span>
          </div>
          <h1>{copy.title}</h1>
          <p>{copy.subtitle}</p>
        </div>

        <div className="integrations-hub-store-context">
          <span>{copy.activeStore}</span>
          <strong>{storeName || "Diaglob"}</strong>
          {shopDomain && <small>{shopDomain}</small>}
        </div>
      </section>

      <section className="integrations-hub-summary">
        <article>
          <div className="integrations-hub-summary-icon is-positive">
            <Check size={18} />
          </div>
          <div>
            <span>{copy.connected}</span>
            <strong>{connectedCount}</strong>
          </div>
        </article>
        <article>
          <div className={`integrations-hub-summary-icon ${attentionCount > 0 ? "is-warning" : "is-neutral"}`}>
            <AlertTriangle size={18} />
          </div>
          <div>
            <span>{copy.attention}</span>
            <strong>{attentionCount}</strong>
          </div>
        </article>
        <article>
          <div className="integrations-hub-summary-icon is-accent">
            <Plug size={18} />
          </div>
          <div>
            <span>{copy.available}</span>
            <strong>{integrations.length}</strong>
          </div>
        </article>
        <article>
          <div className="integrations-hub-summary-icon is-neutral">
            <Activity size={18} />
          </div>
          <div>
            <span>Stack</span>
            <strong>{categoryCount}</strong>
          </div>
        </article>
      </section>

      <section className="integrations-hub-panel integrations-hub-health">
        <div className="integrations-hub-panel-heading">
          <div>
            <span>STATUS</span>
            <h2>{copy.healthTitle}</h2>
            <p>{copy.healthSubtitle}</p>
          </div>
          <button type="button" className="integrations-hub-refresh" onClick={refresh} disabled={loading}>
            <RefreshCw className={loading ? "spin" : ""} size={15} />
            {copy.refresh}
          </button>
        </div>

        {summaryError && (
          <div className="integrations-hub-message is-warning">
            <AlertTriangle size={16} />
            <span>{copy.unavailable}</span>
          </div>
        )}

        {loading && integrations.length === 0 ? (
          <div className="integrations-hub-loading">
            <RefreshCw className="spin" size={18} />
            <span>{copy.loading}</span>
          </div>
        ) : integrations.length > 0 ? (
          <div className="integrations-hub-health-grid">
            {integrations.map((integration: OperationsIntegration) => {
              const degraded = integration.degraded || integration.status === "degraded";
              const statusLabel = integration.connected
                ? copy.statusConnected
                : degraded
                  ? copy.statusDegraded
                  : copy.statusDisconnected;

              return (
                <article
                  key={integration.key}
                  className={`integrations-hub-health-card ${
                    integration.connected ? "is-connected" : degraded ? "is-degraded" : "is-disconnected"
                  }`}
                >
                  <div className="integrations-hub-health-icon">
                    <IntegrationIcon category={integration.category} />
                  </div>
                  <div className="integrations-hub-health-copy">
                    <span>{copy.categories[integration.category] || integration.category}</span>
                    <strong>{integration.name}</strong>
                  </div>
                  <div className="integrations-hub-health-status">
                    <span />
                    {statusLabel}
                  </div>
                </article>
              );
            })}
          </div>
        ) : null}
      </section>

      <section className="integrations-hub-knowledge-card">
        <div className="integrations-hub-knowledge-icon">
          <BrainCircuit size={22} />
        </div>
        <div>
          <span>KNOWLEDGE</span>
          <h2>{copy.knowledgeTitle}</h2>
          <p>{copy.knowledgeSubtitle}</p>
        </div>
        <button type="button" onClick={onNavigateToKnowledge}>
          {copy.knowledgeAction}
          <ArrowRight size={16} />
        </button>
      </section>

      <section className="integrations-hub-panel integrations-hub-management">
        <div className="integrations-hub-panel-heading">
          <div>
            <span>CONNECTORS</span>
            <h2>{copy.managedTitle}</h2>
            <p>{copy.managedSubtitle}</p>
          </div>
        </div>

        <StoreIntegrations
          key={`${storeId}-${refreshKey}`}
          storeId={storeId}
          shopDomain={shopDomain || null}
          canWrite={canWrite}
        />
      </section>
    </div>
  );
}
