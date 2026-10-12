import assert from "node:assert/strict";
import test from "node:test";

import {
  buildPostOAuthStorePayload,
  eligibleShopifyInstallStores,
  parseShopifyInstallHint,
  validatedShopifyAuthorizationUrl,
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
