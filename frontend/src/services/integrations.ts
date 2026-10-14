import { api } from "./api";


export interface CommerceConnectionStatus {
  connected: boolean;
  provider: string | null;
  external_store_url: string | null;
  status: string;
  connected_at: string | null;
  last_sync_at: string | null;
  last_error: string | null;
  dropi_detection: {
    status: "detected" | "not_detected";
    label: string;
    evidence: string[];
  };
}


export interface DropiConnectionStatus {
  connected: boolean;
  status: string;
  external_store_id: string | null;
  api_url: string | null;
  webhook_url: string | null;
  connected_at: string | null;
  last_sync_at: string | null;
  last_error: string | null;
  access_mode: "read_only";
  orders_write_enabled: false;
  shopify_dropify_coexistence: string;
}


export async function getCommerceStatus(
  storeId: number,
) {
  const response =
    await api.get<CommerceConnectionStatus>(
      `/api/stores/${storeId}/commerce`,
    );

  return response.data;
}


export async function connectShopify(
  storeId: number,
  shopDomain: string,
) {
  const response =
    await api.post<{
      ok: boolean;
      provider: string;
      store_id: number;
      shop_domain: string;
      expires_in_seconds: number;
      authorization_url: string;
    }>(
      `/api/stores/${storeId}/shopify/connect`,
      {
        shop_domain: shopDomain,
      },
    );

  return response.data;
}


export async function reauthorizeShopify(
  storeId: number,
) {
  const response =
    await api.post<{
      ok: boolean;
      provider: string;
      store_id: number;
      shop_domain: string;
      expires_in_seconds: number;
      authorization_url: string;
      reauthorization: boolean;
    }>(
      `/api/stores/${storeId}/shopify/reauthorize`,
    );

  return response.data;
}


export async function disconnectShopify(
  storeId: number,
) {
  const response =
    await api.delete<{
      ok: boolean;
      connected: boolean;
      store_id: number;
    }>(
      `/api/stores/${storeId}/shopify/disconnect`,
    );

  return response.data;
}


export interface ShopifyTestResult {
  connected: boolean;
  shop_name: string;
  shop_domain: string;
  currency: string;
  error?: string;
}


export async function testShopifyConnection(
  storeId: number,
) {
  const response =
    await api.post<ShopifyTestResult>(
      `/api/stores/${storeId}/shopify/test`,
    );

  return response.data;
}


export interface ShopifySyncResult {
  ok: boolean;
  fetched: number;
  created: number;
  updated: number;
  failed: number;
  error?: string;
}


export async function syncShopifyProducts(
  storeId: number,
) {
  const response =
    await api.post<ShopifySyncResult>(
      `/api/stores/${storeId}/shopify/sync/products`,
    );

  return response.data;
}


export interface OrderItem {
  id: number;
  title: string;
  sku: string | null;
  quantity: number;
  unit_price: number;
  currency: string;
  shopify_variant_id: string | null;
}


export interface Order {
  id: number;
  order_number: string;
  total_amount: number;
  currency: string;
  financial_status: string | null;
  fulfillment_status: string | null;
  source: string | null;
  invoice_url: string | null;
  shopify_draft_order_id: string | null;
  note: string | null;
  created_at: string | null;
  items: OrderItem[];
}


export interface OrderCreateResult {
  ok: boolean;
  idempotent: boolean;
  order_id: number;
  status: string;
  shopify_draft_order_id: string | null;
  invoice_url: string | null;
  total_amount: number;
  currency: string;
  order_number: string;
}


export async function createShopifyOrder(
  storeId: number,
  items: {
    variant_local_id: number;
    quantity: number;
  }[],
  options?: {
    customer_email?: string;
    customer_name?: string;
    note?: string;
    idempotency_key?: string;
  },
) {
  const response =
    await api.post<OrderCreateResult>(
      `/api/stores/${storeId}/shopify/orders`,
      {
        items,
        ...options,
      },
    );

  return response.data;
}


export async function listShopifyOrders(
  storeId: number,
) {
  const response =
    await api.get<{
      items: Order[];
      total: number;
    }>(
      `/api/stores/${storeId}/shopify/orders`,
    );

  return response.data;
}


export async function getShopifyOrder(
  storeId: number,
  orderId: number,
) {
  const response =
    await api.get<Order>(
      `/api/stores/${storeId}/shopify/orders/${orderId}`,
    );

  return response.data;
}


export async function getDropiStatus(
  storeId: number,
) {
  const response =
    await api.get<DropiConnectionStatus>(
      `/api/stores/${storeId}/dropi`,
    );

  return response.data;
}


