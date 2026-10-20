/** Codes for a Shopify provider's auth failure, not a DIAGLOB login expiry.
 * Never match a 401 merely by endpoint path: DIAGLOB authentication can
 * legitimately expire during any request, including Shopify endpoints.
 */
const PROVIDER_401_CODES = new Set([
  "SHOPIFY_REAUTH_REQUIRED",
  "SHOPIFY_SHOP_IDENTITY_MISMATCH",
]);

export function isShopifyProviderAuthFailure(
  status: number | undefined,
  detail: unknown,
): boolean {
  if (status !== 401 || !detail || typeof detail !== "object") return false;
  const code = (detail as Record<string, unknown>).code;
  return typeof code === "string" && PROVIDER_401_CODES.has(code);
}
