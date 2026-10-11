export function parseShopifyHostedPricingReturn(search: string) {
  const params = new URLSearchParams(search);
  const shouldReverify = params.has("plan_handle");
  params.delete("plan_handle");
  params.delete("shop");
  return {
    shouldReverify,
    cleanedSearch: params.toString(),
  };
}