export async function connectDropi(
  storeId: number,
  apiToken: string,
) {
  const response =
    await api.post<{
      ok: boolean;
      connected: boolean;
      store_id: number;
      status: string;
      webhook_url: string;
    }>(
      `/api/stores/${storeId}/dropi/connect`,
      {
        api_token: apiToken,
      },
    );

  return response.data;
}


export async function disconnectDropi(
  storeId: number,
) {
  const response =
    await api.delete<{
      ok: boolean;
      connected: boolean;
      store_id: number;
    }>(
      `/api/stores/${storeId}/dropi/disconnect`,
    );

  return response.data;
}



export interface DropiCatalogPreview {
  country_code: string;
  total_returned: number;
  items: Array<{
    id: string | number | null;
    name: string | null;
    sku: string | null;
    type: string | null;
    stock: number | null;
  }>;
}

export async function testDropiConnection(storeId: number) {
  const response = await api.post<DropiConnectionStatus & {
    capabilities: {
      catalog_preview: boolean;
      order_creation: boolean;
      tracking: boolean;
    };
  }>(`/api/stores/${storeId}/dropi/test`);
  return response.data;
}

export async function previewDropiCatalog(storeId: number, limit = 5) {
  const response = await api.get<DropiCatalogPreview>(
    `/api/stores/${storeId}/dropi/preview/products`,
    { params: { limit } },
  );
  return response.data;
}




export interface DropiCatalogMapping {
  product_variant_id: number;
  shopify_variant_id: string | null;
  shopify_product_id: string | null;
  shopify_product_title: string;
  shopify_sku: string | null;
  dropi_variant_id: string;
  sku_check: "match" | "different" | "unknown";
  stock_check: "match" | "different" | "unknown";
}

export interface DropiCatalogProduct {
  id: string | null;
  name: string | null;
  sku: string | null;
  type: string | null;
  stock: number | null;
  variants: Array<{ id: string | null; sku: string | null; stock: number | null }>;
  variants_in_page: boolean;
  variants_truncated: boolean;
  shopify_mappings: DropiCatalogMapping[];
  mapping_status: "linked" | "unmapped";
  differences_detected: boolean;
}

export interface DropiCatalogPage {
  provider: "dropi";
  country_code: string;
  access_mode: "read_only";
  shopify_write_performed: false;
  page: number;
  limit: number;
  query: string;
  items: DropiCatalogProduct[];
  returned: number;
  has_more: boolean;
  next_page: number | null;
  total: null;
  unmapped_products: number;
  products_with_differences: number;
}

export async function searchDropiCatalog(
  storeId: number,
  page = 1,
  query = "",
  limit = 20,
) {
  const response = await api.get<DropiCatalogPage>(
    `/api/stores/${storeId}/dropi/catalog`,
    { params: { page, query, limit } },
  );
  return response.data;
}

export interface DropiInventoryInspection {
  provider: "dropi";
  access_mode: "read_only";
  stock_synced_to_shopify: false;
  item: {
    id: string | number | null;
    name: string | null;
    sku: string | null;
    type: string | null;
    stock: number | null;
    variations: Array<{
      id: string | number | null;
      sku: string | null;
      stock: number | null;
    }>;
  };
}

export async function inspectDropiProduct(storeId: number, productId: string) {
  const response = await api.get<DropiInventoryInspection>(
    `/api/stores/${storeId}/dropi/products/${encodeURIComponent(productId)}`,
  );
  return response.data;
}


export interface DropiVariantMapping {
  provider: "dropi";
  product_id: number;
  product_title: string;
  product_variant_id: number;
  shopify_variant_id: string | null;
  variant_title: string;
  sku: string | null;
  mapped: boolean;
  external_product_id: string | null;
  external_variant_id: string | null;
  external_sku: string | null;
  active: boolean;
}

export interface DropiMappings {
  provider: "dropi";
  items: DropiVariantMapping[];
  total: number;
  mapped: number;
  unmapped: number;
}

export async function listDropiMappings(storeId: number) {
  const response = await api.get<DropiMappings>(`/api/stores/${storeId}/dropi/mappings`);
  return response.data;
}

export async function saveDropiMapping(
  storeId: number,
  variantId: number,
  payload: { external_product_id: string; external_variant_id: string; external_sku?: string; active?: boolean },
) {
  const response = await api.put<DropiVariantMapping>(
    `/api/stores/${storeId}/dropi/mappings/${variantId}`,
    payload,
  );
  return response.data;
}

