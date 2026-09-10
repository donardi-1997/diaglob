import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BrainCircuit,
  Check,
  CreditCard,
  Lightbulb,
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
import "../onboarding-activation-polish.css";

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
    nextTitle: string;
    nextSubtitle: string;
    nextLabel: string;
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
    nextTitle: "¿Qué pasa después de conectar?",
    nextSubtitle: "Usa estos siguientes pasos para convertir una conexión técnica en una operación activa.",
    nextLabel: "Siguiente paso",
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
    nextTitle: "What happens after you connect?",
    nextSubtitle: "Use these next steps to turn a technical connection into an active operating workflow.",
    nextLabel: "Next step",
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
    nextTitle: "O que acontece depois de conectar?",
    nextSubtitle: "Use estes próximos passos para transformar uma conexão técnica em uma operação ativa.",
    nextLabel: "Próximo passo",
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

const NEXT_STEP_COPY: Record<LocaleKey, Record<string, string>> = {
  es: {
    shopify:
      "Sincroniza el catálogo y valida variantes/precios. Luego revisa Comercio para confirmar que los pedidos y productos queden listos para operar y medir.",
    nuvemshop:
      "Sincroniza productos y pedidos. Después revisa Comercio y Analíticas para validar catálogo, órdenes y rendimiento de la tienda.",
    whatsapp:
      "Completa el webhook y token de verificación en Meta y envía un mensaje de prueba. Las conversaciones nuevas aparecerán en la bandeja de Diaglob.",
    telegram:
      "Envía un mensaje de prueba para validar entrada y salida. Las conversaciones nuevas quedarán disponibles en la bandeja operativa.",
    dropi:
      "Valida catálogo, costos y disponibilidad del proveedor antes de usar esos datos en pedidos y analítica de rentabilidad.",
    payments:
      "Verifica credenciales y ambiente, ejecuta una prueba controlada y confirma conciliación antes de usar el proveedor en producción.",
    commerce:
      "Sincroniza el catálogo disponible y revisa Comercio para validar productos, variantes y pedidos antes de operar.",
    messaging:
      "Envía un mensaje de prueba y confirma que la conversación aparezca en la bandeja antes de activar automatizaciones o IA.",
    supplier:
      "Revisa que catálogo, costos y disponibilidad estén completos antes de usar el proveedor en la operación.",
    default:
      "Haz una prueba del flujo conectado y confirma que los datos esperados aparezcan en Diaglob antes de usarlo en producción.",
  },
  en: {
    shopify:
      "Sync the catalog and validate variants and prices. Then review Commerce to confirm products and orders are ready to operate and measure.",
    nuvemshop:
      "Sync products and orders, then review Commerce and Analytics to validate catalog, orders, and store performance.",
    whatsapp:
      "Finish the webhook and verification-token setup in Meta and send a test message. New conversations should appear in the Diaglob inbox.",
    telegram:
      "Send a test message to validate inbound and outbound delivery. New conversations should appear in the operating inbox.",
    dropi:
      "Validate supplier catalog, costs, and availability before using that data in orders and profitability analytics.",
    payments:
      "Verify credentials and environment, run a controlled test, and confirm reconciliation before using the provider in production.",
    commerce:
      "Sync the available catalog and review Commerce to validate products, variants, and orders before operating.",
    messaging:
      "Send a test message and confirm the conversation appears in the inbox before enabling automations or AI.",
    supplier:
      "Review catalog, costs, and availability before using the supplier in your operating workflow.",
    default:
      "Test the connected workflow and confirm expected data appears in Diaglob before using it in production.",
  },
  "pt-BR": {
    shopify:
      "Sincronize o catálogo e valide variantes e preços. Depois revise Comércio para confirmar que produtos e pedidos estão prontos para operar e medir.",
    nuvemshop:
      "Sincronize produtos e pedidos e depois revise Comércio e Analytics para validar catálogo, pedidos e desempenho da loja.",
    whatsapp:
      "Conclua o webhook e o token de verificação no Meta e envie uma mensagem de teste. Novas conversas aparecerão na caixa de entrada da Diaglob.",
    telegram:
      "Envie uma mensagem de teste para validar entrada e saída. Novas conversas ficarão disponíveis na caixa de entrada operacional.",
    dropi:
      "Valide catálogo, custos e disponibilidade do fornecedor antes de usar esses dados em pedidos e analytics de rentabilidade.",
    payments:
      "Verifique credenciais e ambiente, execute um teste controlado e confirme a conciliação antes de usar o provedor em produção.",
    commerce:
      "Sincronize o catálogo disponível e revise Comércio para validar produtos, variantes e pedidos antes de operar.",
    messaging:
      "Envie uma mensagem de teste e confirme que a conversa aparece na caixa de entrada antes de ativar automações ou IA.",
    supplier:
      "Revise catálogo, custos e disponibilidade antes de usar o fornecedor na operação.",
    default:
      "Teste o fluxo conectado e confirme que os dados esperados aparecem na Diaglob antes de usar em produção.",
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

function nextStepFor(integration: OperationsIntegration, locale: LocaleKey) {
  const identity = `${integration.provider || ""} ${integration.key || ""} ${integration.name || ""}`.toLowerCase();
  const copy = NEXT_STEP_COPY[locale];

  if (identity.includes("shopify")) return copy.shopify;
  if (identity.includes("nuvem")) return copy.nuvemshop;
  if (identity.includes("whatsapp")) return copy.whatsapp;
  if (identity.includes("telegram")) return copy.telegram;
  if (identity.includes("dropi") || identity.includes("droppi")) return copy.dropi;
  if (integration.category === "payments" || integration.category === "payment") return copy.payments;
  if (integration.category === "commerce") return copy.commerce;
  if (integration.category === "messaging") return copy.messaging;
  if (integration.category === "supplier") return copy.supplier;
  return copy.default;
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
      setSummary(null);
      setSummaryError(true);
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => {
    setSummary(null);
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

  const hasSummary = summary !== null;
  const integrations = summary?.integrations || [];
  const connectedIntegrations = integrations.filter((integration) => integration.connected);
  const connectedCount = connectedIntegrations.length;
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
            <strong>{hasSummary ? connectedCount : "—"}</strong>
          </div>
        </article>
        <article>
          <div
            className={`integrations-hub-summary-icon ${
              hasSummary && attentionCount > 0 ? "is-warning" : "is-neutral"
            }`}
          >
            <AlertTriangle size={18} />
          </div>
          <div>
            <span>{copy.attention}</span>
            <strong>{hasSummary ? attentionCount : "—"}</strong>
          </div>
        </article>
        <article>
          <div className="integrations-hub-summary-icon is-accent">
            <Plug size={18} />
          </div>
          <div>
            <span>{copy.available}</span>
            <strong>{hasSummary ? integrations.length : "—"}</strong>
          </div>
        </article>
        <article>
          <div className="integrations-hub-summary-icon is-neutral">
            <Activity size={18} />
          </div>
          <div>
            <span>Stack</span>
            <strong>{hasSummary ? categoryCount : "—"}</strong>
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

      {connectedIntegrations.length > 0 && (
        <section className="integrations-hub-panel integrations-hub-next">
          <div className="integrations-hub-panel-heading">
            <div>
              <span>ACTIVATION</span>
              <h2>{copy.nextTitle}</h2>
              <p>{copy.nextSubtitle}</p>
            </div>
          </div>
          <div className="integrations-hub-next-grid">
            {connectedIntegrations.map((integration) => (
              <article className="integrations-hub-next-card" key={`next-${integration.key}`}>
                <div className="integrations-hub-next-icon">
                  <Lightbulb size={18} />
                </div>
                <div className="integrations-hub-next-copy">
                  <span>{copy.nextLabel}</span>
                  <strong>{integration.name}</strong>
                  <p>{nextStepFor(integration, locale)}</p>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

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
