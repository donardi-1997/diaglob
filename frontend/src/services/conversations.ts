import { api } from "./api";
import type {
  ConversationDetail,
  ConversationListResponse,
  ConversationMode,
} from "../types/conversation";

export async function getConversations(storeId?: number) {
  const headers: Record<string, string> = {};

  if (storeId) {
    headers["X-Store-Id"] = String(storeId);
  } else {
    // Use global scope to get conversations from all stores
    headers["X-Diaglob-Global-Scope"] = "1";
  }

  const response = await api.get<ConversationListResponse>(
    "/api/conversations",
    { headers },
  );

  return response.data;
}

export async function getConversation(conversationId: number) {
  const response = await api.get<ConversationDetail>(
    `/api/conversations/${conversationId}`,
  );

  return response.data;
}

export async function setConversationMode(
  conversationId: number,
  mode: ConversationMode,
) {
  const response = await api.patch(
    `/api/conversations/${conversationId}/mode`,
    null,
    {
      params: {
        mode,
      },
    },
  );

  return response.data;
}

export async function sendConversationMessage(
  conversationId: number,
  text: string,
) {
  const response = await api.post(
    `/api/conversations/${conversationId}/messages`,
    {
      text,
      sender: "human",
    },
  );

  return response.data;
}

export async function sendWhatsAppMessage(
  conversationId: number,
  text: string,
) {
  const response = await api.post(
    `/api/conversations/${conversationId}/whatsapp/send`,
    {
      text,
      sender: "human",
    },
  );

  return response.data;
}

export async function getWhatsAppStatus(
  storeId: number,
) {
  const response = await api.get<{
    connected: boolean;
    phone_number_id: string | null;
  }>(
    `/api/stores/${storeId}/whatsapp`,
  );

  return response.data;
}

