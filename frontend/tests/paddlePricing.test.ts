import assert from "node:assert/strict";
import test from "node:test";

async function loadPricingHelpers() {
  try {
    return await import("../src/services/paddlePricing.ts");
  } catch {
    assert.fail("Paddle pricing helpers must be available to build checkout requests");
  }
}

test("price previews omit an unknown country so Paddle detects location", async () => {
  const { buildPaddlePricePreviewRequest } = await loadPricingHelpers();
  assert.deepEqual(
    buildPaddlePricePreviewRequest([
      { priceId: "pri_starter_month", quantity: 1 },
    ], null),
    { items: [{ priceId: "pri_starter_month", quantity: 1 }] },
  );
});

test("price previews pass a valid backend country to Paddle", async () => {
  const { buildPaddlePricePreviewRequest } = await loadPricingHelpers();
  assert.deepEqual(
    buildPaddlePricePreviewRequest([
      { priceId: "pri_starter_month", quantity: 1 },
    ], "CO"),
    {
      items: [{ priceId: "pri_starter_month", quantity: 1 }],
      address: { countryCode: "CO" },
    },
  );
});

test("Paddle display prices are returned formatted strings without conversion", async () => {
  const { mapPaddleFormattedTotals } = await loadPricingHelpers();
  assert.deepEqual(
    mapPaddleFormattedTotals([
      {
        price: { id: "pri_starter_month" },
        formattedTotals: { subtotal: "COP\u00a042.500,00", total: "COP\u00a050.575,00" },
      },
    ]),
    { pri_starter_month: "COP\u00a042.500,00" },
  );
});

test("checkout uses the selected price, one-page overlay, signed metadata, email, and welcome URL", async () => {
  const { buildPaddleCheckoutOptions } = await loadPricingHelpers();
  assert.deepEqual(
    buildPaddleCheckoutOptions({
      priceId: "pri_scale_year",
      customerEmail: "member@example.test",
      countryCode: "CO",
      customData: { organization_id: "42", checkout_signature: "signature" },
      origin: "https://diaglob.example",
    }),
    {
      items: [{ priceId: "pri_scale_year", quantity: 1 }],
      customer: {
        email: "member@example.test",
        address: { countryCode: "CO" },
      },
      customData: { organization_id: "42", checkout_signature: "signature" },
      settings: {
        displayMode: "overlay",
        variant: "one-page",
        successUrl: "https://diaglob.example/welcome",
      },
    },
  );
});