export async function deleteDropiMapping(storeId: number, variantId: number) {
  const response = await api.delete<{ ok: boolean }>(
    `/api/stores/${storeId}/dropi/mappings/${variantId}`,
  );
  return response.data;
}

export interface DropiOrderReadiness {
  provider: "dropi";
  order_id: number;
  shopify_order_id: string | null;
  order_number: string;
  dry_run: boolean;
  ready_for_provider_contract_test: boolean;
  can_send_to_dropi: false;
  idempotency_key: string;
  rate_type: string;
  missing_shipping_fields: string[];
  blockers: string[];
  items: Array<{
    order_item_id: number;
    shopify_variant_id: string | null;
    sku: string | null;
    quantity: number;
    mapped: boolean;
    dropi_product_id: string | null;
    dropi_variant_id: string | null;
  }>;
}

export async function getDropiOrderReadiness(storeId: number, orderId: number) {
  const response = await api.get<DropiOrderReadiness>(
    `/api/stores/${storeId}/dropi/orders/${orderId}/readiness`,
  );
  return response.data;
}

export interface WhatsAppConnectionStatus {
  connected: boolean;
  status: string;
  phone_number_id: string | null;
  business_account_id: string | null;
  verify_token: string | null;
  connected_at: string | null;
  last_error: string | null;
}


export async function getWhatsAppStatus(
  storeId: number,
) {
  const response =
    await api.get<WhatsAppConnectionStatus>(
      `/api/stores/${storeId}/whatsapp`,
    );

  return response.data;
}


export async function connectWhatsApp(
  storeId: number,
  phoneNumberId: string,
  businessAccountId: string,
  accessToken: string,
) {
  const response =
    await api.post<{
      ok: boolean;
      connected: boolean;
      store_id: number;
      status: string;
      phone_number_id: string;
      verify_token: string | null;
    }>(
      `/api/stores/${storeId}/whatsapp/connect`,
      {
        phone_number_id: phoneNumberId,
        business_account_id: businessAccountId,
        access_token: accessToken,
      },
    );

  return response.data;
}


export async function disconnectWhatsApp(
  storeId: number,
) {
  const response =
    await api.delete<{
      ok: boolean;
      connected: boolean;
      store_id: number;
    }>(
      `/api/stores/${storeId}/whatsapp/disconnect`,
    );

  return response.data;
}


export interface CommerceSummary {
  connected: boolean;
  provider: string | null;
  total_products: number;
  total_variants: number;
  total_orders: number;
  orders_by_status: {
    pending: number;
    created: number;
    failed: number;
    unknown: number;
  };
  total_order_value: number;
  currency: string;
  recent_orders: {
    id: number;
    order_number: string;
    total_amount: number;
    currency: string;
    financial_status: string | null;
    source: string | null;
    external_creation_status: string | null;
    created_at: string | null;
  }[];
  recent_products: {
    id: number;
    title: string;
    image_url: string | null;
    active: boolean;
    updated_at: string | null;
  }[];
}


export async function getCommerceSummary(
  storeId: number,
) {
  const response =
    await api.get<CommerceSummary>(
      `/api/stores/${storeId}/commerce/summary`,
    );

  return response.data;
}


export interface CommerceProductVariant {
  id: number;
  shopify_variant_id: string | null;
  title: string;
  sku: string | null;
  barcode: string | null;
  price: number;
  currency: string;
  inventory_quantity: number;
  available: boolean;
}


export interface CommerceProduct {
  id: number;
  organization_id: number;
  store_id: number;
  shopify_product_id: string | null;
  title: string;
  handle: string | null;
  description: string;
  image_url: string | null;
  vendor: string | null;
  product_type: string | null;
  active: boolean;
  store: {
    id: number;
    name: string;
    country_code: string;
    currency: string;
  } | null;
  variants: CommerceProductVariant[];
}


export async function listCommerceProducts(
  storeId: number,
  q?: string,
) {
  const params = new URLSearchParams();

  if (q) {
    params.set("q", q);
  }

  const url =
    `/api/stores/${storeId}/commerce/products`
    + (params.toString()
      ? `?${params.toString()}`
      : "");

  const response =
    await api.get<{
      items: CommerceProduct[];
      total: number;
    }>(url);

  return response.data;
}


export interface CommerceOrderItem {
  id: number;
  title: string;
  sku: string | null;
  quantity: number;
  unit_price: number;
  currency: string;
  shopify_variant_id: string | null;
}


