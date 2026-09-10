export const DROPSHIPPING_ANALYTICS_SECTIONS = [
  "overview",
  "profitability",
  "products",
  "orders",
] as const;

export type DropshippingAnalyticsSection =
  (typeof DROPSHIPPING_ANALYTICS_SECTIONS)[number];


export function settledValue<T>(
  result: PromiseSettledResult<T>,
): T | null {
  return result.status === "fulfilled" ? result.value : null;
}


export function getFailedDropshippingSections(
  results: readonly PromiseSettledResult<unknown>[],
): DropshippingAnalyticsSection[] {
  return DROPSHIPPING_ANALYTICS_SECTIONS.filter(
    (_section, index) => results[index]?.status === "rejected",
  );
}


export function allDropshippingSectionsFailed(
  failedSections: readonly DropshippingAnalyticsSection[],
): boolean {
  return failedSections.length === DROPSHIPPING_ANALYTICS_SECTIONS.length;
}
