import { apiRequest } from "./api";

export interface AgentApproval {
  id: number;
  tool_name: string;
  action: string;
  risk: string;
  confirmation: string;
  status: string;
}

export interface AgentToolCall {
  id: number;
  tool_name: string;
  title: string;
  description: string | null;
  status: string;
  approval: AgentApproval | null;
}

export interface AgentChatMessage {
  id: number;
  role: "user" | "assistant";
  text: string;
  created_at: string;
  tool_calls: AgentToolCall[];
}

export interface AgentChatSession {
  id: number;
  store_id: number;
  title: string;
  has_pending_turn: boolean;
  messages?: AgentChatMessage[];
  pending_actions?: AgentToolCall[];
}

export async function createAgentChatSession(
  storeId: number,
) {
  return apiRequest<AgentChatSession>(
    "/api/ai/chat/sessions",
    {
      method: "POST",
      storeId: String(storeId),
      body: JSON.stringify({
        store_id: storeId,
        context: {
          page: "mobile-copilot",
          platform: "mobile",
        },
      }),
    },
  );
}

export async function sendAgentChatMessage(
  sessionId: number,
  storeId: number,
  text: string,
) {
  return apiRequest<AgentChatSession>(
    `/api/ai/chat/sessions/${sessionId}/messages`,
    {
      method: "POST",
      storeId: String(storeId),
      body: JSON.stringify({
        text,
        context: {
          page: "mobile-copilot",
          platform: "mobile",
        },
      }),
    },
  );
}

export async function resolveApproval(
  sessionId: number,
  approvalId: number,
  storeId: number,
  action: "approve" | "cancel",
) {
  return apiRequest<AgentChatSession>(
    `/api/ai/chat/sessions/${sessionId}/approvals/${approvalId}/${action}`,
    {
      method: "POST",
      storeId: String(storeId),
    },
  );
}
