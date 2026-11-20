import { expect, test } from "@playwright/test";

// This smoke test is opt-in only. It never chooses a plan, claims an install,
// posts an order, changes permissions or invokes privacy deletion.
test("a dedicated staging reviewer can inspect Shopify billing and installation safely", async ({ page }) => {
  const email = process.env.E2E_STAGING_EMAIL;
  const password = process.env.E2E_STAGING_PASSWORD;
  const base = process.env.E2E_STAGING_BASE_URL;
  if (!email || !password || !base) {
    throw new Error("Dedicated staging reviewer credentials and staging URL are required.");
  }

  const frontendHost = new URL(base).hostname.toLowerCase();
  const allowedStaging = (host: string) =>
    host === frontendHost || host === "staging.diaglob.tech" ||
    host.endsWith(".staging.diaglob.tech");
  const failedWrites: string[] = [];

  // Browser-side fail-closed access: only this staging zone and Cognito login.
  // Reject requests to production API, Partner, Paddle and other third parties.
  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const host = url.hostname.toLowerCase();
    if (allowedStaging(host)) {
      if (url.pathname.startsWith("/api/") && !["GET", "HEAD"].includes(request.method())) {
        failedWrites.push(request.method() + " " + url.pathname);
        return route.abort();
      }
      return route.continue();
    }
    if (/^cognito-idp\.[a-z0-9-]+\.amazonaws\.com$/.test(host) &&
        request.method() === "POST" && url.pathname === "/") {
      return route.continue();
    }
    return route.abort();
  });

  await page.goto("/app/plans");
  await expect(page).toHaveURL(/\/login$/);
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.locator('form.marketing-auth-form button[type="submit"]').click();

  // A real staging reviewer must belong to a Shopify-billed test organization.
  await expect(page.getByRole("heading", { name: "Planes y facturación Shopify" }))
    .toBeVisible({ timeout: 25_000 });
  await expect(page.getByText("Gestionado en Shopify")).toBeVisible();
  await expect(page.getByText("Shopify administra los cobros.", { exact: false })).toBeVisible();

  // Visiting the managed-install entry is read-only; no code is submitted.
  await page.goto("/shopify/install?managed=1");
  await expect(page.getByRole("heading", { name: "Conecta tu tienda Shopify" })).toBeVisible();
  await expect(page.getByLabel("Código temporal de Shopify")).toBeVisible();
  expect(failedWrites).toEqual([]);
});
