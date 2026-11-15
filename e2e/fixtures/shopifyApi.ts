import type { Page, Route } from "@playwright/test";

// These are synthetic browser/API fixtures. Never use live access tokens,
// real customer records or actual Shopify domains in mocked CI.
export const SHOP = "diaglob-e2e.myshopify.com";
export const PUBLIC_APP_CLIENT_ID = "c5fc9aed710462d41767477fa9e595c0";
export const SHOP_ADMIN_URL =
  "https://" + SHOP + "/admin/apps/" + PUBLIC_APP_CLIENT_ID;

export type ApiCall = { method: string; path: string; headers: Record<string, string> };

export interface StoreFixture {
  id: number;
  name: string;
  slug: string;
  active: boolean;
  shopify_domain: string | null;
  country_code: string;
  currency: string;
  timezone: string;
  default_language: string;
}

export const PRIMARY_STORE: StoreFixture = {
  id: 17, name: "Tienda piloto", slug: "pilot", active: true,
  shopify_domain: null, country_code: "CO", currency: "COP",
  timezone: "America/Bogota", default_language: "es",
};
export const FOREIGN_BOUND_STORE: StoreFixture = {
  ...PRIMARY_STORE, id: 19, name: "Otra tienda", slug: "other",
  shopify_domain: "unrelated.myshopify.com",
};

export interface ShopifyMockOptions {
  authenticated?: boolean;
  permissions?: string[];
  role?: string;
  stores?: StoreFixture[];
  pending?: boolean;
  managedPending?: boolean;
  claimStatus?: number;
  claimDetail?: unknown;
  organizationOverride?: Record<string, unknown>;
  billingMismatch?: boolean;
  hostedPricingConfigured?: boolean;
}

