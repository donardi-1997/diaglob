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
