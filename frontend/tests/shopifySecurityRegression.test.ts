import assert from "node:assert/strict";
import test from "node:test";

import {
  DIAGLOB_SHOPIFY_CLIENT_ID,
  eligibleShopifyInstallStores,
  parseShopifyInstallHint,
  parseShopifyInstallMode,
  validatedShopifyAuthorizationUrl,
  validatedShopifyInstallCompletion,
} from "../src/shopifyInstall.ts";
import { resolveOrganizationId, resolveStoreId } from "../src/hooks/workspaceSelection.ts";
import { resolveRequestStoreId } from "../src/services/storeRequestScope.ts";
import { classifyStoreAvailability } from "../src/services/storeAvailability.ts";
import { parseShopifyHostedPricingReturn } from "../src/services/shopifyBillingReturn.ts";

const SHOP = "safe-test.myshopify.com";
const OAUTH = "https://" + SHOP + "/admin/oauth/authorize?client_id=" +
  DIAGLOB_SHOPIFY_CLIENT_ID + "&state=fixture-state";

test("Shopify OAuth accepts this app, this shop, and exactly one state", () => {
  assert.equal(validatedShopifyAuthorizationUrl(OAUTH, SHOP), OAUTH);
  const withScope = OAUTH + "&scope=read_products";
  assert.equal(validatedShopifyAuthorizationUrl(withScope, SHOP), withScope);
});

test("Shopify OAuth denies wrong app identity, duplicate security parameters and fragments", () => {
  const cases = [
    OAUTH.replace(DIAGLOB_SHOPIFY_CLIENT_ID, "attacker-client"),
    OAUTH + "&client_id=attacker-client",
    OAUTH + "&client_id=" + DIAGLOB_SHOPIFY_CLIENT_ID,
    OAUTH + "&state=second-state",
    OAUTH + "&state=fixture-state",
    OAUTH + "#secret",
    OAUTH.replace("state=fixture-state", "state="),
    OAUTH.replace("client_id=" + DIAGLOB_SHOPIFY_CLIENT_ID, "client_id="),
    OAUTH.replace("https://", "http://"),
    OAUTH.replace(SHOP, "another.myshopify.com"),
    OAUTH.replace("/admin/oauth/authorize", "/admin/oauth/access_token"),
    OAUTH.replace(SHOP, "user@" + SHOP),
    OAUTH.replace(SHOP, SHOP + ":444"),
  ];
  for (const url of cases) {
    assert.throws(
      () => validatedShopifyAuthorizationUrl(url, SHOP),
      /Invalid Shopify authorization redirect/,
      url,
    );
  }
});

test("untrusted install hints reject duplicate values and hostile URL shapes", () => {
  assert.equal(parseShopifyInstallHint("?shop=OTHER.myshopify.com"), "other.myshopify.com");
  for (const query of [
    "?shop=" + SHOP + "&shop=" + SHOP,
    "?shop=https%3A%2F%2F" + SHOP,
    "?shop=" + SHOP + ".attacker.example",
    "?shop=bad%40" + SHOP,
    "?shop=" + SHOP + "%2Fadmin",
    "?shop=" + SHOP + "&state=forged",
    "?shop=" + "a".repeat(1050),
  ]) assert.equal(parseShopifyInstallHint(query), null, query);
});

test("tracking can preserve a mode but cannot authorize one or change its meaning", () => {
  assert.equal(parseShopifyInstallMode("?managed=1&utm_source=test&utm_campaign=demo"), "managed");
  assert.equal(parseShopifyInstallMode("?authorized=1&utm_medium=referral"), "authorized");
  for (const query of [
    "?utm_source=ads", "?managed=1&authorized=1",
    "?managed=1&managed=1", "?authorized=1&authorized=1",
    "?authorized=1&shop=" + SHOP, "?managed=1&redirect_uri=https://attacker.example",
    "?managed=1&state=forged", "?managed=1&unknown=1",
    "?managed=1&" + "x".repeat(1100),
  ]) assert.equal(parseShopifyInstallMode(query), null, query);
});

