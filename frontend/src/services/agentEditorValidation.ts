/** Only active, authorized stores can be assigned to an enabled agent. */
export function validateAgentStoreAssignment(
  active: boolean,
  selectedStoreIds: number[],
  availableActiveStoreIds: number[],
): "STORE_REQUIRED" | "STORE_UNAVAILABLE" | null {
  const allowed = new Set(availableActiveStoreIds);
  if (selectedStoreIds.some((id) => !Number.isInteger(id) || !allowed.has(id))) {
    return "STORE_UNAVAILABLE";
  }
  if (active && selectedStoreIds.length === 0) {
    return "STORE_REQUIRED";
  }
  return null;
}
