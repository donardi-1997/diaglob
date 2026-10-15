import { parseShopifyInstallHint } from "../shopifyInstall.ts";

export type RegistrationChannel = "direct" | "shopify_install";

/** A valid install return path is only a signup intent, not Shopify proof. */
export function registrationChannelForReturnTo(value: unknown): RegistrationChannel {
  if (typeof value !== "string" || !value.startsWith("/shopify/install?")) {
    return "direct";
  }
  if (value === "/shopify/install?authorized=1" || value === "/shopify/install?managed=1") return "shopify_install";
  const search = value.slice("/shopify/install".length);
  return parseShopifyInstallHint(search) ? "shopify_install" : "direct";
}
