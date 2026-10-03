export const COPILOT_PAGE_TEXT_LIMIT = 6000;

export interface CopilotPageContextInput {
  page: string;
  pageLabel?: string;
  entityType?: string;
  entityId?: string | number;
  searchQuery?: string;
}

export function normalizeCopilotPageText(
  text: string,
  limit = COPILOT_PAGE_TEXT_LIMIT,
) {
  const normalized = String(text || "")
    .replace(/\u00a0/g, " ")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();

  if (normalized.length <= limit) return normalized;
  return normalized.slice(0, Math.max(0, limit)).trimEnd();
}

export function captureCopilotPageText(
  root: ParentNode | null,
  limit = COPILOT_PAGE_TEXT_LIMIT,
) {
  if (!root || typeof document === "undefined") return "";

  const clone = root.cloneNode(true) as HTMLElement;
  clone
    .querySelectorAll(
      [
        "input",
        "textarea",
        "select",
        "option",
        "script",
        "style",
        "code",
        "pre",
        "[data-copilot-private]",
        "[aria-hidden='true']",
        ".copilot-panel-root",
      ].join(","),
    )
    .forEach((node) => node.remove());

  return normalizeCopilotPageText(
    clone.innerText || clone.textContent || "",
    limit,
  );
}

export function buildCopilotPageContext(
  input: CopilotPageContextInput,
  pageText: string,
) {
  return {
    page: input.page,
    page_label: input.pageLabel || input.page,
    entity_type: input.entityType || undefined,
    entity_id: input.entityId ?? undefined,
    search_query: input.searchQuery || undefined,
    page_text: pageText || undefined,
    context_source: "current_view",
    context_version: 1,
  };
}
