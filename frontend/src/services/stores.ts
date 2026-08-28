import { api } from "./api";


export interface Store {
  id: number;
  name: string;
  slug: string;
  country_code: string;
  currency: string;
  timezone: string;
  default_language: string;
  shopify_domain: string | null;
  active: boolean;
}


export interface StoresResponse {
  items: Store[];
  total: number;
}


export interface StoreCreatePayload {
  name: string;
  country_code: string;
  currency?: string;
  timezone?: string;
  default_language?: string;
  shopify_domain?: string | null;
  active?: boolean;
}


export interface StoreUpdatePayload {
  name?: string;
  currency?: string;
  timezone?: string;
  default_language?: string;
  shopify_domain?: string | null;
  active?: boolean;
}


const globalHeaders = {
  "X-Diaglob-Global-Scope": "1",
};


export async function getStores() {
  const response =
    await api.get<StoresResponse>(
      "/api/stores",
      {
        headers: globalHeaders,
      },
    );

  return response.data;
}


export async function getStoresForManagement() {
  const response =
    await api.get<StoresResponse>(
      "/api/stores",
      {
        params: {
          include_suspended: true,
        },

        headers: globalHeaders,
      },
    );

  return response.data;
}


export async function createStore(
  payload: StoreCreatePayload,
) {
  const response =
    await api.post<Store>(
      "/api/stores",
      payload,
      {
        headers: globalHeaders,
      },
    );

  return response.data;
}


export async function updateStore(
  storeId: number,
  payload: StoreUpdatePayload,
) {
  const response =
    await api.patch<Store>(
      `/api/stores/${storeId}`,
      payload,
      {
        headers: globalHeaders,
      },
    );

  return response.data;
}


export async function deleteStore(
  storeId: number,
) {
  const response =
    await api.delete(
      `/api/stores/${storeId}`,
      {
        headers: globalHeaders,
      },
    );

  return response.data;
}
