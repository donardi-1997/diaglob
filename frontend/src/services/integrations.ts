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
