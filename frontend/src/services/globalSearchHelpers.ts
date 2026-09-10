export function normalizeGlobalSearchQuery(value: string) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}


export function globalSearchMatches(
  query: string,
  values: Array<string | null | undefined>,
) {
  const normalizedQuery = normalizeGlobalSearchQuery(query);

  if (!normalizedQuery) return false;

  return values.some((value) =>
    normalizeGlobalSearchQuery(value || "").includes(normalizedQuery),
  );
}
