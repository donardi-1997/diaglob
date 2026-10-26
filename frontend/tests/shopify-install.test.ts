import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  buildPostOAuthStorePayload,
  eligibleShopifyInstallStores,
  parseShopifyInstallHint,
  parseShopifyInstallMode,
  validatedShopifyAuthorizationUrl,
  validatedShopifyInstallCompletion,
  DIAGLOB_SHOPIFY_CLIENT_ID,
} from "../src/shopifyInstall.ts";

test("only a single Shopify domain is accepted as an untrusted install hint", () => {
  assert.equal(
    parseShopifyInstallHint("?shop=Demo.MYSHOPIFY.COM"),
    "demo.myshopify.com",
  );
  assert.equal(parseShopifyInstallHint("?shop=demo.myshopify.com&shop=evil.myshopify.com"), null);
  assert.equal(parseShopifyInstallHint("?shop=demo.myshopify.com&returnTo=https://evil.com"), null);
  assert.equal(parseShopifyInstallHint("?shop=https://demo.myshopify.com"), null);
  assert.equal(parseShopifyInstallHint("?shop=demo.myshopify.com.evil.com"), null);
  assert.equal(parseShopifyInstallHint("?shop=demo.myshopify.com%2Fadmin"), null);
  assert.equal(parseShopifyInstallHint("?shop="), null);
});

test("installation returns to the verified shop and this app without leaking a claim code", () => {
  const shop = "synthetic.myshopify.com";
  const result = {
    connected: true, store_id: 42, shop_domain: shop,
    shopify_admin_url: `https://${shop}/admin/apps/${DIAGLOB_SHOPIFY_CLIENT_ID}`,
  };
  assert.equal(validatedShopifyInstallCompletion(result, 42, shop), result.shopify_admin_url);
  for (const changed of [
    { connected: false }, { store_id: 43 }, { shop_domain: "other.myshopify.com" },
    { shopify_admin_url: result.shopify_admin_url + "?code=private" },
    { shopify_admin_url: result.shopify_admin_url + "#private" },
    { shopify_admin_url: "https://evil.example/" },
    { shopify_admin_url: `https://${shop}/admin/apps/${"a".repeat(32)}` },
  ]) assert.throws(() => validatedShopifyInstallCompletion({ ...result, ...changed }, 42, shop));
});

test("the public frontend app identity stays aligned with Shopify TOML", () => {
  const toml = readFileSync(new URL("../../shopify.app.toml", import.meta.url), "utf8");
  assert.ok(toml.includes(`client_id = "${DIAGLOB_SHOPIFY_CLIENT_ID}"`));
});

test("merchant must select their eligible preexisting DIAGLOB store", () => {
  const stores = [
    { id: 1, active: true, shopify_domain: null },
    { id: 2, active: false, shopify_domain: null },
    { id: 3, active: true, shopify_domain: "different.myshopify.com" },
    { id: 4, active: true, shopify_domain: "DEMO.MYSHOPIFY.COM" },
  ];
  assert.deepEqual(
    eligibleShopifyInstallStores(stores, "demo.myshopify.com").map((x) => x.id),
    [1, 4],
  );
  assert.equal(eligibleShopifyInstallStores(stores, "else.myshopify.com").length, 1);
});

test("Shopify OAuth destination must be same-shop HTTPS and exact authorize path", () => {
  const url = "https://demo.myshopify.com/admin/oauth/authorize?client_id=test&state=synthetic";
  assert.equal(validatedShopifyAuthorizationUrl(url, "demo.myshopify.com"), url);
  for (const invalid of [
    "https://evil.example/admin/oauth/authorize?client_id=x&state=x",
    "http://demo.myshopify.com/admin/oauth/authorize?client_id=x&state=x",
    "https://demo.myshopify.com/admin/oauth/access_token?client_id=x&state=x",
    "https://demo.myshopify.com:444/admin/oauth/authorize?client_id=x&state=x",
    "https://demo.myshopify.com/admin/oauth/authorize?client_id=x",
  ]) {
    assert.throws(() => validatedShopifyAuthorizationUrl(invalid, "demo.myshopify.com"));
  }
});

