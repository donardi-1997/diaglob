import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BrainCircuit,
  Check,
  ChevronRight,
  CreditCard,
  Filter,
  MessageSquareText,
  Package,
  Plug,
  RefreshCw,
  Search,
  ShieldCheck,
  ShoppingBag,
  Sparkles,
  Store as StoreIcon,
  Truck,
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
  storeCountryCode?: string | null;
  canWrite: boolean;
  onNavigateToKnowledge: () => void;
  onNavigateToStores: () => void;
}

type LocaleKey = "es" | "en" | "pt-BR";
type StatusFilter = "all" | "connected" | "available" | "attention";

interface CatalogIntegration extends OperationsIntegration {
  description: string;
  virtual?: boolean;
}

const COPY: Record<LocaleKey, {
  eyebrow: string;
  title: string;
  subtitle: string;
  activeStore: string;
  refresh: string;
  connected: string;
  attention: string;
  available: string;
  categoriesLabel: string;
  catalogTitle: string;
  catalogSubtitle: string;
  searchPlaceholder: string;
  all: string;
  connectedFilter: string;
  availableFilter: string;
  attentionFilter: string;
  configure: string;
  manage: string;
  openKnowledge: string;
  noResultsTitle: string;
  noResultsSubtitle: string;
  managedTitle: string;
  managedSubtitle: string;
  securityTitle: string;
  securitySubtitle: string;
  noStoreTitle: string;
  noStoreSubtitle: string;
  noStoreAction: string;
  loading: string;
  unavailable: string;
  statusConnected: string;
  statusDisconnected: string;
  statusDegraded: string;
  statusPlanned: string;
  nextLabel: string;
  storeScope: string;
  orgScope: string;
  categories: Record<string, string>;
}> = {
  es: {
    eyebrow: "ECOSISTEMA CONECTADO",
    title: "Integraciones",
    subtitle: "Conecta tu operación sin convertir la configuración técnica en otro trabajo. Todo el stack, su estado y sus próximos pasos en un solo lugar.",
    activeStore: "Tienda activa",
    refresh: "Actualizar",
    connected: "Conectadas",
    attention: "Requieren atención",
    available: "Integraciones",
    categoriesLabel: "Categorías",
    catalogTitle: "Tu ecosistema",
    catalogSubtitle: "Busca, filtra y administra las herramientas que conectan comercio, mensajería, proveedores, logística, pagos y conocimiento.",
    searchPlaceholder: "Buscar Shopify, WhatsApp, proveedor...",
    all: "Todas",
    connectedFilter: "Conectadas",
    availableFilter: "Por conectar",
    attentionFilter: "Con atención",
    configure: "Configurar",
    manage: "Administrar",
    openKnowledge: "Abrir Knowledge",
    noResultsTitle: "No encontramos integraciones",
    noResultsSubtitle: "Prueba otra búsqueda o cambia los filtros.",
    managedTitle: "Configuración y credenciales",
    managedSubtitle: "Conecta, prueba, sincroniza o desconecta proveedores. Las acciones avanzadas aparecen solo cuando las necesitas.",
    securityTitle: "Credenciales protegidas",
    securitySubtitle: "Los secretos se envían únicamente al backend y no vuelven a mostrarse después de guardarlos.",
    noStoreTitle: "Crea una tienda antes de conectar tu stack",
    noStoreSubtitle: "Las integraciones operativas pertenecen a una tienda. Crea o activa una para comenzar.",
    noStoreAction: "Ir a Tiendas",
    loading: "Leyendo el estado de tus conexiones...",
    unavailable: "No pudimos leer la salud general. Puedes seguir administrando tus conexiones.",
    statusConnected: "Conectada",
    statusDisconnected: "Por conectar",
    statusDegraded: "Atención requerida",
    statusPlanned: "Acceso pendiente",
    nextLabel: "Siguiente paso",
    storeScope: "Esta tienda",
    orgScope: "Organización",
    categories: {
      commerce: "Comercio",
      messaging: "Mensajería",
      supplier: "Proveedores",
      payments: "Pagos",
      payment: "Pagos",
      knowledge: "Knowledge",
      logistics: "Logística",
      ads: "Publicidad",
    },
  },
  en: {
    eyebrow: "CONNECTED ECOSYSTEM",
    title: "Integrations",
    subtitle: "Connect your operation without turning technical setup into another job. Your stack, its health and next steps in one place.",
    activeStore: "Active store",
    refresh: "Refresh",
    connected: "Connected",
    attention: "Need attention",
    available: "Integrations",
    categoriesLabel: "Categories",
    catalogTitle: "Your ecosystem",
    catalogSubtitle: "Search, filter and manage the tools connecting commerce, messaging, suppliers, logistics, payments and knowledge.",
    searchPlaceholder: "Search Shopify, WhatsApp, supplier...",
    all: "All",
    connectedFilter: "Connected",
    availableFilter: "To connect",
    attentionFilter: "Needs attention",
    configure: "Configure",
    manage: "Manage",
    openKnowledge: "Open Knowledge",
    noResultsTitle: "No integrations found",
    noResultsSubtitle: "Try another search or change the filters.",
    managedTitle: "Configuration and credentials",
    managedSubtitle: "Connect, test, sync or disconnect providers. Advanced actions appear only when you need them.",
    securityTitle: "Protected credentials",
    securitySubtitle: "Secrets are sent only to the backend and are not shown again after they are saved.",
    noStoreTitle: "Create a store before connecting your stack",
    noStoreSubtitle: "Operational integrations belong to a store. Create or activate one to get started.",
    noStoreAction: "Go to Stores",
    loading: "Reading the status of your connections...",
    unavailable: "We could not read overall health. You can still manage your connections.",
    statusConnected: "Connected",
    statusDisconnected: "To connect",
    statusDegraded: "Needs attention",
    statusPlanned: "Access pending",
    nextLabel: "Next step",
    storeScope: "This store",
    orgScope: "Organization",
    categories: {
      commerce: "Commerce",
      messaging: "Messaging",
      supplier: "Suppliers",
      payments: "Payments",
      payment: "Payments",
      knowledge: "Knowledge",
      logistics: "Logistics",
      ads: "Advertising",
    },
  },
  "pt-BR": {
    eyebrow: "ECOSSISTEMA CONECTADO",
    title: "Integrações",
    subtitle: "Conecte sua operação sem transformar a configuração técnica em outro trabalho. Stack, saúde e próximos passos em um só lugar.",
    activeStore: "Loja ativa",
    refresh: "Atualizar",
    connected: "Conectadas",
    attention: "Precisam de atenção",
    available: "Integrações",
    categoriesLabel: "Categorias",
    catalogTitle: "Seu ecossistema",
    catalogSubtitle: "Busque, filtre e gerencie as ferramentas que conectam comércio, mensagens, fornecedores, logística, pagamentos e conhecimento.",
    searchPlaceholder: "Buscar Shopify, WhatsApp, fornecedor...",
    all: "Todas",
    connectedFilter: "Conectadas",
    availableFilter: "Para conectar",
    attentionFilter: "Com atenção",
    configure: "Configurar",
    manage: "Gerenciar",
    openKnowledge: "Abrir Knowledge",
    noResultsTitle: "Nenhuma integração encontrada",
    noResultsSubtitle: "Tente outra busca ou altere os filtros.",
    managedTitle: "Configuração e credenciais",
    managedSubtitle: "Conecte, teste, sincronize ou desconecte provedores. Ações avançadas aparecem apenas quando necessário.",
    securityTitle: "Credenciais protegidas",
    securitySubtitle: "Os segredos são enviados somente ao backend e não voltam a ser exibidos depois de salvos.",
    noStoreTitle: "Crie uma loja antes de conectar seu stack",
    noStoreSubtitle: "As integrações operacionais pertencem a uma loja. Crie ou ative uma para começar.",
    noStoreAction: "Ir para Lojas",
    loading: "Lendo o status das suas conexões...",
    unavailable: "Não foi possível ler a saúde geral. Você ainda pode gerenciar suas conexões.",
    statusConnected: "Conectada",
    statusDisconnected: "Para conectar",
    statusDegraded: "Requer atenção",
    statusPlanned: "Acesso pendente",
    nextLabel: "Próximo passo",
    storeScope: "Esta loja",
    orgScope: "Organização",
    categories: {
      commerce: "Comércio",
      messaging: "Mensagens",
      supplier: "Fornecedores",
      payments: "Pagamentos",
      payment: "Pagamentos",
      knowledge: "Knowledge",
      logistics: "Logística",
      ads: "Publicidade",
    },
  },
};

