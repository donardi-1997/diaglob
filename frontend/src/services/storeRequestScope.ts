/** Choose a store for an authenticated request without overwriting a caller's
 * explicitly scoped store. Global read requests deliberately omit X-Store-Id.
 * Server-side membership permissions remain authoritative.
 */
export function resolveRequestStoreId(
  activeStoreId: string | null,
  explicitStoreId: unknown,
  globalScope: boolean,
): string | null {
  if (globalScope) return null;
  const validId = (value: unknown): value is string =>
    typeof value === "string" && /^[1-9][0-9]*$/.test(value);
  if (validId(explicitStoreId)) return explicitStoreId;
  if (validId(activeStoreId)) return activeStoreId;
  return null;
}