test("installed app return is bound to exactly one store, shop and application URL", () => {
  const safe = {
    connected: true,
    store_id: 11,
    shop_domain: SHOP,
    shopify_admin_url: "https://" + SHOP + "/admin/apps/" + DIAGLOB_SHOPIFY_CLIENT_ID,
  };
  assert.equal(validatedShopifyInstallCompletion(safe, 11, SHOP), safe.shopify_admin_url);
  for (const change of [
    { connected: false }, { store_id: 12 }, { shop_domain: "other.myshopify.com" },
    { shopify_admin_url: safe.shopify_admin_url + "?code=leak" },
    { shopify_admin_url: safe.shopify_admin_url + "#grant" },
    { shopify_admin_url: safe.shopify_admin_url.replace(DIAGLOB_SHOPIFY_CLIENT_ID, "other-client") },
    { shopify_admin_url: safe.shopify_admin_url.replace(SHOP, "other.myshopify.com") },
  ]) assert.throws(() => validatedShopifyInstallCompletion({ ...safe, ...change }, 11, SHOP));
});

test("a bound Shopify store is never silently reassigned", () => {
  const stores = [
    { id: 1, active: true, shopify_domain: null },
    { id: 2, active: true, shopify_domain: SHOP.toUpperCase() },
    { id: 3, active: true, shopify_domain: "other.myshopify.com" },
    { id: 4, active: false, shopify_domain: null },
  ];
  const before = structuredClone(stores);
  assert.deepEqual(eligibleShopifyInstallStores(stores, SHOP).map((store) => store.id), [1, 2]);
  assert.deepEqual(stores, before);
});

test("organization changes discard previously selected inaccessible stores", () => {
  assert.equal(resolveOrganizationId([{ id: 1 }, { id: 2 }], "2"), "2");
  assert.equal(resolveOrganizationId([{ id: 3 }], "2"), "3");
  assert.equal(resolveOrganizationId([], "2"), "");
  assert.equal(resolveStoreId([{ id: 101, active: true }], "101"), "101");
  assert.equal(resolveStoreId([{ id: 202, active: true }], "101"), "202");
  assert.equal(resolveStoreId([{ id: 203, active: false }], "203"), "");
  assert.equal(resolveStoreId([], "101"), "");
});

test("X-Store-Id rejects unexpected identifiers and never scopes global reads", () => {
  for (const invalid of [
    "0", "01", "-1", "1e3", "1.0", " 1", "1 ", "1\n", "1,2",
    "", "NaN", "Infinity", 22, null, undefined,
  ]) {
    assert.equal(resolveRequestStoreId(null, invalid, false), null, String(invalid));
    assert.equal(resolveRequestStoreId("17", invalid, false), "17", String(invalid));
  }
  assert.equal(resolveRequestStoreId("17", "23", false), "23");
  assert.equal(resolveRequestStoreId("17", "23", true), null);
  assert.equal(resolveRequestStoreId(null, "23", true), null);
});

test("availability distinguishes no stores, unassigned membership and an API mismatch", () => {
  assert.equal(classifyStoreAvailability(1, null, null), "available");
  assert.equal(classifyStoreAvailability(0, 0, true), "no-active-stores");
  assert.equal(classifyStoreAvailability(0, 4, false), "unassigned");
  assert.equal(classifyStoreAvailability(0, 4, true), "mismatch");
  assert.equal(classifyStoreAvailability(0, 4, null), "unknown");
  for (const count of [null, -1, 1.25, NaN, Infinity]) {
    assert.equal(classifyStoreAvailability(0, count, false), "unknown");
  }
});

test("Shopify pricing callbacks are untrusted re-verification hints, not entitlements", () => {
  assert.deepEqual(parseShopifyHostedPricingReturn(
    "?plan_handle=pro&plan_handle=starter&shop=attacker.myshopify.com&tab=usage",
  ), { shouldReverify: true, cleanedSearch: "tab=usage" });
  assert.deepEqual(parseShopifyHostedPricingReturn("?plan=pro&target_plan=scale"), {
    shouldReverify: false, cleanedSearch: "plan=pro&target_plan=scale",
  });
  assert.deepEqual(parseShopifyHostedPricingReturn("?plan_handle="), {
    shouldReverify: true, cleanedSearch: "",
  });
});