const PROVIDER_COPY: Record<LocaleKey, Record<string, string>> = {
  es: {
    shopify: "Sincroniza productos, variantes y pedidos de tu tienda.",
    nuvemshop: "Conecta catálogo y pedidos para operar tiendas Nuvemshop.",
    whatsapp: "Centraliza conversaciones de WhatsApp y habilita automatizaciones.",
    telegram: "Recibe y responde conversaciones de Telegram desde Diaglob.",
    instagram: "Conecta mensajes de Instagram con tu bandeja y automatizaciones.",
    dropi: "Proveedor para dropshipping. La API directa se activará cuando Dropi entregue acceso oficial.",
    cj: "Sincroniza catálogo y operaciones con CJ Dropshipping.",
    google: "Conecta Drive, Sheets y Docs como fuentes de conocimiento.",
    nequi: "Conecta cobros y conciliación de pagos para Colombia.",
    meta_ads: "Conecta datos publicitarios para medir rendimiento y adquisición.",
    default: "Conecta esta herramienta para centralizar la operación en Diaglob.",
  },
  en: {
    shopify: "Sync products, variants and orders from your store.",
    nuvemshop: "Connect catalog and orders to operate Nuvemshop stores.",
    whatsapp: "Centralize WhatsApp conversations and enable automations.",
    telegram: "Receive and reply to Telegram conversations from Diaglob.",
    instagram: "Connect Instagram messages to your inbox and automations.",
    dropi: "Dropshipping supplier. Direct API access will activate once Dropi provides official access.",
    cj: "Sync catalog and operations with CJ Dropshipping.",
    google: "Connect Drive, Sheets and Docs as knowledge sources.",
    nequi: "Connect payments and reconciliation for Colombia.",
    meta_ads: "Connect advertising data to measure performance and acquisition.",
    default: "Connect this tool to centralize your operation in Diaglob.",
  },
  "pt-BR": {
    shopify: "Sincronize produtos, variantes e pedidos da sua loja.",
    nuvemshop: "Conecte catálogo e pedidos para operar lojas Nuvemshop.",
    whatsapp: "Centralize conversas do WhatsApp e habilite automações.",
    telegram: "Receba e responda conversas do Telegram pela Diaglob.",
    instagram: "Conecte mensagens do Instagram à caixa de entrada e automações.",
    dropi: "Fornecedor de dropshipping. A API direta será ativada quando a Dropi fornecer acesso oficial.",
    cj: "Sincronize catálogo e operações com CJ Dropshipping.",
    google: "Conecte Drive, Sheets e Docs como fontes de conhecimento.",
    nequi: "Conecte pagamentos e conciliação para a Colômbia.",
    meta_ads: "Conecte dados de publicidade para medir desempenho e aquisição.",
    default: "Conecte esta ferramenta para centralizar sua operação na Diaglob.",
  },
};

