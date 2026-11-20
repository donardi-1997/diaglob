import { expect, test } from "@playwright/test";
import {
  FOREIGN_BOUND_STORE, mockShopifyApp, PRIMARY_STORE, SHOP, SHOP_ADMIN_URL,
} from "../fixtures/shopifyApi";

test("a merchant without a Diaglob session must sign in before Shopify installation", async ({ page }) => {
  const { calls } = await mockShopifyApp(page, { authenticated: false });
  await page.goto("/shopify/install?managed=1");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.locator('input[type="email"]')).toBeVisible();
  expect(calls.filter((c) => c.path.includes("/shopify/install/"))).toHaveLength(0);
});

test("direct shop hints are never authorization to claim a store", async ({ page }) => {
  const { calls } = await mockShopifyApp(page);
  await page.goto("/shopify/install?shop=attacker.myshopify.com");
  await expect(page.getByRole("heading", { name: "Conecta tu tienda Shopify" })).toBeVisible();
  await expect(page.getByText("Abre DIAGLOB desde Shopify Admin", { exact: false })).toBeVisible();
  expect(calls.some((c) => c.path.endsWith("/shopify/install/pending"))).toBe(false);
  expect(calls.some((c) => c.path.includes("/shopify/install/claim"))).toBe(false);
});