test("verified post-OAuth shop can bootstrap exactly one active local store", () => {
  assert.deepEqual(
    buildPostOAuthStorePayload(
      "diaglob-poc.myshopify.com", " Diaglob POC ", "CO", ["CO", "MX"],
    ),
    {
      name: "Diaglob POC",
      country_code: "CO",
      shopify_domain: "diaglob-poc.myshopify.com",
      active: true,
    },
  );
});

test("post-OAuth store bootstrap rejects browser hints, malformed shops and unsupported markets", () => {
  for (const shop of [null, "", "https://diaglob-poc.myshopify.com", "other.example.com", "DIAGLOB-POC.myshopify.com"]) {
    assert.throws(
      () => buildPostOAuthStorePayload(shop, "Store", "CO", ["CO"]),
      /Shopify authorization is required/,
    );
  }

  for (const name of [" ", "x".repeat(151)]) {
    assert.throws(
      () => buildPostOAuthStorePayload("diaglob-poc.myshopify.com", name, "CO", ["CO"]),
      /Store name is required/,
    );
  }
  for (const country of ["", "co", "US", "CO2"]) {
    assert.throws(
      () => buildPostOAuthStorePayload("diaglob-poc.myshopify.com", "Store", country, ["CO", "MX"]),
      /Select a supported market/,
    );
  }
});

test("managed installation mode survives safe UTM parameters added to links", () => {
  assert.equal(parseShopifyInstallMode("?managed=1"), "managed");
  assert.equal(parseShopifyInstallMode("?managed=1&utm_source=chatgpt.com"), "managed");
  assert.equal(parseShopifyInstallMode("?managed=1&utm_source=chatgpt.com&utm_medium=referral"), "managed");
  assert.equal(parseShopifyInstallMode("?authorized=1&utm_source=chatgpt.com"), "authorized");
  assert.equal(parseShopifyInstallMode("?authorized=1"), "authorized");
});

test("tracking never authorizes an invalid, duplicate or ambiguous Shopify installation", () => {
  for (const invalid of [
    "?managed=0", "?managed=yes", "?managed=1&managed=1", "?managed=1&managed=0",
    "?managed=1&authorized=1", "?managed=1&shop=evil.myshopify.com",
    "?managed=1&next=https://evil.example",
    "?authorized=1&managed=1", "?authorized=1&authorized=1",
    "?utm_source=chatgpt.com", "", "?"+"x".repeat(1050),
  ]) {
    assert.equal(parseShopifyInstallMode(invalid), null, invalid);
  }
});

test("2.3.1: general store settings never ask for a Shopify domain", () => {
  const storesPage = readFileSync(new URL("../src/pages/StoresPage.tsx", import.meta.url), "utf8");
  assert.equal(storesPage.includes("value={form.shopify_domain}"), false);
  assert.equal(storesPage.includes("shopify_domain: form.shopify_domain"), false);
  assert.equal(storesPage.includes('placeholder="mitienda.myshopify.com"'), false);
  // Preserve existing identity as read-only: never erase it during a general edit.
  assert.ok(storesPage.includes("editingStore.shopify_domain || copy.noCommerceDomain"));
});

test("2.3.1: installation requires a verified Shopify grant, not URL hints", () => {
  const installPage = readFileSync(new URL("../src/pages/ShopifyInstallPage.tsx", import.meta.url), "utf8");
  const integrations = readFileSync(new URL("../src/components/StoreIntegrations.tsx", import.meta.url), "utf8");
  assert.ok(installPage.includes("const shop = authorizedGrant ? authorizedShop : null"));
  assert.equal(installPage.includes("parseShopifyInstallHint(location.search)"), false);
  assert.equal(/\bconnectShopify\(/.test(installPage), false);
  assert.equal(/\bconnectShopify\(/.test(integrations), false);
  assert.ok(integrations.includes("/shopify/install?managed=1"));
});
