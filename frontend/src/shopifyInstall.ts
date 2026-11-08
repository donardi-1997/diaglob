/** Parse explicit Shopify installation modes, ignoring only known UTM markers.
 * UI tracking parameters must not change the authenticated Shopify grant path.
 * A mode flag is a navigation hint, never proof of merchant authorization.
 */
export function parseShopifyInstallMode(search: string): "managed" | "authorized" | null {
  if (!search || search.length > 1024) return null;
  const params = new URLSearchParams(search);
  const supportedTracking = new Set([
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
  ]);
  const modeKeys = ["managed", "authorized"].filter((key) => params.has(key));
  if (modeKeys.length !== 1) return null;
  const mode = modeKeys[0] as "managed" | "authorized";
  if (params.getAll(mode).length !== 1 || params.get(mode) !== "1") return null;
  if ([...params.keys()].some((key) => key !== mode && !supportedTracking.has(key))) {
    return null;
  }
  return mode;
}

/** Only a merchant-facing hint; never evidence of Shopify ownership. */
const SHOP_DOMAIN = /^[a-z0-9][a-z0-9-]*\.myshopify\.com$/;
// Public app identity, not a secret. Must match the linked app's TOML/backend.
export const DIAGLOB_SHOPIFY_CLIENT_ID = "c5fc9aed710462d41767477fa9e595c0";

export function validatedShopifyInstallCompletion(
  result: { connected: boolean; store_id: number; shop_domain: string; shopify_admin_url: string },
  storeId: number,
  verifiedShop: string,
): string {
  if (
    result.connected !== true || result.store_id !== storeId ||
    result.shop_domain !== verifiedShop || !SHOP_DOMAIN.test(verifiedShop) ||
    verifiedShop.length > 255 ||
    result.shopify_admin_url !== `https://${verifiedShop}/admin/apps/${DIAGLOB_SHOPIFY_CLIENT_ID}`
  ) throw new Error("No se pudo confirmar el retorno seguro a Shopify.");
  return result.shopify_admin_url;
}

export function parseShopifyInstallHint(search: string): string | null {
  if (search.length > 1024) return null;
  const params = new URLSearchParams(search);
  if ([...params.keys()].some((key) => key !== "shop")) return null;
  const shops = params.getAll("shop");
  if (shops.length !== 1) return null;
  const value = shops[0].trim().toLowerCase();
  return value.length <= 255 && SHOP_DOMAIN.test(value) ? value : null;
}

export interface InstallableStore {
  id: number;
  active: boolean;
  shopify_domain: string | null;
}

/** A pre-existing different shop must never be silently reassigned. */
export function eligibleShopifyInstallStores<T extends InstallableStore>(
  stores: T[], shop: string,
): T[] {
  return stores.filter((store) =>
    store.active &&
    (!store.shopify_domain || store.shopify_domain.toLowerCase() === shop),
  );
}

export function validatedShopifyAuthorizationUrl(url: string, shop: string): string {
  const parsed = new URL(url);
  if (
    parsed.protocol !== "https:" ||
    parsed.hostname !== shop ||
    parsed.port !== "" ||
    parsed.username || parsed.password ||
    parsed.pathname !== "/admin/oauth/authorize" ||
    !parsed.searchParams.get("state") ||
    !parsed.searchParams.get("client_id")
  ) {
    throw new Error("Invalid Shopify authorization redirect");
  }
  return parsed.toString();
}


/**
 * Builds a local Store payload ONLY after the caller has received the
 * verified shop from /api/shopify/install/pending. Browser shop hints alone
 * must never be treated as proof of Shopify ownership.
 */
export function buildPostOAuthStorePayload(
  verifiedShop: string | null,
  name: string,
  countryCode: string,
  allowedCountries: readonly string[],
) {
  if (
    !verifiedShop ||
    parseShopifyInstallHint(`?shop=${encodeURIComponent(verifiedShop)}`) !== verifiedShop
  ) {
    throw new Error("Shopify authorization is required before creating a store");
  }
  const cleanedName = name.trim();
  if (!cleanedName || cleanedName.length > 150) {
    throw new Error("Store name is required (maximum 150 characters)");
  }
  if (!/^[A-Z]{2}$/.test(countryCode) || !allowedCountries.includes(countryCode)) {
    throw new Error("Select a supported market");
  }
  return {
    name: cleanedName,
    country_code: countryCode,
    shopify_domain: verifiedShop,
    active: true as const,
  };
}