test("expired OAuth authorization cannot display or claim eligible stores", async ({ page }) => {
  const { calls } = await mockShopifyApp(page, { pending: false });
  await page.goto("/shopify/install?authorized=1");
  await expect(page.getByText("La autorización de Shopify expiró", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Finalizar conexión" })).toHaveCount(0);
  expect(calls.filter((c) => c.path.includes("/shopify/install/claim"))).toHaveLength(0);
});

test("verified OAuth grant only lists eligible stores from the signed shop", async ({ page }) => {
  const { calls } = await mockShopifyApp(page);
  await page.goto("/shopify/install?authorized=1");
  await expect(page.getByText("Dominio verificado por Shopify")).toBeVisible();
  await expect(page.getByText(SHOP)).toBeVisible();
  const selector = page.getByLabel("Tienda de Diaglob");
  await expect(selector).toBeVisible();
  await expect(selector.locator("option")).toHaveCount(2); // placeholder + pilot
  await expect(selector.locator("option", { hasText: PRIMARY_STORE.name })).toHaveCount(1);
  await expect(selector.locator("option", { hasText: FOREIGN_BOUND_STORE.name })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Finalizar conexión" })).toBeDisabled();
  expect(calls.filter((c) => c.path.includes("/shopify/install/claim"))).toHaveLength(0);
});

test("successful authorization claims only the selected store and returns a safe Admin URL", async ({ page }) => {
  const { calls } = await mockShopifyApp(page);
  await page.goto("/shopify/install?authorized=1");
  await page.getByLabel("Tienda de Diaglob").selectOption(String(PRIMARY_STORE.id));
  await page.getByRole("button", { name: "Finalizar conexión" }).click();
  await expect(page.getByRole("heading", { name: "Conexión con Shopify guardada" })).toBeVisible();
  const link = page.getByRole("link", { name: "Volver a DIAGLOB en Shopify" });
  await expect(link).toHaveAttribute("href", SHOP_ADMIN_URL);
  await expect(page.getByText("No se ha contratado un plan ni se ha generado ningún cargo.")).toBeVisible();
  const claimCalls = calls.filter((c) => c.path.endsWith("/shopify/install/claim"));
  expect(claimCalls).toHaveLength(1);
  expect(claimCalls[0].path).toBe("/api/stores/17/shopify/install/claim");
  expect(claimCalls[0].headers["x-store-id"]).toBe("17");
  expect(claimCalls[0].headers["x-organization-id"]).toBe("41");
  expect(calls.some((c) => /\/shopify\/orders|\/billing\/.*apply/.test(c.path))).toBe(false);
});

test("a domain conflict shows a human-readable failure without marking the installation complete", async ({ page }) => {
  const { calls } = await mockShopifyApp(page, {
    claimStatus: 409,
    claimDetail: "SHOPIFY_STORE_DOMAIN_MISMATCH",
  });
  await page.goto("/shopify/install?authorized=1");
  await page.getByLabel("Tienda de Diaglob").selectOption("17");
  await page.getByRole("button", { name: "Finalizar conexión" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "otro dominio de Shopify" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Conexión con Shopify guardada" })).toHaveCount(0);
  expect(calls.filter((c) => c.path.endsWith("/shopify/install/claim"))).toHaveLength(1);
});

test("a managed install requires a verified one-use code without putting it in the URL", async ({ page }) => {
  const { calls } = await mockShopifyApp(page);
  await page.goto("/shopify/install?managed=1");
  await page.getByLabel("Código temporal de Shopify").fill("SYNTHETIC-ONE-USE-CODE");
  await page.getByRole("button", { name: "Validar instalación de Shopify" }).click();
  await expect(page.getByText("Dominio verificado por Shopify")).toBeVisible();
  await expect(page.getByLabel("Tienda de Diaglob")).toBeVisible();
  expect(page.url()).not.toContain("SYNTHETIC-ONE-USE-CODE");
  await page.getByLabel("Tienda de Diaglob").selectOption("17");
  await page.getByRole("button", { name: "Finalizar conexión" }).click();
  await expect(page.getByRole("heading", { name: "Conexión con Shopify guardada" })).toBeVisible();
  const attempts = calls.filter((c) => c.path.endsWith("/shopify/install/claim-code"));
  expect(attempts).toHaveLength(1);
  expect(attempts[0].method).toBe("POST");
});

test("an expired managed-install code does not allow store binding", async ({ page }) => {
  const { calls } = await mockShopifyApp(page, { managedPending: false });
  await page.goto("/shopify/install?managed=1");
  await page.getByLabel("Código temporal de Shopify").fill("EXPIRED-SYNTHETIC-CODE");
  await page.getByRole("button", { name: "Validar instalación de Shopify" }).click();
  await expect(page.getByRole("button", { name: "Validar instalación de Shopify" })).toBeVisible();
  await expect(page.getByLabel("Tienda de Diaglob")).toHaveCount(0);
  expect(calls.filter((c) => c.path.includes("/shopify/install/claim"))).toHaveLength(0);
});

test("a user without stores.write cannot retrieve or claim a Shopify grant", async ({ page }) => {
  const { calls } = await mockShopifyApp(page, { permissions: ["stores.read"] });
  await page.goto("/shopify/install?authorized=1");
  await expect(page.getByRole("heading", { name: "Conecta tu tienda Shopify" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Finalizar conexión" })).toHaveCount(0);
  expect(calls.some((c) => c.path === "/api/shopify/install/pending")).toBe(false);
  expect(calls.some((c) => c.path.includes("/shopify/install/claim"))).toBe(false);
});

test("Shopify-managed organizations never see a Paddle checkout on the billing page", async ({ page }) => {
  const { calls } = await mockShopifyApp(page);
  await page.goto("/app/plans");
  await expect(page.getByRole("heading", { name: "Planes y facturación Shopify" })).toBeVisible();
  await expect(page.getByText("Gestionado en Shopify")).toBeVisible();
  await expect(page.getByRole("button", { name: "Abrir planes de Shopify" })).toBeEnabled();
  await expect(page.getByText("prueba gratis de 3 días", { exact: false })).toBeVisible();
  expect(calls.some((c) => c.path.includes("paddle/checkout"))).toBe(false);
});

test("Shopify hosted plans open only the verified Shopify Admin destination", async ({ page }) => {
  const { calls } = await mockShopifyApp(page);
  await page.goto("/app/plans");
  await page.getByRole("button", { name: "Abrir planes de Shopify" }).click();
  await expect(page.getByRole("link", { name: "Ir a la selección de planes en Shopify Admin" }))
    .toHaveAttribute("href", "https://admin.shopify.com/store/diaglob-e2e/apps/diaglob/pricing");
  expect(calls.filter((c) => c.path === "/api/billing/shopify/hosted-plan-selection")).toHaveLength(1);
  expect(calls.some((c) => c.method !== "GET" && c.path.startsWith("/api/billing/"))).toBe(false);
});

test("a mismatched billing tenant never exposes a plan-change link", async ({ page }) => {
  await mockShopifyApp(page, { billingMismatch: true });
  await page.goto("/app/plans");
  await expect(page.getByRole("heading", { name: "Planes y facturación Shopify" })).toBeVisible();
  await expect(page.getByText("No se pudo confirmar la organización de facturación.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Abrir planes de Shopify" })).toBeDisabled();
  await expect(page.getByRole("link", { name: "Ir a la selección de planes en Shopify Admin" })).toHaveCount(0);
});

test("billing onboarding without a verified Shopify connection blocks payments", async ({ page }) => {
  const { calls } = await mockShopifyApp(page, {
    organizationOverride: { billing_provider: null, billing_onboarding_channel: "shopify_install" },
  });
  await page.goto("/app/plans");
  await expect(page.getByRole("heading", { name: "Termina de conectar tu tienda Shopify" })).toBeVisible();
  await expect(page.getByText("No se ha creado ninguna suscripción.", { exact: false })).toBeVisible();
  expect(calls.some((c) => c.path.includes("/billing/shopify/hosted-plan-selection"))).toBe(false);
});

test("Shopify billing is read-only for an unauthorized role", async ({ page }) => {
  await mockShopifyApp(page, { role: "viewer" });
  await page.goto("/app/plans");
  await expect(page.getByRole("heading", { name: "Consulta restringida" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Abrir planes de Shopify" })).toHaveCount(0);
});
