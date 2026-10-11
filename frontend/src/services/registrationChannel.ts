import { parseShopifyInstallHint } from "../shopifyInstall.ts";

export type RegistrationChannel = "direct" | "shopify_install";

/** A valid install return path is only a signup intent, not Shopify proof. */
export function registrationChannelForReturnTo(value: unknown): RegistrationChannel {
  if (typeof value !== "string" || !value.startsWith("/shopify/install?")) {
    return "direct";
  }
  const search = value.slice("/shopify/install".length);
  return parseShopifyInstallHint(search) ? "shopify_install" : "direct";
}
