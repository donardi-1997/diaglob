import { useTranslation } from "react-i18next";
import {
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  Check,
  CircleDollarSign,
  Clock3,
  Globe2,
  Languages,
  Pencil,
  Plus,
  ShoppingBag,
  Store as StoreIcon,
  Trash2,
  AlertTriangle,
  X,
} from "lucide-react";

import {
  createStore,
  deleteStore,
  getStoresForManagement,
  updateStore,
  type Store,
} from "../services/stores";

import {
  getMarkets,
  type Market,
} from "../services/markets";

import {
  getCurrentOrganization,
  type Organization,
} from "../services/organizations";

import {
  getCountryFlag,
  getLanguageName,
} from "../utils/markets";

import StoreIntegrations from "../components/StoreIntegrations";


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


const EMPTY_FORM: StoreForm = {
  name: "",
  country_code: "",
  currency: "",
  timezone: "",
  default_language: "",
  shopify_domain: "",
  active: true,
};


export default function StoresPage({
  canWrite,
  onStoresChanged,
  onOpenPlans,
}: StoresPageProps) {
  const { t } = useTranslation();
  const [stores, setStores] =
    useState<Store[]>([]);

  const [markets, setMarkets] =
    useState<Market[]>([]);

  const [organization, setOrganization] =
    useState<Organization | null>(null);

  const [loading, setLoading] =
    useState(true);

  const [saving, setSaving] =
    useState(false);

  const [error, setError] =
    useState("");

  const [success, setSuccess] =
    useState("");

  const [modalOpen, setModalOpen] =
    useState(false);

  const [editingStore, setEditingStore] =
    useState<Store | null>(null);

  const [storeToDelete, setStoreToDelete] =
    useState<Store | null>(null);

  const [planLimitMessage, setPlanLimitMessage] =
    useState<string | null>(null);

  const [deleteConfirmOpen, setDeleteConfirmOpen] =
    useState(false);

  const [deleteConfirmText, setDeleteConfirmText] =
    useState("");

  const [deleting, setDeleting] =
    useState(false);

  const [deleteError, setDeleteError] =
    useState("");

  const [form, setForm] =
    useState<StoreForm>(EMPTY_FORM);


  async function handleDeleteAccount() {
    const confirmLabel = t("landingCtaFinalButton") === "Create account" ? "DELETE" : "ELIMINAR";
    if (deleteConfirmText.trim() !== confirmLabel) {
      setDeleteError(
        t("storesI18nDeleteAccountConfirmError") ||
          `Escribe "${confirmLabel}" para confirmar.`
      );
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
          "No pudimos cerrar tu cuenta. Intenta nuevamente."
      );
    }
  }


  async function loadData() {
    try {
      setLoading(true);
      setError("");

      const [
        storesResponse,
        marketsResponse,
        organizationResponse,
      ] = await Promise.all([
        getStoresForManagement(),
        getMarkets(),
        getCurrentOrganization(),
      ]);

      setStores(
        storesResponse.items,
      );

      setMarkets(
        marketsResponse.items,
      );

      setOrganization(
        organizationResponse,
      );
    } catch (err) {
      console.error(err);

      setError(
        t("storesI18nLoadError"),
      );
    } finally {
      setLoading(false);
    }
  }


  useEffect(() => {
    loadData();
  }, []);


  const selectedMarket =
    useMemo(
      () =>
        markets.find(
          (market) =>
            market.country_code ===
            form.country_code,
        ) || null,
      [
        markets,
        form.country_code,
      ],
    );


  function openCreate() {
    const firstMarket =
      markets[0] || null;

    setEditingStore(null);

    setForm(
      firstMarket
        ? {
            name: "",
            country_code:
              firstMarket.country_code,
            currency:
              firstMarket.currency,
            timezone:
              firstMarket.default_timezone,
            default_language:
              firstMarket.default_language,
            shopify_domain: "",
            active: true,
                    }
        : EMPTY_FORM,
    );

    setError("");
    setSuccess("");
    setModalOpen(true);
  }


  function openEdit(
    store: Store,
  ) {
    setEditingStore(store);

    setForm({
      name:
        store.name,

      country_code:
        store.country_code,

      currency:
        store.currency,

      timezone:
        store.timezone,

      default_language:
        store.default_language,

      shopify_domain:
        store.shopify_domain || "",

      active:
        store.active,

    });

    setError("");
    setSuccess("");
    setModalOpen(true);
  }


  function closeModal() {
    if (saving) {
      return;
    }

    setModalOpen(false);
    setEditingStore(null);
    setForm(EMPTY_FORM);
  }


  function changeMarket(
    countryCode: string,
  ) {
    const market =
      markets.find(
        (item) =>
          item.country_code ===
          countryCode,
      );

    if (!market) {
      return;
    }

    setForm(
      (current) => ({
        ...current,

        country_code:
          market.country_code,

        currency:
          market.currency,

        timezone:
          market.default_timezone,

        default_language:
          market.default_language,
      }),
    );
  }


  function requestDeleteStore(
    store: Store,
  ) {
    setError("");
    setSuccess("");
    setStoreToDelete(store);
  }


  function cancelDeleteStore() {
    if (saving) {
      return;
    }

    setStoreToDelete(null);
  }


  async function confirmDeleteStore() {
    if (!storeToDelete) {
      return;
    }

    try {
      setSaving(true);
      setError("");
      setSuccess("");

      const storeName =
        storeToDelete.name;

      await deleteStore(
        storeToDelete.id,
      );

      setStoreToDelete(null);

      setSuccess(
        t("storesI18nDeletedSuccess", { name: storeName }),
      );

      await loadData();

      onStoresChanged?.();

    } catch (err: any) {
      console.error(err);

      setError(
        err?.response?.data?.detail
        || t("storesI18nDeleteError"),
      );
    } finally {
      setSaving(false);
    }
  }


  async function saveStore(
    event: React.FormEvent,
  ) {
    event.preventDefault();

    const name =
      form.name.trim();

    if (!name) {
      setError(
        t("storesI18nNameRequired"),
      );

      return;
    }

    if (!form.country_code) {
      setError(
        t("storesI18nCountryRequired"),
      );

      return;
    }

    try {
      setSaving(true);
      setError("");
      setSuccess("");

      if (editingStore) {
        await updateStore(
          editingStore.id,
          {
            name,

            currency:
              form.currency,

            timezone:
              form.timezone,

            default_language:
              form.default_language,

            shopify_domain:
              form.shopify_domain.trim()
              || null,

            active:
              form.active,

          },
        );

        setSuccess(
          t("storesI18nUpdatedSuccess"),
        );
      } else {
        await createStore({
          name,

          country_code:
            form.country_code,

          currency:
            form.currency,

          timezone:
            form.timezone,

          default_language:
            form.default_language,

          shopify_domain:
            form.shopify_domain.trim()
            || null,

          active:
            form.active,
        });

        setSuccess(
          t("storesI18nCreatedSuccess"),
        );
      }

      await loadData();

      onStoresChanged?.();

      setModalOpen(false);
      setEditingStore(null);
      setForm(EMPTY_FORM);
    } catch (err: any) {
      console.error(err);

      const status =
        err?.response?.status;

      const detail =
        err?.response?.data?.detail;

      if (status === 409) {
        setError("");

        // Cierra primero el modal de configuración
        // para que el popup del límite quede solo.
        setModalOpen(false);
        setEditingStore(null);
        setForm(EMPTY_FORM);

        setPlanLimitMessage(
          detail
          || t("storesI18nPlanLimitReached"),
        );

        return;
      }

      setError(
        detail
        || t("storesI18nSaveError"),
      );
    } finally {
      setSaving(false);
    }
  }


  if (loading) {
    return (
      <div className="content">
        <div className="stores-loading">
          {t("storesI18nLoading")}
        </div>
      </div>
    );
  }


  return (
    <div className="content stores-page">
      <section className="page-heading stores-heading">
        <div>
          <span className="eyebrow">
            DIAGLOB COMMERCE
          </span>

          <h1>
            {t("storesI18nTitle")}
          </h1>

          <p>
            Administra las tiendas,
            países, monedas e integraciones
            de tu organización.
          </p>
        </div>

        {canWrite && (
          <button
            className="primary-button"
            onClick={openCreate}
          >
            <Plus size={18} />
            {t("storesI18nNewStore")}
          </button>
        )}
      </section>


      {error && !modalOpen && (
        <div className="stores-alert error">
          {error}
        </div>
      )}

      {success && (
        <div className="stores-alert success">
          <Check size={17} />
          {success}
        </div>
      )}


      {organization && (
        <section className="store-plan-card">
          <div className="store-plan-top">
            <div>
              <span className="eyebrow">
                PLAN {organization.plan_name.toUpperCase()}
              </span>

              <h2>
                {t("storesI18nActiveStores")}
              </h2>
            </div>

            <div className="store-plan-count">
              <strong>
                {organization.active_stores}
              </strong>

              <span>
                / {organization.active_store_limit}
              </span>
            </div>
          </div>

          <div className="store-plan-progress">
            <div
              className="store-plan-progress-bar"
              style={{
                width: `${
                  organization.active_store_limit > 0
                    ? Math.min(
                        100,
                        (
                          organization.active_stores /
                          organization.active_store_limit
                        ) * 100,
                      )
                    : 0
                }%`,
              }}
            />
          </div>

          <div className="store-plan-footer">
            <span>
              {organization.active_stores >=
              organization.active_store_limit
                ? t("storesI18nPlanLimitReached")
                : t(
                    organization.active_store_limit -
                      organization.active_stores === 1
                      ? "storesI18nSlotAvailable"
                      : "storesI18nSlotsAvailable",
                    {
                      count:
                        organization.active_store_limit -
                        organization.active_stores,
                    },
                  )}
            </span>

            <strong>
              {organization.plan_name}
            </strong>
          </div>
        </section>
      )}


      <div className="stores-summary">
        <div className="store-summary-card">
          <StoreIcon size={20} />

          <div>
            <strong>
              {stores.length}
            </strong>

            <span>
              {t("storesI18nStores")}
            </span>
          </div>
        </div>

        <div className="store-summary-card">
          <Globe2 size={20} />

          <div>
            <strong>
              {markets.length}
            </strong>

            <span>
              {t("storesI18nAvailableMarkets")}
            </span>
          </div>
        </div>

        <div className="store-summary-card">
          <Check size={20} />

          <div>
            <strong>
              {
                stores.filter(
                  (store) =>
                    store.active,
                ).length
              }
            </strong>

            <span>
              {t("storesI18nActiveStores")}
            </span>
          </div>
        </div>
      </div>


      {stores.length === 0 ? (
        <div className="stores-empty">
          <div className="stores-empty-icon">
            <StoreIcon size={30} />
          </div>

          <h3>
            {t("storesI18nNoStores")}
          </h3>

          <p>
            {t("storesI18nEmptyHelp")}
          </p>

          {canWrite && (
            <button
              className="primary-button"
              onClick={openCreate}
            >
              <Plus size={18} />
              {t("storesI18nCreateFirstStore")}
            </button>
          )}
        </div>
      ) : (
        <div className="stores-grid">
          {stores.map(
            (store) => (
              <article
                key={store.id}
                className="store-management-card"
              >
                <div className="store-card-top">
                  <div className="store-identity">
                    <div className="store-country-flag">
                      {getCountryFlag(
                        store.country_code,
                      )}
                    </div>

                    <div>
                      <h3>
                        {store.name}
                      </h3>

                      <span>
                        {
                          store.country_code
                        }
                        {" · "}
                        {store.currency}
                      </span>
                    </div>
                  </div>

                  <span
                    className={
                      store.active
                        ? "store-status active"
                        : "store-status inactive"
                    }
                  >
                    {store.active
                      ? t("storesI18nActive")
                      : t("storesI18nSuspended")}
                  </span>
                </div>


                <div className="store-card-details">
                  <div>
                    <CircleDollarSign
                      size={16}
                    />

                    <span>
                      Moneda
                    </span>

                    <strong>
                      {store.currency}
                    </strong>
                  </div>

                  <div>
                    <Languages
                      size={16}
                    />

                    <span>
                      Idioma
                    </span>

                    <strong>
                      {getLanguageName(
                        store.default_language,
                      )}
                    </strong>
                  </div>

                  <div>
                    <Clock3
                      size={16}
                    />

                    <span>
                      Zona horaria
                    </span>

                    <strong>
                      {store.timezone}
                    </strong>
                  </div>

                  <div>
                    <ShoppingBag
                      size={16}
                    />

                    <span>
                      Shopify
                    </span>

                    <strong>
                      {
                        store.shopify_domain
                        || t("storesI18nNotConnected")
                      }
                    </strong>
                  </div>
                </div>


                <StoreIntegrations
                  storeId={store.id}
                  shopDomain={
                    store.shopify_domain
                  }
                  canWrite={canWrite}
                />


                {canWrite && (
                  <div className="store-card-actions">
                    <button
                      className="store-edit-button"
                      onClick={() =>
                        openEdit(store)
                      }
                    >
                      <Pencil size={16} />
                      Configurar
                    </button>

                    <button
                      className="store-delete-button"
                      onClick={() =>
                        requestDeleteStore(
                          store
                        )
                      }
                    >
                      <Trash2 size={16} />
                      {t("storesI18nDelete")}
                    </button>
                  </div>
                )}
              </article>
            ),
          )}
        </div>
      )}


      <section className="danger-zone">
        <div className="danger-zone-header">
          <AlertTriangle size={20} />
          <h3>{t("storesI18nDangerZone") || "Zona de peligro"}</h3>
        </div>
        <p className="danger-zone-description">
          {t("storesI18nDeleteAccountDescription") ||
            "Cerrar tu cuenta desactivará tu acceso a todas las organizaciones y tiendas. Esta acción es irreversible."}
        </p>
        <button
          className="danger-button"
          onClick={() => {
            setDeleteConfirmOpen(true);
            setDeleteConfirmText("");
            setDeleteError("");
          }}
        >
          {t("storesI18nDeleteAccount") || "Cerrar cuenta"}
        </button>
      </section>

      {deleteConfirmOpen && (
        <div
          className="stores-modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              setDeleteConfirmOpen(false);
            }
          }}
        >
          <div className="management-modal" role="dialog" aria-modal="true">
            <div className="management-modal-header">
              <h2>{t("storesI18nDeleteAccount") || "Cerrar cuenta"}</h2>
              <button
                type="button"
                className="modal-close"
                onClick={() => setDeleteConfirmOpen(false)}
              >
                <X size={18} />
              </button>
            </div>

            <div className="management-modal-body">
              <p>
                {t("storesI18nDeleteAccountWarning") ||
                  "Esta acción es permanente. Se eliminará tu cuenta de usuario y se desactivará tu acceso."}
              </p>
              <ul className="danger-zone-list">
                <li>{t("storesI18nDeleteAccountLoss1") || "Perderás acceso a todas tus organizaciones"}</li>
                <li>{t("storesI18nDeleteAccountLoss2") || "Se desactivará tu sesión actual"}</li>
                <li>{t("storesI18nDeleteAccountLoss3") || "No podrás recuperar tu cuenta"}</li>
              </ul>

              <label className="danger-zone-confirm-label">
                {t("storesI18nDeleteAccountTypeConfirm") ||
                  'Escribe ELIMINAR para confirmar:'}
                <input
                  type="text"
                  value={deleteConfirmText}
                  onChange={(e) => setDeleteConfirmText(e.target.value)}
                  placeholder={t("landingCtaFinalButton") === "Create account" ? "DELETE" : "ELIMINAR"}
                  className="danger-zone-confirm-input"
                  autoFocus
                />
              </label>

              {deleteError && (
                <div className="login-error">{deleteError}</div>
              )}
            </div>

            <div className="management-modal-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={() => setDeleteConfirmOpen(false)}
                disabled={deleting}
              >
                {t("storesI18nCancel")}
              </button>
              <button
                type="button"
                className="danger-button"
                onClick={handleDeleteAccount}
                disabled={deleting || deleteConfirmText.trim() !== (t("landingCtaFinalButton") === "Create account" ? "DELETE" : "ELIMINAR")}
              >
                {deleting
                  ? t("storesI18nSaving") || "Procesando..."
                  : t("storesI18nDeleteAccount") || "Cerrar cuenta"}
              </button>
            </div>
          </div>
        </div>
      )}


      {planLimitMessage && (
        <div
          className="stores-modal-backdrop"
          onMouseDown={(event) => {
            if (
              event.target ===
              event.currentTarget
            ) {
              setPlanLimitMessage(null);
            }
          }}
        >
          <div
            className="plan-limit-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="plan-limit-title"
          >
            <div className="plan-limit-icon">
              <StoreIcon size={27} />
            </div>

            <div className="plan-limit-copy">
              <span className="eyebrow">
                {t("storesI18nPlanLimitEyebrow")}
              </span>

              <h2 id="plan-limit-title">
                Límite de tiendas alcanzado
              </h2>

              <p>
                {planLimitMessage}
              </p>
            </div>

            {organization && (
              <div className="plan-limit-usage">
                <div>
                  <span>
                    Plan actual
                  </span>

                  <strong>
                    {organization.plan_name}
                  </strong>
                </div>

                <div>
                  <span>
                    {t("storesI18nActiveStores")}
                  </span>

                  <strong>
                    {organization.active_stores}
                    {" / "}
                    {organization.active_store_limit}
                  </strong>
                </div>
              </div>
            )}

            <div className="plan-limit-note">
              {t("storesI18nPlanLimitHelp")}
            </div>

            <div className="plan-limit-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={() =>
                  setPlanLimitMessage(null)
                }
              >
                Entendido
              </button>

              <button
                type="button"
                className="primary-button"
                onClick={() => {
                  setPlanLimitMessage(null);
                  onOpenPlans?.();
                }}
              >
                {t("storesI18nViewPlans")}
              </button>
            </div>
          </div>
        </div>
      )}


      {storeToDelete && (
        <div
          className="stores-modal-backdrop"
          onMouseDown={(event) => {
            if (
              event.target ===
              event.currentTarget
            ) {
              cancelDeleteStore();
            }
          }}
        >
          <div
            className="store-delete-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-store-title"
          >
            <div className="store-delete-modal-icon">
              <Trash2 size={26} />
            </div>

            <div className="store-delete-modal-copy">
              <span className="eyebrow">
                {t("storesI18nConfirmDeleteEyebrow")}
              </span>

              <h2 id="delete-store-title">
                {t("storesI18nDeleteStoreTitle")}
              </h2>

              <p>
                {t("storesI18nAboutToDelete")}
                <strong>
                  {" "}
                  {storeToDelete.name}
                </strong>.
              </p>

              <p className="store-delete-warning">
                {t("storesI18nDeleteWarning")}
              </p>
            </div>

            {error && (
              <div className="stores-alert error">
                {error}
              </div>
            )}

            <div className="store-delete-modal-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={cancelDeleteStore}
                disabled={saving}
              >
                {t("storesI18nCancel")}
              </button>

              <button
                type="button"
                className="store-delete-confirm-button"
                onClick={confirmDeleteStore}
                disabled={saving}
              >
                <Trash2 size={16} />

                {saving
                  ? t("storesI18nDeleting")
                  : t("storesI18nConfirmDelete")}
              </button>
            </div>
          </div>
        </div>
      )}


      {modalOpen && (
        <div
          className="stores-modal-backdrop"
          onMouseDown={
            (event) => {
              if (
                event.target ===
                event.currentTarget
              ) {
                closeModal();
              }
            }
          }
        >
          <form
            className="stores-modal"
            onSubmit={saveStore}
          >
            <div className="stores-modal-header">
              <div>
                <span className="eyebrow">
                  DIAGLOB
                </span>

                <h2>
                  {editingStore
                    ? t("storesI18nConfigureStore")
                    : t("storesI18nNewStore")}
                </h2>
              </div>

              <button
                type="button"
                className="stores-modal-close"
                onClick={closeModal}
                disabled={saving}
              >
                <X size={19} />
              </button>
            </div>


            {error && (
              <div className="stores-alert error">
                {error}
              </div>
            )}


            <div className="stores-form-grid">
              <label className="stores-form-field full">
                <span>
                  {t("storesI18nCountryMarket")}
                </span>

                <select
                  value={
                    form.country_code
                  }
                  onChange={
                    (event) =>
                      changeMarket(
                        event.target.value,
                      )
                  }
                  disabled={
                    Boolean(
                      editingStore
                    )
                  }
                >
                  <option value="">
                    {t("storesI18nSelectCountry")}
                  </option>

                  {[...markets]
                    .sort(
                      (a, b) =>
                        a.country_name.localeCompare(
                          b.country_name,
                          "es",
                          {
                            sensitivity: "base",
                          },
                        ),
                    )
                    .map(
                      (market) => (
                        <option
                          key={
                            market.country_code
                          }
                          value={
                            market.country_code
                          }
                        >
                          {getCountryFlag(
                            market.country_code,
                          )}
                          {" "}
                          {
                            market.country_name
                          }
                        </option>
                      ),
                    )}
                </select>

                {editingStore && (
                  <small>
                    {t("storesI18nMarketLockedHelp")}
                  </small>
                )}
              </label>


              <label className="stores-form-field full">
                <span>
                  {t("storesI18nStoreName")}
                </span>

                <input
                  value={form.name}
                  onChange={
                    (event) =>
                      setForm(
                        (current) => ({
                          ...current,
                          name:
                            event.target.value,
                        }),
                      )
                  }
                  placeholder={t("storesI18nNamePlaceholder")}
                  autoFocus
                />
              </label>


              <label className="stores-form-field">
                <span>
                  Moneda
                </span>

                <select
                  value={form.currency}
                  onChange={
                    (event) =>
                      setForm(
                        (current) => ({
                          ...current,
                          currency:
                            event.target.value,
                        }),
                      )
                  }
                >
                  {
                    (
                      selectedMarket
                        ?.supported_currencies
                      || (
                        selectedMarket
                          ? [
                              selectedMarket.currency,
                            ]
                          : [
                              form.currency,
                            ].filter(Boolean)
                      )
                    ).map(
                      (currency) => (
                        <option
                          key={currency}
                          value={currency}
                        >
                          {currency}
                        </option>
                      ),
                    )
                  }
                </select>
              </label>


              <label className="stores-form-field">
                <span>
                  Idioma
                </span>

                <select
                  value={
                    form.default_language
                  }
                  onChange={
                    (event) =>
                      setForm(
                        (current) => ({
                          ...current,

                          default_language:
                            event.target.value,
                        }),
                      )
                  }
                >
                  {
                    (
                      selectedMarket
                        ?.languages
                      || [
                        form.default_language,
                      ].filter(Boolean)
                    ).map(
                      (language) => (
                        <option
                          key={language}
                          value={language}
                        >
                          {
                            getLanguageName(
                              language,
                            )
                          }
                        </option>
                      ),
                    )
                  }
                </select>
              </label>


              <label className="stores-form-field full">
                <span>
                  Zona horaria
                </span>

                <input
                  value={form.timezone}
                  onChange={
                    (event) =>
                      setForm(
                        (current) => ({
                          ...current,
                          timezone:
                            event.target.value,
                        }),
                      )
                  }
                  placeholder="America/Lima"
                />
              </label>


              <label className="stores-form-field full">
                <span>
                  Dominio Shopify
                </span>

                <input
                  value={
                    form.shopify_domain
                  }
                  onChange={
                    (event) =>
                      setForm(
                        (current) => ({
                          ...current,

                          shopify_domain:
                            event.target.value,
                        }),
                      )
                  }
                  placeholder="mitienda.myshopify.com"
                />

                <small>
                  Puedes dejarlo vacío y
                  conectar Shopify más adelante.
                </small>
              </label>


              <div className="stores-status-control full">
                <label className="stores-toggle">
                  <input
                    type="checkbox"
                    checked={
                      form.active
                    }
                    onChange={
                      (event) =>
                        setForm(
                          (current) => ({
                            ...current,
                            active:
                              event.target.checked,
                          }),
                        )
                    }
                  />

                  <span>
                    {t("storesI18nStoreActive")}
                  </span>
                </label>

                <small>
                  {form.active
                    ? t("storesI18nOperational")
                    : t("storesI18nSuspendedHelp")}
                </small>
              </div>




            </div>


            <div className="market-preview">
              <div className="market-preview-flag">
                {
                  form.country_code
                    ? getCountryFlag(
                        form.country_code,
                      )
                    : "🌎"
                }
              </div>

              <div>
                <strong>
                  {
                    selectedMarket
                      ?.country_name
                    || editingStore?.name
                    || t("storesI18nMarket")
                  }
                </strong>

                <span>
                  {form.currency || "—"}
                  {" · "}
                  {
                    form.default_language
                      ? getLanguageName(
                          form.default_language,
                        )
                      : "—"
                  }
                  {" · "}
                  {form.timezone || "—"}
                </span>
              </div>
            </div>


            <div className="stores-modal-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={closeModal}
                disabled={saving}
              >
                {t("storesI18nCancel")}
              </button>

              <button
                type="submit"
                className="primary-button"
                disabled={saving}
              >
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
    </div>
  );
}
