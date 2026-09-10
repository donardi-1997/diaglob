import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  Check,
  CircleDollarSign,
  Clock3,
  Globe2,
  Languages,
  Pencil,
  Plug,
  Plus,
  Store as StoreIcon,
  Trash2,
  X,
} from "lucide-react";

import {
  createStore,
  deleteStore,
  getStoresForManagement,
  updateStore,
  type Store,
} from "../services/stores";
import { getMarkets, type Market } from "../services/markets";
import {
  getCurrentOrganization,
  type Organization,
} from "../services/organizations";
import { getCountryFlag, getLanguageName } from "../utils/markets";
import "../stores-v2.css";

interface StoresPageProps {
  canWrite: boolean;
  onStoresChanged?: () => void;
  onOpenPlans?: () => void;
}

interface StoreForm {
  name: string;
  country_code: string;
  currency: string;
  timezone: string;
  default_language: string;
  shopify_domain: string;
  active: boolean;
}

type LocaleKey = "es" | "en" | "pt-BR";

const EMPTY_FORM: StoreForm = {
  name: "",
  country_code: "",
  currency: "",
  timezone: "",
  default_language: "",
  shopify_domain: "",
  active: true,
};

const COPY: Record<
  LocaleKey,
  {
    eyebrow: string;
    title: string;
    subtitle: string;
    planUsage: string;
    storesConfigured: string;
    activeStores: string;
    markets: string;
    integrationsTitle: string;
    integrationsBody: string;
    integrationsHint: string;
    sectionKicker: string;
    sectionTitle: string;
    sectionBody: string;
    currency: string;
    language: string;
    timezone: string;
    commerceDomain: string;
    noCommerceDomain: string;
    active: string;
    inactive: string;
    configure: string;
    delete: string;
    createTitle: string;
    editTitle: string;
    createStepMarket: string;
    createStepDetails: string;
    createStepIntegrations: string;
    market: string;
    storeName: string;
    commerceDomainHelp: string;
    status: string;
    activeHelp: string;
    inactiveHelp: string;
    preview: string;
    nextStepNote: string;
    emptyTitle: string;
    emptyBody: string;
    dangerTitle: string;
    dangerBody: string;
    closeAccount: string;
    closeWarning: string;
    closeLoss1: string;
    closeLoss2: string;
    closeLoss3: string;
    closeConfirm: string;
    deleteStoreTitle: string;
    deleteStoreBody: string;
    deleteStoreWarning: string;
    planLimitTitle: string;
    planCurrent: string;
    understood: string;
    confirmDeleteWord: string;
  }
