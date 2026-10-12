/** Privacy-minimized Shopify -> Meta event mapping (no shopper PII).
 * Shopify event.id is stable; verified order IDs support future browser/server deduplication.
 * These transformations never claim attribution, and cannot be used as sales totals.
 */
export const EVENT_MAP = Object.freeze({
  page_viewed: "PageView",
  product_viewed: "ViewContent",
  product_added_to_cart: "AddToCart",
  checkout_started: "InitiateCheckout",
  checkout_completed: "Purchase",
});
const money = (v) => {
  if (v?.amount === null || v?.amount === undefined || v?.amount === "") return null;
  const amount = Number(v.amount);
  const currency = v?.currencyCode;
  if (!Number.isFinite(amount) || amount < 0 || !/^[A-Z]{3}$/.test(currency || "")) return null;
  return {value: amount, currency};
};
export function convertShopifyEvent(event) {
  const eventName = EVENT_MAP[event?.name];
  if (!eventName || typeof event.id !== "string" || event.id.length < 1 || event.id.length > 200) return null;
  let amount = null;
  let productId = null;
  if (event.name === "product_viewed") {
    const variant = event.data?.productVariant;
    amount = money(variant?.price);
    productId = variant?.product?.id || variant?.id;
  } else if (event.name === "product_added_to_cart") {
    const line = event.data?.cartLine;
    amount = money(line?.cost?.totalAmount || line?.merchandise?.price);
    productId = line?.merchandise?.product?.id || line?.merchandise?.id;
  } else if (event.name === "checkout_started" || event.name === "checkout_completed") {
    amount = money(event.data?.checkout?.totalPrice);
  }
  // On checkout_completed the order ID can be correlated with Shopify's
  // signed orders/create webhook. Event IDs alone cannot prove a purchase.
  // Fall back to the SDK event ID if checkout.order.id is unavailable.
  const rawOrder = event.name === "checkout_completed" ? event.data?.checkout?.order?.id : null;
  const match = typeof rawOrder === "string" || typeof rawOrder === "number"
    ? String(rawOrder).match(/^(?:gid:\/\/shopify\/Order\/)?([0-9]{1,30})$/)
    : null;
  const eventId = match ? "shopify:order:" + match[1] : "shopify:" + event.id;
  const data = {
    event_name: eventName,
    event_id: eventId,
    shopify_event: event.name,
    // Timestamp controlled by Shopify in the Web Pixel event; not proof of payment.
    event_time: event.timestamp,
  };
  if (amount) { data.value = amount.value; data.currency = amount.currency; }
  if (typeof productId === "string" && productId.length <= 120) data.content_ids = [productId];
  return data;
}