/**
 * Shopify App Store requirement 2.1.1: an HTTP failure must never reach the
 * merchant as raw client text such as "Request failed with status code 409".
 * Only known backend reason codes and HTTP statuses are translated, and the
 * result is always an actionable message in Spanish.
 */
interface InstallFailureResponse {
  status?: number;
  data?: { detail?: unknown };
}

interface InstallFailure {
  response?: InstallFailureResponse;
}

const REASON_CODE = /^[A-Z][A-Z0-9_]*$/;

const INSTALL_REASON_MESSAGES: Record<string, string> = {
  SHOPIFY_BILLING_ORGANIZATION_REQUIRED:
    "Esta organización no puede reclamar una instalación de Shopify porque su facturación " +
    "no está en el canal de Shopify. Entra con una cuenta creada desde la instalación de " +
    "Shopify o contacta a soporte de DIAGLOB.",
  SHOPIFY_STORE_DOMAIN_MISMATCH:
    "La tienda seleccionada ya está vinculada a otro dominio de Shopify. Elige otra tienda " +
    "o desvincula primero ese dominio.",
  COMMERCE_ALREADY_CONNECTED:
    "La tienda seleccionada ya tiene otra integración de comercio conectada.",
  SHOPIFY_STORE_ALREADY_CONNECTED:
    "Esa tienda de Shopify ya está conectada a DIAGLOB. Abre la app desde Shopify Admin para " +
    "continuar.",
  SHOPIFY_INSTALL_GRANT_EXPIRED:
    "El código de instalación expiró o ya fue utilizado. Genera uno nuevo desde Shopify Admin " +
    "(caduca en 10 minutos).",
  SHOPIFY_EXPIRING_INSTALL_GRANT_REQUIRED:
    "Shopify no devolvió credenciales renovables. Genera el código de instalación de nuevo " +
    "desde Shopify Admin.",
  SHOPIFY_INSTALL_STORE_INVALID:
    "La tienda seleccionada ya no está disponible para esta instalación.",
  ORGANIZATION_CONTEXT_REQUIRED:
    "Selecciona una organización antes de continuar.",
  TRIAL_STORE_ALREADY_USED:
    "Esta tienda ya utilizó la prueba gratuita de DIAGLOB. Conéctala con un plan de pago.",
  TRIAL_NOT_AVAILABLE:
    "Esta cuenta no tiene una prueba gratuita disponible. Elige un plan para continuar.",
};

function readInstallFailure(error: unknown): {
  status: number | null;
  code: string | null;
  message: string | null;
} {
  const response = (error as InstallFailure | null)?.response;
  const status = typeof response?.status === "number" ? response.status : null;
  const detail = response?.data?.detail;

  if (typeof detail === "string") {
    const value = detail.trim();
    if (!value) return { status, code: null, message: null };
    return REASON_CODE.test(value)
      ? { status, code: value, message: null }
      : { status, code: null, message: value };
  }

  if (detail && typeof detail === "object") {
    const record = detail as { code?: unknown; message?: unknown };
    const code =
      typeof record.code === "string" && REASON_CODE.test(record.code.trim())
        ? record.code.trim()
        : null;
    const message =
      typeof record.message === "string" && record.message.trim()
        ? record.message.trim()
        : null;
    return { status, code, message };
  }

  return { status, code: null, message: null };
}

