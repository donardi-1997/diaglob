import { api } from "./api";

export interface InstagramConnectionStatus {
  connected: boolean;
  status: string;
  instagram_account_id: string | null;
  page_id: string | null;
  username: string | null;
  connected_at: string | null;
  last_error: string | null;
  webhook_url: string;
  webhook_ready: boolean;
  verify_token?: string | null;
}

export async function getInstagramStatus(storeId: number) {
  const response = await api.get<InstagramConnectionStatus>(
    `/api/stores/${storeId}/instagram`,
  );
  return response.data;
}

export async function connectInstagram(
  storeId: number,
  payload: {
    instagram_account_id: string;
    page_id?: string;
    access_token: string;
  },
) {
  const response = await api.post<InstagramConnectionStatus>(
    `/api/stores/${storeId}/instagram/connect`,
    payload,
  );
  return response.data;
}

export async function disconnectInstagram(storeId: number) {
  const response = await api.delete(
    `/api/stores/${storeId}/instagram/disconnect`,
  );
  return response.data;
}
