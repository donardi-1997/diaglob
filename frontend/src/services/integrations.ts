import { api } from "./api";


export interface CommerceConnectionStatus {
  connected: boolean;
  provider: string | null;
  external_store_url: string | null;
  status: string;
  connected_at: string | null;
  last_sync_at: string | null;
  last_error: string | null;
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
      verify_token: string;
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