export interface CommerceOrder {
  id: number;
  order_number: string;
  total_amount: number;
  currency: string;
  financial_status: string | null;
  fulfillment_status: string | null;
  source: string | null;
  invoice_url: string | null;
  shopify_draft_order_id: string | null;
  external_creation_status: string | null;
  note: string | null;
  created_at: string | null;
  items: CommerceOrderItem[];
}


export async function listCommerceOrders(
  storeId: number,
) {
  const response =
    await api.get<{
      items: CommerceOrder[];
      total: number;
    }>(
      `/api/stores/${storeId}/commerce/orders`,
    );

  return response.data;
}


// ============================================================
// NUVEMSHOP
// ============================================================


export interface NuvemshopConnectionStatus {
  connected: boolean;
  status: string;
  nuvemshop_store_id: string | null;
  store_name: string | null;
  currency: string | null;
  connected_at: string | null;
  last_sync_at: string | null;
  last_error: string | null;
}


export async function getNuvemshopStatus(
  storeId: number,
) {
  const response =
    await api.get<NuvemshopConnectionStatus>(
      `/api/stores/${storeId}/nuvemshop/status`,
    );

  return response.data;
}


export async function connectNuvemshop(
  storeId: number,
) {
  const response =
    await api.post<{
      authorization_url: string;
      state: string;
    }>(
      `/api/stores/${storeId}/nuvemshop/connect`,
    );

  return response.data;
}


export async function disconnectNuvemshop(
  storeId: number,
) {
  const response =
    await api.delete<{
      ok: boolean;
      connected: boolean;
      store_id: number;
    }>(
      `/api/stores/${storeId}/nuvemshop/disconnect`,
    );

  return response.data;
}


export async function syncNuvemshopProducts(
  storeId: number,
) {
  const response =
    await api.post<{
      ok: boolean;
      fetched: number;
      created: number;
      updated: number;
      failed: number;
    }>(
      `/api/stores/${storeId}/nuvemshop/sync/products`,
    );

  return response.data;
}


export async function syncNuvemshopOrders(
  storeId: number,
) {
  const response =
    await api.post<{
      ok: boolean;
      fetched: number;
      created: number;
      updated: number;
      failed: number;
    }>(
      `/api/stores/${storeId}/nuvemshop/sync/orders`,
    );

  return response.data;
}


// ============================================================
// PAYMENT PROVIDERS
// ============================================================


export interface PaymentProviderInfo {
  code: string;
  name: string;
  payment_methods: string[];
  supports_webhooks: boolean;
  supports_reversals: boolean;
}


export interface PaymentConnectionStatus {
  connected: boolean;
  provider: string;
  status: string;
  environment: string | null;
  merchant_reference: string | null;
  connected_at: string | null;
  last_error: string | null;
}


export interface PaymentTransaction {
  id: number;
  provider: string;
  status: string;
  amount: string;
  currency: string;
  payment_method: string;
  provider_transaction_id: string | null;
  order_id: number | null;
  customer_phone: string | null;
  provider_status: string | null;
  expires_at: string | null;
  paid_at: string | null;
  created_at: string | null;
}


export async function getPaymentProviders(
  storeId: number,
) {
  const response =
    await api.get<{
      store_id: number;
      providers: PaymentProviderInfo[];
    }>(
      `/api/stores/${storeId}/payments/providers`,
    );

  return response.data;
}


export async function getPaymentStatus(
  storeId: number,
  provider: string,
) {
  const response =
    await api.get<PaymentConnectionStatus>(
      `/api/stores/${storeId}/payments/${provider}/status`,
    );

  return response.data;
}


export async function connectPayment(
  storeId: number,
  provider: string,
  data: {
    environment: string;
    client_id: string;
    client_secret: string;
    webhook_secret?: string;
    merchant_reference?: string;
  },
) {
  const response =
    await api.post<{
      ok: boolean;
      connected: boolean;
      provider: string;
      status: string;
      environment: string;
    }>(
      `/api/stores/${storeId}/payments/${provider}/connect`,
      data,
    );

  return response.data;
}


export async function disconnectPayment(
  storeId: number,
  provider: string,
) {
  const response =
    await api.delete<{
      ok: boolean;
      connected: boolean;
      provider: string;
    }>(
      `/api/stores/${storeId}/payments/${provider}/disconnect`,
    );

  return response.data;
}


export async function createPayment(
  storeId: number,
  data: {
    provider: string;
    amount?: number;
    currency?: string;
    customer_phone: string;
    idempotency_key?: string;
    order_id?: number;
    payment_method?: string;
  },
) {
  const response =
    await api.post<PaymentTransaction>(
      `/api/stores/${storeId}/payments`,
      data,
    );

  return response.data;
}