const NEXT_STEP_COPY: Record<LocaleKey, Record<string, string>> = {
  es: {
    shopify: "Sincroniza el catálogo y valida variantes y precios antes de operar.",
    nuvemshop: "Sincroniza productos y pedidos y valida los datos en Comercio.",
    whatsapp: "Envía un mensaje de prueba y confirma que llegue a Conversaciones.",
    telegram: "Prueba entrada y salida antes de activar automatizaciones.",
    instagram: "Valida un mensaje entrante antes de automatizar respuestas.",
    google: "Añade una fuente y confirma que el contenido quede disponible en Knowledge.",
    supplier: "Valida catálogo, costos y disponibilidad antes de crear pedidos.",
    logistics: "Prueba una guía y confirma que los cambios de estado lleguen al tracking.",
    payments: "Ejecuta una prueba controlada y confirma conciliación antes de producción.",
    default: "Haz una prueba de punta a punta antes de usarla en producción.",
  },
  en: {
    shopify: "Sync the catalog and validate variants and prices before operating.",
    nuvemshop: "Sync products and orders and validate the data in Commerce.",
    whatsapp: "Send a test message and confirm it reaches Conversations.",
    telegram: "Test inbound and outbound delivery before enabling automations.",
    instagram: "Validate one inbound message before automating replies.",
    google: "Add a source and confirm its content is available in Knowledge.",
    supplier: "Validate catalog, costs and availability before creating orders.",
    logistics: "Test a tracking number and confirm status updates reach tracking.",
    payments: "Run a controlled test and confirm reconciliation before production.",
    default: "Run an end-to-end test before using it in production.",
  },
  "pt-BR": {
    shopify: "Sincronize o catálogo e valide variantes e preços antes de operar.",
    nuvemshop: "Sincronize produtos e pedidos e valide os dados em Comércio.",
    whatsapp: "Envie uma mensagem de teste e confirme que chega em Conversas.",
    telegram: "Teste entrada e saída antes de ativar automações.",
    instagram: "Valide uma mensagem recebida antes de automatizar respostas.",
    google: "Adicione uma fonte e confirme que o conteúdo está disponível em Knowledge.",
    supplier: "Valide catálogo, custos e disponibilidade antes de criar pedidos.",
    logistics: "Teste um rastreio e confirme as atualizações de status.",
    payments: "Execute um teste controlado e confirme a conciliação antes da produção.",
    default: "Execute um teste ponta a ponta antes de usar em produção.",
  },
};

