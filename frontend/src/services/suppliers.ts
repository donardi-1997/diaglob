import { api } from "./api";

export interface CJConnectionStatus {
  provider: "cj";
  connected: boolean;
  status: string;
  external_account_id: string | null;
  external_account_name: string | null;
  access_token_expires_at: string | null;
  refresh_token_expires_at: string | null;
  connected_at: string | null;
  last_sync_at: string | null;
  last_error: string | null;
}

export interface CJConnectionTestResult {
  ok: boolean;
  connected: boolean;
  provider: "cj";
  external_account_id: string | null;
  external_account_name: string | null;
  account_email: string | null;
  root: string | null;
  is_sandbox: boolean;
  qps_limit: number | null;
}

export interface CJProduct {
  provider: "cj";
  external_product_id: string;
  title: string;
  sku: string | null;
  image_url: string | null;
  supplier_cost_usd: string | number | null;
  suggested_sell_price: string | number | null;
  category_id: string | null;
  category_name: string | null;
  listed_count: number | null;
}

export interface CJVariant {
  provider: "cj";
  external_variant_id: string;
  external_product_id: string;
  title: string;
  sku: string | null;
  barcode: string | null;
  image_url: string | null;
  option: string | null;
  supplier_cost_usd: string | number | null;
  suggested_sell_price: string | number | null;
  weight_g: string | number | null;
  length_mm: string | number | null;
  width_mm: string | number | null;
  height_mm: string | number | null;
}

export interface CJStockWarehouse {
  warehouse_id: string;
  warehouse_name: string | null;
  country_code: string | null;
  total_inventory: number;
  cj_inventory: number;
  factory_inventory: number;
}

export interface CJStockResult {
  provider: "cj";
  external_variant_id: string;
  total_inventory: number;
  warehouses: CJStockWarehouse[];
}

export interface CJFreightOption {
  logistics_name: string | null;
  transit_time: string | null;
  price_usd: string | number | null;
  base_price_usd: string | number | null;
  taxes_fee_usd: string | number | null;
  clearance_fee_usd: string | number | null;
}

export interface CJFreightQuote {
  provider: "cj";
  origin_country_code: string;
  destination_country_code: string;
  items: { variant_id: string; quantity: number }[];
  options: CJFreightOption[];
}

export interface CJVariantMapping {
  provider: "cj";
  product_id: number;
  product_title: string;
  product_variant_id: number;
  shopify_variant_id: string | null;
  variant_title: string;
  sku: string | null;
  mapped: boolean;
  mapping_id: number | null;
  external_product_id: string | null;
  external_variant_id: string | null;
  external_sku: string | null;
  active: boolean;
  updated_at: string | null;
}

export interface CJVariantMappingList {
  provider: "cj";
  items: CJVariantMapping[];
  total: number;
  mapped: number;
  unmapped: number;
}

export async function getCJStatus(storeId: number) {
  const response = await api.get<CJConnectionStatus>(
    `/api/stores/${storeId}/suppliers/cj`,
  );
  return response.data;
}

export async function connectCJ(storeId: number, apiKey: string) {
  const response = await api.post(
    `/api/stores/${storeId}/suppliers/cj/connect`,
    { api_key: apiKey },
  );
  return response.data;
}

export async function testCJConnection(storeId: number) {
  const response = await api.post<CJConnectionTestResult>(
    `/api/stores/${storeId}/suppliers/cj/test`,
  );
  return response.data;
}

export async function disconnectCJ(storeId: number) {
  const response = await api.delete(
    `/api/stores/${storeId}/suppliers/cj/disconnect`,
  );
  return response.data;
}

export async function searchCJProducts(
  storeId: number,
  query: string,
  page = 1,
  limit = 20,
) {
  const params = new URLSearchParams({
    page: String(page),
    limit: String(limit),
  });
  if (query.trim()) params.set("query", query.trim());

  const response = await api.get<{
    provider: "cj";
    items: CJProduct[];
    page: number;
    limit: number;
    total: number | null;
    total_pages: number | null;
  }>(`/api/stores/${storeId}/suppliers/cj/products?${params.toString()}`);
  return response.data;
}

export async function getCJVariants(
  storeId: number,
  productId: string,
  countryCode?: string,
) {
  const params = new URLSearchParams();
  if (countryCode) params.set("country_code", countryCode.toUpperCase());
  const suffix = params.toString() ? `?${params.toString()}` : "";

  const response = await api.get<{
    provider: "cj";
    items: CJVariant[];
  }>(
    `/api/stores/${storeId}/suppliers/cj/products/${encodeURIComponent(productId)}/variants${suffix}`,
  );
  return response.data;
}

export async function getCJStock(storeId: number, variantId: string) {
  const response = await api.get<CJStockResult>(
    `/api/stores/${storeId}/suppliers/cj/variants/${encodeURIComponent(variantId)}/stock`,
  );
  return response.data;
}

export async function quoteCJFreight(
  storeId: number,
  input: {
    start_country_code: string;
    end_country_code: string;
    zip_code?: string;
    items: { variant_id: string; quantity: number }[];
  },
) {
  const response = await api.post<CJFreightQuote>(
    `/api/stores/${storeId}/suppliers/cj/freight/quote`,
    input,
  );
  return response.data;
}

export async function enableCJTrackingWebhook(storeId: number) {
  const response = await api.post(
    `/api/stores/${storeId}/suppliers/cj/webhooks/logistics/enable`,
  );
  return response.data;
}


export async function getCJVariantMappings(storeId: number) {
  const response = await api.get<CJVariantMappingList>(
    `/api/stores/${storeId}/suppliers/cj/mappings`,
  );
  return response.data;
}

export async function saveCJVariantMapping(
  storeId: number,
  productVariantId: number,
  input: {
    external_product_id: string;
    external_variant_id: string;
    external_sku?: string | null;
    active?: boolean;
  },
) {
  const response = await api.put<CJVariantMapping>(
    `/api/stores/${storeId}/suppliers/cj/mappings/${productVariantId}`,
    input,
  );
  return response.data;
}

export async function deleteCJVariantMapping(
  storeId: number,
  productVariantId: number,
) {
  const response = await api.delete(
    `/api/stores/${storeId}/suppliers/cj/mappings/${productVariantId}`,
  );
  return response.data;
}