export async function getPayment(
  storeId: number,
  paymentId: number,
) {
  const response =
    await api.get<PaymentTransaction>(
      `/api/stores/${storeId}/payments/${paymentId}`,
    );

  return response.data;
}


export async function reconcilePayment(
  storeId: number,
  paymentId: number,
) {
  const response =
    await api.post<PaymentTransaction>(
      `/api/stores/${storeId}/payments/${paymentId}/reconcile`,
    );

  return response.data;
}


export async function cancelPayment(
  storeId: number,
  paymentId: number,
) {
  const response =
    await api.post<PaymentTransaction>(
      `/api/stores/${storeId}/payments/${paymentId}/cancel`,
    );

  return response.data;
}


export async function reversePayment(
  storeId: number,
  paymentId: number,
  reason?: string,
) {
  const response =
    await api.post<PaymentTransaction>(
      `/api/stores/${storeId}/payments/${paymentId}/reverse`,
      { reason: reason || "Merchant requested reversal" },
    );

  return response.data;
}


/** OAuth-first Shopify handoff: cookie remains HttpOnly on the backend. */
export async function getPendingShopifyInstall() {
  const response = await api.get<{
    pending: boolean;
    shop_domain: string | null;
  }>("/api/shopify/install/pending", { withCredentials: true });
  return response.data;
}

export async function claimPendingShopifyInstall(storeId: number) {
  const response = await api.post<{
    connected: boolean;
    store_id: number;
    shop_domain: string;
  }>(
    `/api/stores/${storeId}/shopify/install/claim`,
    {},
    { withCredentials: true },
  );
  return response.data;
}


/** Merchant measurement configuration only; no Pixel/CAPI deployment. */
export interface MetaPixelSettingsStatus {
  store_id: number;
  configured: boolean;
  pixel_id: string | null;
  existing_tracking: "unknown" | "none" | "shopify_meta" | "manual_pixel";
  enabled: boolean;
  status: "not_configured" | "awaiting_extension" | "provisioned";
  extension_installed: boolean;
  duplicate_tracking_risk: "unknown" | "high" | "none_reported";
}

export async function getStoreMetaPixel(storeId: number) {
  const response = await api.get<MetaPixelSettingsStatus>(
    `/api/stores/${storeId}/meta-pixel`,
  );
  return response.data;
}

export async function saveStoreMetaPixel(
  storeId: number,
  pixelId: string,
  existingTracking: MetaPixelSettingsStatus["existing_tracking"],
) {
  const response = await api.put<MetaPixelSettingsStatus>(
    `/api/stores/${storeId}/meta-pixel`,
    { pixel_id: pixelId, existing_tracking: existingTracking },
  );
  return response.data;
}

export async function removeStoreMetaPixel(storeId: number) {
  const response = await api.delete<MetaPixelSettingsStatus>(
    `/api/stores/${storeId}/meta-pixel`,
  );
  return response.data;
}


export interface MetaPixelReadiness {
  can_provision: boolean;
  blockers: string[];
  events_active: false;
}

/** Admin-only staging. Provisioning never starts transmitting customer events. */
export async function getMetaPixelReadiness(storeId: number) {
  const response = await api.get<MetaPixelReadiness>(
    `/api/stores/${storeId}/meta-pixel/readiness`,
  );
  return response.data;
}

export async function provisionMetaPixel(storeId: number) {
  const response = await api.post<{
    provisioned: boolean; events_active: false; web_pixel_gid: string;
  }>(`/api/stores/${storeId}/meta-pixel/provision`);
  return response.data;
}

export async function unprovisionMetaPixel(storeId: number) {
  const response = await api.post<{
    provisioned: boolean; events_active: false;
  }>(`/api/stores/${storeId}/meta-pixel/unprovision`);
  return response.data;
}


export async function verifyStoreMetaPixelOnShopify(storeId: number) {
  const response = await api.get<{
    verified: boolean;
    reason: string;
    events_active: false;
  }>(`/api/stores/${storeId}/meta-pixel/verify-remote`);
  return response.data;
}


export interface WhatsAppDiagnosticStatus {
  configured: boolean;
  provider_verified: boolean;
  waba_subscription_verified: boolean;
  webhook_signature_ready: boolean;
  webhook_verify_configured: boolean;
  errors: string[];
}

/** Read-only provider check. Does not send messages or subscribe the WABA. */
export async function getWhatsAppDiagnostics(storeId: number) {
  const response = await api.get<WhatsAppDiagnosticStatus>(
    `/api/stores/${storeId}/whatsapp/diagnostics`,
  );
  return response.data;
}