const FALLBACK_CATALOG: Omit<OperationsIntegration, "connected" | "status">[] = [
  { key: "catalog:shopify", provider: "shopify", name: "Shopify", category: "commerce", available: true, scope: "store" },
  { key: "catalog:nuvemshop", provider: "nuvemshop", name: "Nuvemshop", category: "commerce", available: true, scope: "store" },
  { key: "catalog:whatsapp", provider: "whatsapp", name: "WhatsApp", category: "messaging", available: true, scope: "store" },
  { key: "catalog:telegram", provider: "telegram", name: "Telegram", category: "messaging", available: true, scope: "store" },
  { key: "catalog:instagram", provider: "instagram", name: "Instagram", category: "messaging", available: true, scope: "store" },
  { key: "catalog:dropi", provider: "dropi", name: "Dropi", category: "supplier", available: false, scope: "store" },
  { key: "catalog:cj", provider: "cj", name: "CJ Dropshipping", category: "supplier", available: true, scope: "store" },
  { key: "catalog:google", provider: "google", name: "Google & Knowledge", category: "knowledge", available: true, scope: "organization" },
];

function normalizeLocale(language: string): LocaleKey {
  if (language.toLowerCase().startsWith("pt")) return "pt-BR";
  if (language.toLowerCase().startsWith("en")) return "en";
  return "es";
}

