export type StoreAvailability =
  | "available"
  | "no-active-stores"
  | "unassigned"
  | "mismatch"
  | "unknown";

/**
 * Classification based only on the current member's visible stores and the
 * current organization's already-authorized aggregate from /api/organization.
 * It never changes permissions or assumes empty data means no stores exist.
 */
export function classifyStoreAvailability(
  visibleStores: number,
  organizationActiveStores: number | null,
  allStores: boolean | null,
): StoreAvailability {
  if (visibleStores > 0) return "available";
  if (
    organizationActiveStores === null ||
    !Number.isSafeInteger(organizationActiveStores) ||
    organizationActiveStores < 0
  ) {
    return "unknown";
  }
  if (organizationActiveStores === 0) return "no-active-stores";
  if (allStores === false) return "unassigned";
  return allStores === true ? "mismatch" : "unknown";
}
