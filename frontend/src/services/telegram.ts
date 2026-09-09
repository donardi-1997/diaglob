import { api } from "./api";

export interface TelegramConnectionStatus {
  connected: boolean;
  status: string;
  bot_id: number | null;
  bot_username: string | null;
  bot_name: string | null;
  connected_at: string | null;
  last_error: string | null;
}

export async function getTelegramStatus(storeId: number) {
  const response = await api.get<TelegramConnectionStatus>(
    `/api/stores/${storeId}/telegram`,
  );
  return response.data;
}

export async function connectTelegram(storeId: number, botToken: string) {
  const response = await api.post<{
    ok: boolean;
    connected: boolean;
    store_id: number;
    status: string;
    bot_id: number;
    bot_username: string | null;
    bot_name: string | null;
  }>(
    `/api/stores/${storeId}/telegram/connect`,
    { bot_token: botToken },
  );
  return response.data;
}

export async function disconnectTelegram(storeId: number) {
  const response = await api.delete<{
    ok: boolean;
    connected: boolean;
    store_id: number;
  }>(`/api/stores/${storeId}/telegram/disconnect`);
  return response.data;
}

export async function sendTelegramMessage(
  conversationId: number,
  text: string,
) {
  const response = await api.post<{
    ok: boolean;
    message_id: number;
    external_message_id: string | null;
  }>(
    `/api/conversations/${conversationId}/telegram/send`,
    { text, sender: "human" },
  );
  return response.data;
}