function IntegrationIcon({ category }: { category: string }) {
  if (category === "commerce") return <ShoppingBag size={19} />;
  if (category === "messaging") return <MessageSquareText size={19} />;
  if (category === "supplier") return <Package size={19} />;
  if (category === "logistics") return <Truck size={19} />;
  if (category === "payments" || category === "payment") return <CreditCard size={19} />;
  if (category === "knowledge") return <BrainCircuit size={19} />;
  return <Plug size={19} />;
}

function normalizeProvider(integration: OperationsIntegration) {
  const raw = (integration.provider || integration.name || "").toLowerCase();
  if (raw.includes("shopify")) return "shopify";
  if (raw.includes("nuvem")) return "nuvemshop";
  if (raw.includes("whatsapp")) return "whatsapp";
  if (raw.includes("telegram")) return "telegram";
  if (raw.includes("instagram")) return "instagram";
  if (raw.includes("dropi")) return "dropi";
  if (raw === "cj" || raw.includes("cj dropshipping")) return "cj";
  if (raw.includes("google")) return "google";
  if (raw.includes("nequi")) return "nequi";
  if (raw.includes("meta")) return "meta_ads";
  return raw.replace(/[^a-z0-9_]+/g, "_");
}

function statusKind(integration: OperationsIntegration): "connected" | "attention" | "available" | "planned" {
  if (integration.degraded || integration.status === "degraded") return "attention";
  if (integration.connected) return "connected";
  if (integration.available === false || integration.status === "planned") return "planned";
  return "available";
}

function nextStepFor(integration: OperationsIntegration, locale: LocaleKey) {
  const provider = normalizeProvider(integration);
  const copy = NEXT_STEP_COPY[locale];
  if (copy[provider]) return copy[provider];
  if (integration.category === "supplier") return copy.supplier;
  if (integration.category === "logistics") return copy.logistics;
  if (integration.category === "payments" || integration.category === "payment") return copy.payments;
  return copy.default;
}

