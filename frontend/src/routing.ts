export const APP_PAGE_SEGMENTS = {
  overview: "overview",
  analytics: "analytics",
  conversations: "conversations",
  customers: "customers",
  commerce: "commerce",
  "post-sales": "post-sales",
  integrations: "integrations",
  automations: "automations",
  agents: "agents",
  knowledge: "knowledge",
  settings: "stores",
  team: "team",
  plans: "plans",
} as const;

export type AppPageKey = keyof typeof APP_PAGE_SEGMENTS;

const APP_SEGMENT_TO_PAGE = Object.fromEntries(
  Object.entries(APP_PAGE_SEGMENTS).map(([page, segment]) => [segment, page]),
) as Record<string, AppPageKey>;

export function getAppPath(page: string) {
  const segment = APP_PAGE_SEGMENTS[page as AppPageKey];
  return segment ? `/app/${segment}` : "/app";
}

export function isAppRoot(pathname: string) {
  return pathname === "/app" || pathname === "/app/";
}

export function getAppPageFromPath(pathname: string): AppPageKey | null {
  const normalized = pathname.length > 1 && pathname.endsWith("/")
    ? pathname.slice(0, -1)
    : pathname;

  const match = normalized.match(/^\/app\/([^/]+)$/);
  if (!match) return null;

  return APP_SEGMENT_TO_PAGE[match[1]] || null;
}

export function isAppPath(pathname: string) {
  return isAppRoot(pathname) || pathname.startsWith("/app/");
}

export function sanitizeReturnTo(value: unknown, fallback = "/app") {
  if (typeof value !== "string") return fallback;
  if (!value.startsWith("/")) return fallback;
  if (value.startsWith("//")) return fallback;

  const pathOnly = value.split(/[?#]/, 1)[0];
  return isAppPath(pathOnly) ? value : fallback;
}
