import { api } from "./api";
import type {
  ConversationDetail,
  ConversationListResponse,
  ConversationMode,
} from "../types/conversation";

export async function getConversations() {
  const response = await api.get<ConversationListResponse>(
    "/api/conversations",
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