export default function IntegrationsHubPage({
  storeId,
  storeName,
  shopDomain,
  storeCountryCode,
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
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [categoryFilter, setCategoryFilter] = useState("all");

  const loadSummary = useCallback(async () => {
    if (!storeId) {
      setSummary(null);
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setSummaryError(false);
      setSummary(await getOperationsSummary(storeId));
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
      setRefreshKey((currentValue) => currentValue + 1);
      void loadSummary();
    };

    window.addEventListener("focus", handleFocus);
    return () => window.removeEventListener("focus", handleFocus);
  }, [loadSummary]);

  const catalog = useMemo<CatalogIntegration[]>(() => {
    const live = summary?.integrations || [];
    const liveByProvider = new Map<string, OperationsIntegration>();

    live.forEach((integration) => {
      liveByProvider.set(normalizeProvider(integration), integration);
    });

    const fallback = FALLBACK_CATALOG.map((item) => {
      const existing = liveByProvider.get(item.provider);
      if (existing) {
        liveByProvider.delete(item.provider);
        return existing;
      }

      return {
        ...item,
        connected: false,
        status: item.available === false ? "planned" : "disconnected",
      } as OperationsIntegration;
    });

    const merged = [...fallback, ...Array.from(liveByProvider.values())];

    return merged.map((integration) => {
      const provider = normalizeProvider(integration);
      return {
        ...integration,
        description: PROVIDER_COPY[locale][provider] || PROVIDER_COPY[locale].default,
        virtual: integration.key.startsWith("catalog:"),
      };
    });
  }, [summary, locale]);

  const categoryOptions = useMemo(
    () => Array.from(new Set(catalog.map((integration) => integration.category))),
    [catalog],
  );

  const filteredCatalog = useMemo(() => {
    const needle = query.trim().toLowerCase();

    return catalog.filter((integration) => {
      const kind = statusKind(integration);
      const matchesStatus =
        statusFilter === "all"
        || (statusFilter === "connected" && kind === "connected")
        || (statusFilter === "available" && (kind === "available" || kind === "planned"))
        || (statusFilter === "attention" && kind === "attention");

      const matchesCategory = categoryFilter === "all" || integration.category === categoryFilter;
      const haystack = `${integration.name} ${integration.provider} ${integration.category} ${integration.description}`.toLowerCase();
      const matchesQuery = !needle || haystack.includes(needle);

      return matchesStatus && matchesCategory && matchesQuery;
    });
  }, [catalog, query, statusFilter, categoryFilter]);

  const connectedCount = catalog.filter((integration) => statusKind(integration) === "connected").length;
  const attentionCount = catalog.filter((integration) => statusKind(integration) === "attention").length;
  const categoryCount = categoryOptions.length;

  const refresh = () => {
    setRefreshKey((currentValue) => currentValue + 1);
    void loadSummary();
  };

  const handleIntegrationAction = (integration: CatalogIntegration) => {
    if (integration.category === "knowledge" || normalizeProvider(integration) === "google") {
      onNavigateToKnowledge();
      return;
    }

    document.getElementById("integration-management")?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  };

  const statusLabel = (integration: CatalogIntegration) => {
    const kind = statusKind(integration);
    if (kind === "connected") return copy.statusConnected;
    if (kind === "attention") return copy.statusDegraded;
    if (kind === "planned") return copy.statusPlanned;
    return copy.statusDisconnected;
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
        <div className="integrations-hub-hero-copy">
          <div className="integrations-hub-eyebrow">
            <Sparkles size={14} />
            <span>{copy.eyebrow}</span>
          </div>
          <h1>{copy.title}</h1>
          <p>{copy.subtitle}</p>
        </div>

        <div className="integrations-hub-store-context">
          <div>
            <span>{copy.activeStore}</span>
            <strong>{storeName || "Diaglob"}</strong>
            {shopDomain && <small>{shopDomain}</small>}
          </div>
          <button type="button" className="integrations-hub-refresh" onClick={refresh} disabled={loading}>
            <RefreshCw className={loading ? "spin" : ""} size={15} />
            {copy.refresh}
          </button>
        </div>
      </section>

      <section className="integrations-hub-summary" aria-label={copy.title}>
        <article>
          <div className="integrations-hub-summary-icon is-positive"><Check size={18} /></div>
          <div><span>{copy.connected}</span><strong>{summary ? connectedCount : "—"}</strong></div>
        </article>
        <article>
          <div className={`integrations-hub-summary-icon ${attentionCount > 0 ? "is-warning" : "is-neutral"}`}>
            <AlertTriangle size={18} />
          </div>
          <div><span>{copy.attention}</span><strong>{summary ? attentionCount : "—"}</strong></div>
        </article>
        <article>
          <div className="integrations-hub-summary-icon is-accent"><Plug size={18} /></div>
          <div><span>{copy.available}</span><strong>{catalog.length}</strong></div>
        </article>
        <article>
          <div className="integrations-hub-summary-icon is-neutral"><Activity size={18} /></div>
          <div><span>{copy.categoriesLabel}</span><strong>{categoryCount}</strong></div>
        </article>
      </section>

      {summaryError && (
        <div className="integrations-hub-message is-warning" role="status">
          <AlertTriangle size={16} />
          <span>{copy.unavailable}</span>
        </div>
      )}

      <section className="integrations-hub-panel integrations-hub-catalog">
        <div className="integrations-hub-panel-heading">
          <div>
            <span>INTEGRATION HUB</span>
            <h2>{copy.catalogTitle}</h2>
            <p>{copy.catalogSubtitle}</p>
          </div>
        </div>

        <div className="integrations-hub-toolbar">
          <label className="integrations-hub-search">
            <Search size={17} />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={copy.searchPlaceholder}
              aria-label={copy.searchPlaceholder}
            />
          </label>

          <div className="integrations-hub-filter-group" aria-label="Status">
            <Filter size={15} />
            {([
              ["all", copy.all],
              ["connected", copy.connectedFilter],
              ["available", copy.availableFilter],
              ["attention", copy.attentionFilter],
            ] as [StatusFilter, string][]).map(([value, label]) => (
              <button
                type="button"
                key={value}
                className={statusFilter === value ? "is-active" : ""}
                onClick={() => setStatusFilter(value)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="integrations-hub-category-tabs" aria-label={copy.categoriesLabel}>
          <button
            type="button"
            className={categoryFilter === "all" ? "is-active" : ""}
            onClick={() => setCategoryFilter("all")}
          >
            {copy.all}
          </button>
          {categoryOptions.map((category) => (
            <button
              type="button"
              key={category}
              className={categoryFilter === category ? "is-active" : ""}
              onClick={() => setCategoryFilter(category)}
            >
              {copy.categories[category] || category}
            </button>
          ))}
        </div>

        {loading && !summary ? (
          <div className="integrations-hub-loading">
            <RefreshCw className="spin" size={18} />
            <span>{copy.loading}</span>
          </div>
        ) : filteredCatalog.length > 0 ? (
          <div className="integrations-hub-catalog-grid">
            {filteredCatalog.map((integration) => {
              const kind = statusKind(integration);
              const provider = normalizeProvider(integration);
              const isKnowledge = integration.category === "knowledge" || provider === "google";

              return (
                <article className={`integrations-hub-card is-${kind}`} key={integration.key}>
                  <div className="integrations-hub-card-top">
                    <div className="integrations-hub-card-icon">
                      <IntegrationIcon category={integration.category} />
                    </div>
                    <div className={`integrations-hub-card-status is-${kind}`}>
                      <span />
                      {statusLabel(integration)}
                    </div>
                  </div>

                  <div className="integrations-hub-card-heading">
                    <span>{copy.categories[integration.category] || integration.category}</span>
                    <h3>{integration.name}</h3>
                  </div>

                  <p className="integrations-hub-card-description">{integration.description}</p>

                  <div className="integrations-hub-card-meta">
                    <span>{integration.scope === "organization" ? copy.orgScope : copy.storeScope}</span>
                    {integration.payment_methods?.slice(0, 2).map((method) => (
                      <span key={method}>{method}</span>
                    ))}
                  </div>

                  {kind === "connected" && (
                    <div className="integrations-hub-card-next">
                      <span>{copy.nextLabel}</span>
                      <p>{nextStepFor(integration, locale)}</p>
                    </div>
                  )}

                  <button
                    type="button"
                    className="integrations-hub-card-action"
                    onClick={() => handleIntegrationAction(integration)}
                  >
                    {isKnowledge ? copy.openKnowledge : kind === "connected" ? copy.manage : copy.configure}
                    {isKnowledge ? <ArrowRight size={15} /> : <ChevronRight size={15} />}
                  </button>
                </article>
              );
            })}
          </div>
        ) : (
          <div className="integrations-hub-no-results">
            <Search size={24} />
            <strong>{copy.noResultsTitle}</strong>
            <p>{copy.noResultsSubtitle}</p>
          </div>
        )}
      </section>

      <section id="integration-management" className="integrations-hub-panel integrations-hub-management">
        <div className="integrations-hub-panel-heading integrations-hub-management-heading">
          <div>
            <span>CONFIGURATION</span>
            <h2>{copy.managedTitle}</h2>
            <p>{copy.managedSubtitle}</p>
          </div>
          <div className="integrations-hub-security">
            <ShieldCheck size={18} />
            <div>
              <strong>{copy.securityTitle}</strong>
              <span>{copy.securitySubtitle}</span>
            </div>
          </div>
        </div>

        <StoreIntegrations
          key={`${storeId}-${refreshKey}`}
          storeId={storeId}
          shopDomain={shopDomain || null}
          storeCountryCode={storeCountryCode}
          canWrite={canWrite}
        />
      </section>
    </div>
  );
}