> = {
  es: {
    eyebrow: "OPERACIÓN MULTITIENDA",
    title: "Tiendas",
    subtitle:
      "Configura cada mercado donde operas. Las conexiones con Shopify, WhatsApp, proveedores y pagos se administran por separado en Integraciones.",
    planUsage: "Uso del plan",
    storesConfigured: "Tiendas configuradas",
    activeStores: "Tiendas activas",
    markets: "Mercados disponibles",
    integrationsTitle: "Integraciones en un solo lugar",
    integrationsBody:
      "Esta vista se concentra en la identidad y configuración operativa de cada tienda. Conecta y sincroniza tus canales desde Integraciones.",
    integrationsHint: "Usa Integraciones en el menú lateral para administrar conexiones",
    sectionKicker: "WORKSPACE",
    sectionTitle: "Tus tiendas",
    sectionBody: "Cada tarjeta representa un mercado operativo independiente.",
    currency: "Moneda",
    language: "Idioma",
    timezone: "Zona horaria",
    commerceDomain: "Dominio de comercio",
    noCommerceDomain: "Sin dominio definido",
    active: "Activa",
    inactive: "Suspendida",
    configure: "Configurar",
    delete: "Eliminar",
    createTitle: "Crear nueva tienda",
    editTitle: "Configurar tienda",
    createStepMarket: "Mercado",
    createStepDetails: "Operación",
    createStepIntegrations: "Integraciones después",
    market: "País / mercado",
    storeName: "Nombre de la tienda",
    commerceDomainHelp:
      "Opcional. Guarda el dominio de Shopify como identificador; la conexión OAuth se completa después en Integraciones.",
    status: "Estado operativo",
    activeHelp: "La tienda estará disponible para la operación y para seleccionar en el workspace.",
    inactiveHelp: "La tienda queda suspendida y no participa en la operación activa.",
    preview: "Vista previa del mercado",
    nextStepNote:
      "Primero crea la tienda. Después conecta Shopify, WhatsApp, proveedores o pagos desde el Hub de Integraciones.",
    emptyTitle: "Crea tu primera tienda",
    emptyBody:
      "Empieza por el mercado principal de tu operación. Podrás añadir conexiones y automatizaciones después.",
    dangerTitle: "Zona de peligro",
    dangerBody:
      "Cerrar tu cuenta desactivará tu acceso a todas las organizaciones y tiendas. Esta acción es irreversible.",
    closeAccount: "Cerrar cuenta",
    closeWarning:
      "Esta acción es permanente. Se eliminará tu cuenta de usuario y se desactivará tu acceso.",
    closeLoss1: "Perderás acceso a todas tus organizaciones",
    closeLoss2: "Se desactivará tu sesión actual",
    closeLoss3: "No podrás recuperar tu cuenta",
    closeConfirm: 'Escribe "ELIMINAR" para confirmar.',
    deleteStoreTitle: "Eliminar tienda",
    deleteStoreBody: "Estás a punto de eliminar",
    deleteStoreWarning:
      "Esta acción elimina el acceso a la tienda y puede afectar datos asociados. Confirma solo si estás seguro.",
    planLimitTitle: "Límite de tiendas alcanzado",
    planCurrent: "Plan actual",
    understood: "Entendido",
    confirmDeleteWord: "ELIMINAR",
  },
  en: {
    eyebrow: "MULTI-STORE OPERATIONS",
    title: "Stores",
    subtitle:
      "Configure every market where you operate. Shopify, WhatsApp, supplier and payment connections are managed separately in Integrations.",
    planUsage: "Plan usage",
    storesConfigured: "Configured stores",
    activeStores: "Active stores",
    markets: "Available markets",
    integrationsTitle: "Integrations in one place",
    integrationsBody:
      "This view focuses on store identity and operating configuration. Connect and sync channels from Integrations.",
    integrationsHint: "Use Integrations in the sidebar to manage connections",
    sectionKicker: "WORKSPACE",
    sectionTitle: "Your stores",
    sectionBody: "Each card represents an independent operating market.",
    currency: "Currency",
    language: "Language",
    timezone: "Timezone",
    commerceDomain: "Commerce domain",
    noCommerceDomain: "No domain defined",
    active: "Active",
    inactive: "Suspended",
    configure: "Configure",
    delete: "Delete",
    createTitle: "Create new store",
    editTitle: "Configure store",
    createStepMarket: "Market",
    createStepDetails: "Operations",
    createStepIntegrations: "Integrations next",
    market: "Country / market",
    storeName: "Store name",
    commerceDomainHelp:
      "Optional. Save the Shopify domain as an identifier; complete the OAuth connection later in Integrations.",
    status: "Operating status",
    activeHelp: "The store will be available for operations and workspace selection.",
    inactiveHelp: "The store remains suspended and is excluded from active operations.",
    preview: "Market preview",
    nextStepNote:
      "Create the store first. Then connect Shopify, WhatsApp, suppliers or payments from the Integrations Hub.",
    emptyTitle: "Create your first store",
    emptyBody:
      "Start with your main operating market. You can add connections and automations afterwards.",
    dangerTitle: "Danger zone",
    dangerBody:
      "Closing your account disables access to every organization and store. This action cannot be undone.",
    closeAccount: "Close account",
    closeWarning:
      "This action is permanent. Your user account will be deleted and your access disabled.",
    closeLoss1: "You will lose access to every organization",
    closeLoss2: "Your current session will be disabled",
    closeLoss3: "You will not be able to recover your account",
    closeConfirm: 'Type "DELETE" to confirm.',
    deleteStoreTitle: "Delete store",
    deleteStoreBody: "You are about to delete",
    deleteStoreWarning:
      "This removes access to the store and may affect associated data. Continue only if you are sure.",
    planLimitTitle: "Store limit reached",
    planCurrent: "Current plan",
    understood: "Got it",
    confirmDeleteWord: "DELETE",
  },
  "pt-BR": {
    eyebrow: "OPERAÇÃO MULTILOJA",
    title: "Lojas",
    subtitle:
      "Configure cada mercado onde você opera. Conexões com Shopify, WhatsApp, fornecedores e pagamentos são gerenciadas separadamente em Integrações.",
    planUsage: "Uso do plano",
    storesConfigured: "Lojas configuradas",
    activeStores: "Lojas ativas",
    markets: "Mercados disponíveis",
    integrationsTitle: "Integrações em um só lugar",
    integrationsBody:
      "Esta tela foca na identidade e configuração operacional de cada loja. Conecte e sincronize canais em Integrações.",
    integrationsHint: "Use Integrações no menu lateral para gerenciar conexões",
    sectionKicker: "WORKSPACE",
    sectionTitle: "Suas lojas",
    sectionBody: "Cada cartão representa um mercado operacional independente.",
    currency: "Moeda",
    language: "Idioma",
    timezone: "Fuso horário",
    commerceDomain: "Domínio de comércio",
    noCommerceDomain: "Sem domínio definido",
    active: "Ativa",
    inactive: "Suspensa",
    configure: "Configurar",
    delete: "Excluir",
    createTitle: "Criar nova loja",
    editTitle: "Configurar loja",
    createStepMarket: "Mercado",
    createStepDetails: "Operação",
    createStepIntegrations: "Integrações depois",
    market: "País / mercado",
    storeName: "Nome da loja",
    commerceDomainHelp:
      "Opcional. Salve o domínio Shopify como identificador; conclua a conexão OAuth depois em Integrações.",
    status: "Status operacional",
    activeHelp: "A loja ficará disponível para operação e seleção no workspace.",
    inactiveHelp: "A loja fica suspensa e não participa da operação ativa.",
    preview: "Prévia do mercado",
    nextStepNote:
      "Crie a loja primeiro. Depois conecte Shopify, WhatsApp, fornecedores ou pagamentos no Hub de Integrações.",
    emptyTitle: "Crie sua primeira loja",
    emptyBody:
      "Comece pelo principal mercado da operação. Você poderá adicionar conexões e automações depois.",
    dangerTitle: "Zona de perigo",
    dangerBody:
      "Fechar sua conta desativa o acesso a todas as organizações e lojas. Esta ação é irreversível.",
    closeAccount: "Fechar conta",
    closeWarning:
      "Esta ação é permanente. Sua conta de usuário será excluída e seu acesso desativado.",
    closeLoss1: "Você perderá acesso a todas as organizações",
    closeLoss2: "Sua sessão atual será desativada",
    closeLoss3: "Você não poderá recuperar sua conta",
    closeConfirm: 'Digite "EXCLUIR" para confirmar.',
    deleteStoreTitle: "Excluir loja",
    deleteStoreBody: "Você está prestes a excluir",
    deleteStoreWarning:
      "Esta ação remove o acesso à loja e pode afetar dados associados. Continue somente se tiver certeza.",
    planLimitTitle: "Limite de lojas atingido",
    planCurrent: "Plano atual",
    understood: "Entendi",
    confirmDeleteWord: "EXCLUIR",
  },
};