/** Translate any rejected install request into a message a merchant can act on. */
export function describeShopifyInstallError(error: unknown): string {
  const { status, code, message } = readInstallFailure(error);

  if (code && INSTALL_REASON_MESSAGES[code]) return INSTALL_REASON_MESSAGES[code];
  if (status === 401) {
    return "Tu sesión expiró. Inicia sesión de nuevo en DIAGLOB y repite el paso.";
  }
  if (message) return message;

  if (status === 402) {
    return "Se requiere un plan activo para completar esta operación.";
  }
  if (status === 403) {
    return "No tienes permisos para administrar las tiendas de esta organización.";
  }
  if (status === 404) {
    return "El código expiró o ya fue utilizado. Genera uno nuevo desde Shopify Admin.";
  }
  if (status === 409) {
    return "No se pudo completar la conexión con Shopify: hay un conflicto con el estado " +
      "actual de la tienda. Recarga la página e inténtalo de nuevo; si persiste, contacta " +
      "a soporte de DIAGLOB.";
  }
  if (status === 410) {
    return "Esta instalación debe iniciarse desde Shopify Admin.";
  }
  if (status !== null && status >= 500) {
    return "DIAGLOB no respondió correctamente. Inténtalo de nuevo en unos minutos.";
  }
  if (status === null) {
    return "No se pudo contactar con DIAGLOB. Revisa tu conexión e inténtalo de nuevo.";
  }
  return `No fue posible completar la operación (HTTP ${status}). Inténtalo de nuevo.`;
}

/** Organization fields the install page uses to explain a guard before it fires. */
export interface ShopifyInstallOrganization {
  active?: boolean;
  billing_provider?: string | null;
  billing_onboarding_channel?: string | null;
  plan?: string | null;
  pending_plan?: string | null;
  active_stores?: number;
  active_store_limit?: number;
}

/**
 * Client-side mirror of the store-capacity guard. Returns a blocker only when
 * the create-store request is certain to be rejected; the backend still owns
 * the decision.
 */
export function shopifyInstallStoreBlocker(
  organization: ShopifyInstallOrganization,
  hasEligibleStore: boolean,
): string | null {
  if (hasEligibleStore) return null;
  const used = organization.active_stores;
  const limit = organization.active_store_limit;
  if (typeof used !== "number" || typeof limit !== "number" || used < limit) return null;
  return `Tu plan permite hasta ${limit === 1 ? "una tienda activa" : `${limit} tiendas activas`} ` +
    `y ya tienes ${used}. Libera una tienda o cambia de plan para vincular esta instalación ` +
    "de Shopify.";
}

/**
 * Client-side mirror of `_eligible_shopify_claim_billing`. Reports a blocker
 * only for combinations that are certain to fail, so a valid installation is
 * never blocked by an incomplete client-side view.
 */
export function shopifyInstallBillingBlocker(
  organization: ShopifyInstallOrganization,
): string | null {
  if (organization.active === false) {
    return "Esta organización no está activa. Contacta a soporte de DIAGLOB.";
  }

  const provider = (organization.billing_provider ?? "").trim().toLowerCase();
  if (provider === "shopify") return null;
  if (provider) {
    return "Esta organización tiene facturación directa y no puede vincular una instalación " +
      "de Shopify. Entra con una cuenta creada desde la instalación de Shopify o contacta " +
      "a soporte de DIAGLOB.";
  }

  const plan = (organization.plan ?? "none").trim().toLowerCase();
  if (organization.pending_plan) {
    return "Esta organización tiene un cambio de plan pendiente. Contacta a soporte de DIAGLOB " +
      "para vincular la instalación.";
  }
  // An incomplete snapshot must never block a valid installation.
  if (organization.billing_onboarding_channel === undefined || organization.plan === undefined) {
    return null;
  }
  if ((organization.billing_onboarding_channel ?? "").trim() !== "shopify_install") {
    return "Esta cuenta no se creó desde la instalación de Shopify, por lo que no puede " +
      "reclamar esta instalación. Regístrate desde el enlace de instalación o contacta a " +
      "soporte de DIAGLOB.";
  }
  if (plan !== "none" && plan !== "trial") {
    return "Esta organización tiene un plan que requiere revisión manual antes de vincular " +
      "Shopify. Contacta a soporte de DIAGLOB.";
  }
  return null;
}