export async function mockShopifyApp(
  page: Page,
  options: ShopifyMockOptions = {},
): Promise<{ calls: ApiCall[] }> {
  const calls: ApiCall[] = [];
  const authenticated = options.authenticated !== false;
  const permissions = options.permissions ??
    ["dashboard.read", "stores.read", "stores.write"];
  const stores = options.stores ?? [PRIMARY_STORE, FOREIGN_BOUND_STORE];

  // Strict synthetic-only egress guard. No test can accidentally call
  // Cognito, Shopify Partner, Paddle or real Diaglob endpoints.
  await page.route("**/*", async (route) => {
    const url = route.request().url();
    if (url.startsWith("data:") || url.startsWith("blob:")) {
      await route.continue();
      return;
    }
    const parsed = new URL(url);
    if (parsed.hostname === "127.0.0.1" || parsed.hostname === "localhost") {
      await route.continue();
      return;
    }
    await route.abort();
  });

  // Keep advertising disabled; eliminate consent overlays without external pixels.
  await page.addInitScript(() => {
    localStorage.setItem("diaglob-cookie-consent-v1", JSON.stringify({
      version: 1, necessary: true, advertising: false,
      decidedAt: "2026-01-01T00:00:00.000Z",
    }));
  });

  if (authenticated) {
    await page.addInitScript(() => {
      localStorage.setItem("diaglob-access-token", "synthetic-e2e-access");
      localStorage.setItem("diaglob-id-token", "synthetic-e2e-id");
      localStorage.setItem("diaglob-organization-id", "41");
      localStorage.setItem("diaglob-language", "es");
    });
  }

  const organization = {
    id: 41,
    name: "Organización sintética",
    slug: "synthetic-review",
    active: true,
    auto_renew_enabled: true,
    billing_provider: "shopify",
    billing_onboarding_channel: "shopify_install",
    plan: "starter",
    plan_name: "Starter",
    subscription_status: "active",
    trial: { status: "ended", started_at: null, ends_at: null, days_remaining: 0, ai_response_limit: 50 },
    billing_period_months: 1, next_billed_at: null,
    pending_plan: null, pending_billing_period_months: null,
    pending_plan_effective_at: null,
    active_stores: 1, active_store_limit: 3,
    role: options.role ?? "owner",
    all_stores: true, permissions,
    ...options.organizationOverride,
  };
  const respond = async (route: Route,
                         body: unknown, status = 200) => {
    await route.fulfill({
      status,
      contentType: "application/json; charset=utf-8",
      headers: { "Cache-Control": "no-store" },
      body: JSON.stringify(body),
    });
  };

  await page.route("**/api/**", async (route) => {
    const req = route.request();
    const u = new URL(req.url());
    const path = u.pathname;
    const method = req.method();
    calls.push({ method, path, headers: req.headers() });
    if (method === "GET" && path === "/api/me") {
      return respond(route, {
        id: 23, name: "Usuario sintético", email: "e2e@example.invalid",
        active: true,
      });
    }
    if (method === "GET" && path === "/api/me/organizations") {
      return respond(route, { total: 1, items: [{
        id: 41, name: "Organización sintética", slug: "synthetic-review",
        role: options.role ?? "owner", all_stores: true, permissions,
      }] });
    }
    if (method === "GET" && path === "/api/stores") {
      return respond(route, { total: stores.length, items: stores });
    }
    if (method === "GET" && path === "/api/organization") {
      return respond(route, organization);
    }
    if (method === "GET" && path === "/api/markets") {
      return respond(route, { total: 1, items: [{
        country_code: "CO", country_name: "Colombia", country_name_en: "Colombia",
        region: "south_america", currency: "COP",
        default_language: "es", languages: ["es"], default_timezone: "America/Bogota",
      }] });
    }
    if (method === "GET" && path === "/api/shopify/install/pending") {
      return respond(route, { pending: options.pending !== false,
        shop_domain: options.pending === false ? null : SHOP });
    }
    if (method === "POST" && path === "/api/shopify/install/managed/pending") {
      return respond(route, { pending: options.managedPending !== false,
        shop_domain: options.managedPending === false ? null : SHOP });
    }
    if (method === "POST" && /^\/api\/stores\/[0-9]+\/shopify\/install\/claim(?:-code)?$/.test(path)) {
      if (options.claimStatus && options.claimStatus !== 200) {
        return respond(route, {
          detail: options.claimDetail ?? "SHOPIFY_STORE_DOMAIN_MISMATCH",
        }, options.claimStatus);
      }
      const storeId = Number(path.split("/")[3]);
      return respond(route, {
        connected: true, store_id: storeId, shop_domain: SHOP,
        shopify_admin_url: SHOP_ADMIN_URL, webhooks_ready: true,
      });
    }
    if (method === "GET" && path === "/api/billing/shopify/reconciliation-history") {
      return respond(route, {
        organization_id: options.billingMismatch ? 999 : 41,
        applied: false, items: [],
      });
    }
    if (method === "GET" && path === "/api/billing/shopify/transition-proposals") {
      return respond(route, {
        organization_id: options.billingMismatch ? 999 : 41,
        applied: false, items: [],
      });
    }
    if (method === "GET" && path === "/api/billing/shopify/capabilities") {
      return respond(route, {
        organization_id: 41, shopify_hosted_pricing_configured:
          options.hostedPricingConfigured !== false,
        verified_entitlement_apply_enabled: false,
        paddle_checkout_available: false, paddle_migration_required: false,
        public_plans: ["starter", "growth", "pro"],
        trial_days: 3, billing_period_months: [1, 12],
      });
    }
    if (method === "GET" && path === "/api/billing/shopify/hosted-plan-selection") {
      return respond(route, {
        provider: "shopify", hosted_by_shopify: true,
        entitlements_applied: false,
        url: "https://admin.shopify.com/store/diaglob-e2e/apps/diaglob/pricing",
      });
    }
    // Unknown calls are deliberate 404s, never forwarded to a real backend.
    return respond(route, { detail: "SYNTHETIC_API_NOT_IMPLEMENTED" }, 404);
  });

  return { calls };
}
