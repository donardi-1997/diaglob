/** Copy into Shopify CLI-generated extensions/diaglob-meta-pixel/src/index.js.
 * This staging implementation NEVER injects a global fbq or scrapes DOM.
 * Shopify runs app pixels in a strict worker sandbox and owns consent gating.
 */
import {register} from "@shopify/web-pixels-extension";
import {convertShopifyEvent, EVENT_MAP} from "./mapping.mjs";
register(({analytics, init, customerPrivacy, settings}) => {
  // The Shopify customer-privacy declaration independently prevents callbacks
  // in consent-required regions until the browser visitor grants consent.
  const initialPrivacy = init?.customerPrivacy;
  let privacy = initialPrivacy;
  customerPrivacy?.subscribe?.("visitorConsentCollected", (evt) => {
    privacy = evt.customerPrivacy;
  });
  const pixelId = String(settings?.pixelId || "");
  const endpoint = String(settings?.collectorUrl || "");
  // A source key is a public routing identifier, not an authentication secret.
  const source = String(settings?.sourceId || "");
  const configured = /^[0-9]{8,30}$/.test(pixelId)
    && /^https:\/\/api\.diaglob\.tech\/api\/web-pixels\/collect$/.test(endpoint)
    && /^[a-f0-9-]{36}$/.test(source);
  // Server-side public collector and Shopify extension are not yet released.
  // OFF remains the only valid runtime value until explicit merchant activation.
  if (!configured || settings?.trackingEnabled !== "true") return;
  Object.keys(EVENT_MAP).forEach((shopifyEvent) => {
    analytics.subscribe(shopifyEvent, (event) => {
      if (privacy?.marketingAllowed !== true || privacy?.analyticsProcessingAllowed !== true
          || privacy?.saleOfDataAllowed === false) return;
      const data = convertShopifyEvent(event);
      if (!data) return;
      // No buyer email, name, IP or addresses. No merchant access tokens.
      void fetch(endpoint, {
        method: "POST",
        headers: {"Content-Type": "text/plain"},
        body: JSON.stringify({source_id: source, pixel_id: pixelId, ...data}),
        keepalive: true,
      }).catch(() => {});
    });
  });
});
