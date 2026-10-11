/** Payment flows must never fall back to Paddle for an unknown provider. */
export type BillingChannel = "shopify" | "paddle" | "unverified";

export function billingChannel(value: string | null | undefined): BillingChannel {
  const normalized = typeof value === "string" ? value.trim().toLowerCase() : "";
  if (normalized === "shopify") return "shopify";
  if (normalized === "paddle") return "paddle";
  return "unverified";
}