function normalizeLocale(language: string): LocaleKey {
  if (language.toLowerCase().startsWith("pt")) return "pt-BR";
  if (language.toLowerCase().startsWith("en")) return "en";
  return "es";
}

export default function StoresPage({
  canWrite,
  onStoresChanged,
  onOpenPlans,
}: StoresPageProps) {
  const { t, i18n } = useTranslation();
  const locale = normalizeLocale(i18n.resolvedLanguage || i18n.language || "es");
  const copy = COPY[locale];

  const [stores, setStores] = useState<Store[]>([]);
  const [markets, setMarkets] = useState<Market[]>([]);
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [editingStore, setEditingStore] = useState<Store | null>(null);
  const [storeToDelete, setStoreToDelete] = useState<Store | null>(null);
  const [planLimitMessage, setPlanLimitMessage] = useState<string | null>(null);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [form, setForm] = useState<StoreForm>(EMPTY_FORM);

  async function loadData() {
    try {
      setLoading(true);
      setError("");

      const [storesResponse, marketsResponse, organizationResponse] = await Promise.all([
        getStoresForManagement(),
        getMarkets(),
        getCurrentOrganization(),
      ]);

      setStores(storesResponse.items);
      setMarkets(marketsResponse.items);
      setOrganization(organizationResponse);
    } catch (err) {
      console.error(err);
      setError(t("storesI18nLoadError"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  const selectedMarket = useMemo(
    () => markets.find((market) => market.country_code === form.country_code) || null,
    [markets, form.country_code],
  );

  const activeStores = useMemo(
    () => stores.filter((store) => store.active).length,
    [stores],
  );

  const planUsage = organization?.active_store_limit
    ? Math.min(100, (organization.active_stores / organization.active_store_limit) * 100)
    : 0;

  function openCreate() {
    const firstMarket = markets[0] || null;
    setEditingStore(null);
    setForm(
      firstMarket
        ? {
            name: "",
            country_code: firstMarket.country_code,
            currency: firstMarket.currency,
            timezone: firstMarket.default_timezone,
            default_language: firstMarket.default_language,
            shopify_domain: "",
            active: true,
          }
        : EMPTY_FORM,
    );
    setError("");
    setSuccess("");
    setModalOpen(true);
  }

  function openEdit(store: Store) {
    setEditingStore(store);
    setForm({
      name: store.name,
      country_code: store.country_code,
      currency: store.currency,
      timezone: store.timezone,
      default_language: store.default_language,
      shopify_domain: store.shopify_domain || "",
      active: store.active,
    });
    setError("");
    setSuccess("");
    setModalOpen(true);
  }

  function closeModal() {
    if (saving) return;
    setModalOpen(false);
    setEditingStore(null);
    setForm(EMPTY_FORM);
    setError("");
  }

  function changeMarket(countryCode: string) {
    const market = markets.find((item) => item.country_code === countryCode);
    if (!market) return;

    setForm((current) => ({
      ...current,
      country_code: market.country_code,
      currency: market.currency,
      timezone: market.default_timezone,
      default_language: market.default_language,
    }));
  }

  async function saveStore(event: React.FormEvent) {
    event.preventDefault();
    const name = form.name.trim();

    if (!name) {
      setError(t("storesI18nNameRequired"));
      return;
    }

    if (!form.country_code) {
      setError(t("storesI18nCountryRequired"));
      return;
    }

    try {
      setSaving(true);
      setError("");
      setSuccess("");

      if (editingStore) {
        await updateStore(editingStore.id, {
          name,
          currency: form.currency,
          timezone: form.timezone,
          default_language: form.default_language,
          shopify_domain: form.shopify_domain.trim() || null,
          active: form.active,
        });
        setSuccess(t("storesI18nUpdatedSuccess"));
      } else {
        await createStore({
          name,
          country_code: form.country_code,
          currency: form.currency,
          timezone: form.timezone,
          default_language: form.default_language,
          shopify_domain: form.shopify_domain.trim() || null,
          active: form.active,
        });
        setSuccess(t("storesI18nCreatedSuccess"));
      }

      await loadData();
      onStoresChanged?.();
      setModalOpen(false);
      setEditingStore(null);
      setForm(EMPTY_FORM);
    } catch (err: any) {
      console.error(err);
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail;

      if (status === 409) {
        setError("");
        setModalOpen(false);
        setEditingStore(null);
        setForm(EMPTY_FORM);
        setPlanLimitMessage(detail || t("storesI18nPlanLimitReached"));
        return;
      }

      setError(detail || t("storesI18nSaveError"));
    } finally {
      setSaving(false);
    }
  }

  async function confirmDeleteStore() {
    if (!storeToDelete) return;

    try {
      setSaving(true);
      setError("");
      setSuccess("");
      const storeName = storeToDelete.name;
      await deleteStore(storeToDelete.id);
      setStoreToDelete(null);
      setSuccess(t("storesI18nDeletedSuccess", { name: storeName }));
      await loadData();
      onStoresChanged?.();
    } catch (err: any) {
      console.error(err);
      setError(err?.response?.data?.detail || t("storesI18nDeleteError"));
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteAccount() {
    if (deleteConfirmText.trim() !== copy.confirmDeleteWord) {
      setDeleteError(copy.closeConfirm);
      return;
    }

    try {
      setDeleting(true);
      setDeleteError("");
      const { closeAccount } = await import("../services/account");
      await closeAccount();
      localStorage.clear();
      window.location.href = "/";
    } catch (err: any) {
      setDeleting(false);
      setDeleteError(
        err?.response?.data?.detail?.message ||
          err?.response?.data?.detail ||
          err?.message ||
          t("storesI18nDeleteAccountError") ||
          "Unable to close account.",
      );
    }
  }

  if (loading) {
    return (
      <div className="content stores-v2">
        <div className="stores-v2-loading">{t("storesI18nLoading")}</div>
      </div>
    );
  }

  return (
    <div className="content stores-v2">
      <section className="stores-v2-hero">
        <div className="stores-v2-hero-copy">
          <span className="stores-v2-eyebrow">
            <StoreIcon size={14} />
            {copy.eyebrow}
          </span>
          <h1>{copy.title}</h1>
          <p>{copy.subtitle}</p>
        </div>

        {canWrite && (
          <button type="button" className="stores-v2-primary" onClick={openCreate}>
            <Plus size={17} />
            {t("storesI18nNewStore")}
          </button>
        )}
      </section>

      {error && !modalOpen && !storeToDelete && (
        <div className="stores-v2-alert is-error">
          <AlertTriangle size={16} />
          {error}
        </div>
      )}

      {success && (
        <div className="stores-v2-alert is-success">
          <Check size={16} />
          {success}
        </div>
      )}

      <section className="stores-v2-stats" aria-label="Store overview">
        <article className="stores-v2-stat">
          <div className="stores-v2-stat-icon"><StoreIcon size={18} /></div>
          <div><strong>{stores.length}</strong><span>{copy.storesConfigured}</span></div>
        </article>
        <article className="stores-v2-stat">
          <div className="stores-v2-stat-icon"><Check size={18} /></div>
          <div><strong>{activeStores}</strong><span>{copy.activeStores}</span></div>
        </article>
        <article className="stores-v2-stat">
          <div className="stores-v2-stat-icon"><Globe2 size={18} /></div>
          <div><strong>{markets.length}</strong><span>{copy.markets}</span></div>
        </article>
      </section>

      <section className="stores-v2-overview">
        {organization ? (
          <article className="stores-v2-plan">
            <div className="stores-v2-plan-top">
              <div>
                <span className="stores-v2-plan-label">{copy.planUsage}</span>
                <h2>{organization.plan_name}</h2>
              </div>
              <div className="stores-v2-plan-count">
                <strong>{organization.active_stores}</strong>
                <span>/ {organization.active_store_limit}</span>
              </div>
            </div>
            <div className="stores-v2-progress" aria-hidden="true">
              <span style={{ width: `${planUsage}%` }} />
            </div>
            <div className="stores-v2-plan-meta">
              <span>
                {organization.active_stores >= organization.active_store_limit
                  ? t("storesI18nPlanLimitReached")
                  : t(
                      organization.active_store_limit - organization.active_stores === 1
                        ? "storesI18nSlotAvailable"
                        : "storesI18nSlotsAvailable",
                      { count: organization.active_store_limit - organization.active_stores },
                    )}
              </span>
              <strong>{organization.plan_name}</strong>
            </div>
          </article>
        ) : <div />}

        <article className="stores-v2-integrations-note">
          <div>
            <div className="stores-v2-integrations-icon"><Plug size={18} /></div>
            <h3>{copy.integrationsTitle}</h3>
            <p>{copy.integrationsBody}</p>
          </div>
          <span className="stores-v2-integrations-hint">
            <Plug size={14} />
            {copy.integrationsHint}
          </span>
        </article>
      </section>

      <section>
        <div className="stores-v2-section-heading">
          <div>
            <span className="stores-v2-section-kicker">{copy.sectionKicker}</span>
            <h2>{copy.sectionTitle}</h2>
            <p>{copy.sectionBody}</p>
          </div>
        </div>
      </section>

      {stores.length === 0 ? (
        <section className="stores-v2-empty">
          <div className="stores-v2-empty-icon"><StoreIcon size={26} /></div>
          <h3>{copy.emptyTitle}</h3>
          <p>{copy.emptyBody}</p>
          {canWrite && (
            <button type="button" className="stores-v2-primary" onClick={openCreate}>
              <Plus size={17} />
              {t("storesI18nCreateFirstStore")}
            </button>
          )}
        </section>
      ) : (
        <section className="stores-v2-grid">
          {stores.map((store) => (
            <article
              key={store.id}
              className={`stores-v2-card ${store.active ? "" : "is-inactive"}`}
            >
              <div className="stores-v2-card-header">
                <div className="stores-v2-identity">
                  <div className="stores-v2-flag">{getCountryFlag(store.country_code)}</div>
                  <div>
                    <h3>{store.name}</h3>
                    <span>{store.country_code} · {store.currency}</span>
                  </div>
                </div>
                <span
                  className={`stores-v2-status ${store.active ? "is-active" : "is-inactive"}`}
                  data-short-label={store.active ? copy.active : copy.inactive}
                >
                  {store.active ? copy.active : copy.inactive}
                </span>
              </div>

              <div className="stores-v2-card-body">
                <div className="stores-v2-detail">
                  <CircleDollarSign size={15} />
                  <div><span>{copy.currency}</span><strong>{store.currency}</strong></div>
                </div>
                <div className="stores-v2-detail">
                  <Languages size={15} />
                  <div><span>{copy.language}</span><strong>{getLanguageName(store.default_language)}</strong></div>
                </div>
                <div className="stores-v2-detail">
                  <Clock3 size={15} />
                  <div><span>{copy.timezone}</span><strong>{store.timezone}</strong></div>
                </div>
                <div className="stores-v2-detail">
                  <Globe2 size={15} />
                  <div><span>{copy.market}</span><strong>{store.country_code}</strong></div>
                </div>
              </div>

              <div className="stores-v2-commerce-domain">
                <span>{copy.commerceDomain}</span>
                <strong>{store.shopify_domain || copy.noCommerceDomain}</strong>
              </div>

              {canWrite && (
                <div className="stores-v2-card-actions">
                  <button type="button" className="stores-v2-card-action" onClick={() => openEdit(store)}>
                    <Pencil size={14} />
                    {copy.configure}
                  </button>
                  <button
                    type="button"
                    className="stores-v2-card-action is-danger"
                    onClick={() => {
                      setError("");
                      setSuccess("");
                      setStoreToDelete(store);
                    }}
                  >
                    <Trash2 size={14} />
                    {copy.delete}
                  </button>
                </div>
              )}
            </article>
          ))}
        </section>
      )}

      <section className="stores-v2-danger-zone">
        <div className="stores-v2-danger-header">
          <AlertTriangle size={18} />
          <h3>{copy.dangerTitle}</h3>
        </div>
        <p>{copy.dangerBody}</p>
        <button
          type="button"
          className="stores-v2-danger"
          onClick={() => {
            setDeleteConfirmOpen(true);
            setDeleteConfirmText("");
            setDeleteError("");
          }}
        >
          {copy.closeAccount}
        </button>
      </section>

      {modalOpen && (
        <div
          className="stores-v2-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeModal();
          }}
        >
          <form className="stores-v2-modal" onSubmit={saveStore}>
            <div className="stores-v2-modal-header">
              <div>
                <span className="stores-v2-modal-kicker">DIAGLOB · STORES</span>
                <h2>{editingStore ? copy.editTitle : copy.createTitle}</h2>
              </div>
              <button
                type="button"
                className="stores-v2-icon-button"
                onClick={closeModal}
                disabled={saving}
                aria-label={t("storesI18nCancel")}
              >
                <X size={18} />
              </button>
            </div>

            {!editingStore && (
              <div className="stores-v2-onboarding" aria-label="Store onboarding">
                <div className="stores-v2-onboarding-step"><strong>1</strong><span>{copy.createStepMarket}</span></div>
                <div className="stores-v2-onboarding-step"><strong>2</strong><span>{copy.createStepDetails}</span></div>
                <div className="stores-v2-onboarding-step is-next"><strong>3</strong><span>{copy.createStepIntegrations}</span></div>
              </div>
            )}

            {error && (
              <div className="stores-v2-alert is-error" style={{ margin: "16px 22px 0" }}>
                <AlertTriangle size={16} />
                {error}
              </div>
            )}

            <div className="stores-v2-form">
              <label className="stores-v2-field is-full">
                <span className="stores-v2-field-label">{copy.market}</span>
                <select
                  value={form.country_code}
                  onChange={(event) => changeMarket(event.target.value)}
                  disabled={Boolean(editingStore)}
                >
                  <option value="">{t("storesI18nSelectCountry")}</option>
                  {[...markets]
                    .sort((a, b) => a.country_name.localeCompare(b.country_name, locale, { sensitivity: "base" }))
                    .map((market) => (
                      <option key={market.country_code} value={market.country_code}>
                        {getCountryFlag(market.country_code)} {market.country_name}
                      </option>
                    ))}
                </select>
                {editingStore && <small>{t("storesI18nMarketLockedHelp")}</small>}
              </label>

              <label className="stores-v2-field is-full">
                <span className="stores-v2-field-label">{copy.storeName}</span>
                <input
                  value={form.name}
                  onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                  placeholder={t("storesI18nNamePlaceholder")}
                  autoFocus
                />
              </label>

              <label className="stores-v2-field">
                <span className="stores-v2-field-label">{copy.currency}</span>
                <select
                  value={form.currency}
                  onChange={(event) => setForm((current) => ({ ...current, currency: event.target.value }))}
                >
                  {(selectedMarket?.supported_currencies ||
                    (selectedMarket ? [selectedMarket.currency] : [form.currency].filter(Boolean)))
                    .map((currency) => <option key={currency} value={currency}>{currency}</option>)}
                </select>
              </label>

              <label className="stores-v2-field">
                <span className="stores-v2-field-label">{copy.language}</span>
                <select
                  value={form.default_language}
                  onChange={(event) => setForm((current) => ({ ...current, default_language: event.target.value }))}
                >
                  {(selectedMarket?.languages || [form.default_language].filter(Boolean))
                    .map((language) => (
                      <option key={language} value={language}>{getLanguageName(language)}</option>
                    ))}
                </select>
              </label>

              <label className="stores-v2-field is-full">
                <span className="stores-v2-field-label">{copy.timezone}</span>
                <input
                  value={form.timezone}
                  onChange={(event) => setForm((current) => ({ ...current, timezone: event.target.value }))}
                  placeholder="America/Bogota"
                />
              </label>

              <label className="stores-v2-field is-full">
                <span className="stores-v2-field-label">{copy.commerceDomain}</span>
                <input
                  value={form.shopify_domain}
                  onChange={(event) => setForm((current) => ({ ...current, shopify_domain: event.target.value }))}
                  placeholder="mitienda.myshopify.com"
                />
                <small>{copy.commerceDomainHelp}</small>
              </label>

              <div className="stores-v2-toggle-row">
                <label>
                  <input
                    type="checkbox"
                    checked={form.active}
                    onChange={(event) => setForm((current) => ({ ...current, active: event.target.checked }))}
                  />
                  {copy.status}
                </label>
                <small>{form.active ? copy.activeHelp : copy.inactiveHelp}</small>
              </div>

              <div className="stores-v2-market-preview">
                <div className="stores-v2-market-preview-flag">
                  {form.country_code ? getCountryFlag(form.country_code) : "🌎"}
                </div>
                <div>
                  <span className="stores-v2-field-label">{copy.preview}</span>
                  <strong>{selectedMarket?.country_name || editingStore?.name || copy.market}</strong>
                  <span>
                    {form.currency || "—"} · {form.default_language ? getLanguageName(form.default_language) : "—"} · {form.timezone || "—"}
                  </span>
                </div>
              </div>

              {!editingStore && (
                <div className="stores-v2-form-note">
                  <Plug size={15} />
                  <span>{copy.nextStepNote}</span>
                </div>
              )}
            </div>

            <div className="stores-v2-modal-actions">
              <button type="button" className="stores-v2-secondary" onClick={closeModal} disabled={saving}>
                {t("storesI18nCancel")}
              </button>
              <button type="submit" className="stores-v2-primary" disabled={saving}>
                {saving
                  ? t("storesI18nSaving")
                  : editingStore
                    ? t("storesI18nSaveChanges")
                    : t("storesI18nCreateStore")}
              </button>
            </div>
          </form>
        </div>
      )}

      {storeToDelete && (
        <div
          className="stores-v2-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !saving) setStoreToDelete(null);
          }}
        >
          <div className="stores-v2-modal" role="dialog" aria-modal="true" aria-labelledby="delete-store-title">
            <div className="stores-v2-modal-header">
              <div>
                <span className="stores-v2-modal-kicker">DIAGLOB · STORES</span>
                <h2 id="delete-store-title">{copy.deleteStoreTitle}</h2>
              </div>
              <button type="button" className="stores-v2-icon-button" onClick={() => setStoreToDelete(null)} disabled={saving}>
                <X size={18} />
              </button>
            </div>
            <div className="stores-v2-confirm-copy">
              <p>{copy.deleteStoreBody} <strong>{storeToDelete.name}</strong>.</p>
              <p>{copy.deleteStoreWarning}</p>
              {error && (
                <div className="stores-v2-alert is-error" style={{ marginTop: 14 }}>
                  <AlertTriangle size={16} />
                  {error}
                </div>
              )}
            </div>
            <div className="stores-v2-modal-actions">
              <button type="button" className="stores-v2-secondary" onClick={() => setStoreToDelete(null)} disabled={saving}>
                {t("storesI18nCancel")}
              </button>
              <button type="button" className="stores-v2-danger" onClick={() => void confirmDeleteStore()} disabled={saving}>
                <Trash2 size={15} />
                {saving ? t("storesI18nDeleting") : t("storesI18nConfirmDelete")}
              </button>
            </div>
          </div>
        </div>
      )}

      {planLimitMessage && (
        <div
          className="stores-v2-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setPlanLimitMessage(null);
          }}
        >
          <div className="stores-v2-modal" role="dialog" aria-modal="true" aria-labelledby="plan-limit-title">
            <div className="stores-v2-modal-header">
              <div>
                <span className="stores-v2-modal-kicker">{copy.planUsage}</span>
                <h2 id="plan-limit-title">{copy.planLimitTitle}</h2>
              </div>
              <button type="button" className="stores-v2-icon-button" onClick={() => setPlanLimitMessage(null)}>
                <X size={18} />
              </button>
            </div>
            <div className="stores-v2-confirm-copy">
              <p>{planLimitMessage}</p>
              {organization && (
                <ul className="stores-v2-confirm-list">
                  <li>{copy.planCurrent}: <strong>{organization.plan_name}</strong></li>
                  <li>{copy.activeStores}: <strong>{organization.active_stores} / {organization.active_store_limit}</strong></li>
                </ul>
              )}
            </div>
            <div className="stores-v2-modal-actions">
              <button type="button" className="stores-v2-secondary" onClick={() => setPlanLimitMessage(null)}>
                {copy.understood}
              </button>
              {onOpenPlans && (
                <button
                  type="button"
                  className="stores-v2-primary"
                  onClick={() => {
                    setPlanLimitMessage(null);
                    onOpenPlans();
                  }}
                >
                  {t("storesI18nViewPlans")}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {deleteConfirmOpen && (
        <div
          className="stores-v2-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !deleting) setDeleteConfirmOpen(false);
          }}
        >
          <div className="stores-v2-modal" role="dialog" aria-modal="true" aria-labelledby="close-account-title">
            <div className="stores-v2-modal-header">
              <div>
                <span className="stores-v2-modal-kicker">{copy.dangerTitle}</span>
                <h2 id="close-account-title">{copy.closeAccount}</h2>
              </div>
              <button type="button" className="stores-v2-icon-button" onClick={() => setDeleteConfirmOpen(false)} disabled={deleting}>
                <X size={18} />
              </button>
            </div>
            <div className="stores-v2-confirm-copy">
              <p>{copy.closeWarning}</p>
              <ul className="stores-v2-confirm-list">
                <li>{copy.closeLoss1}</li>
                <li>{copy.closeLoss2}</li>
                <li>{copy.closeLoss3}</li>
              </ul>
              <p><strong>{copy.closeConfirm}</strong></p>
            </div>
            <input
              type="text"
              className="stores-v2-confirm-input"
              value={deleteConfirmText}
              onChange={(event) => setDeleteConfirmText(event.target.value)}
              placeholder={copy.confirmDeleteWord}
              autoFocus
            />
            {deleteError && (
              <div className="stores-v2-alert is-error" style={{ margin: "12px 22px 0" }}>
                <AlertTriangle size={16} />
                {deleteError}
              </div>
            )}
            <div className="stores-v2-modal-actions">
              <button type="button" className="stores-v2-secondary" onClick={() => setDeleteConfirmOpen(false)} disabled={deleting}>
                {t("storesI18nCancel")}
              </button>
              <button
                type="button"
                className="stores-v2-danger"
                onClick={() => void handleDeleteAccount()}
                disabled={deleting || deleteConfirmText.trim() !== copy.confirmDeleteWord}
              >
                <Trash2 size={15} />
                {deleting ? t("storesI18nSaving") : copy.closeAccount}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
