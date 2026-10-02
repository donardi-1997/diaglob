import { api } from "./api";

export interface AgentApproval {
  id: number;
  tool_name: string;
  action: string;
  risk: "read" | "write" | "external" | "financial" | "destructive";
  confirmation: "none" | "simple" | "critical";
  status: "pending" | "approved" | "consumed" | "cancelled" | "expired";
  store_id: number;
  arguments: Record<string, unknown>;
  expires_at: string;
  approved_at: string | null;
  consumed_at: string | null;
}

export interface AgentToolCall {
  id: number;
  tool_use_id: string;
  tool_name: string;
  title: string;
  description: string | null;
  arguments: Record<string, unknown>;
  status: string;
  result: Record<string, unknown> | null;
  approval: AgentApproval | null;
  created_at: string;
}

export interface AgentChatMessage {
  id: number;
  role: "user" | "assistant";
  text: string;
  model_id: string | null;
  billable: boolean;
  created_at: string;
  tool_calls: AgentToolCall[];
}

export interface AgentChatSession {
  id: number;
  store_id: number;
  title: string;
  context: Record<string, unknown>;
  status: string;
  has_pending_turn: boolean;
  created_at: string;
  updated_at: string;
  messages?: AgentChatMessage[];
  pending_actions?: AgentToolCall[];
}

export async function listAgentChatSessions(storeId: number) {
  const response = await api.get<{ items: AgentChatSession[]; total: number }>(
    "/api/ai/chat/sessions",
    { params: { store_id: storeId } },
  );
  return response.data;
}

export async function createAgentChatSession(
  storeId: number,
  context: Record<string, unknown> = {},
) {
  const response = await api.post<AgentChatSession>(
    "/api/ai/chat/sessions",
    {
      store_id: storeId,
      context,
    },
  );
  return response.data;
}

export async function getAgentChatSession(sessionId: number) {
  const response = await api.get<AgentChatSession>(
    `/api/ai/chat/sessions/${sessionId}`,
  );
  return response.data;
}

export async function archiveAgentChatSession(sessionId: number) {
  const response = await api.delete<AgentChatSession>(
    `/api/ai/chat/sessions/${sessionId}`,
  );
  return response.data;
}

export async function sendAgentChatMessage(
  sessionId: number,
  text: string,
  context: Record<string, unknown> = {},
) {
  const response = await api.post<AgentChatSession>(
    `/api/ai/chat/sessions/${sessionId}/messages`,
    { text, context },
  );
  return response.data;
}

export async function approveAgentChatAction(
  sessionId: number,
  approvalId: number,
) {
  const response = await api.post<AgentChatSession>(
    `/api/ai/chat/sessions/${sessionId}/approvals/${approvalId}/approve`,
  );
  return response.data;
}

export async function cancelAgentChatAction(
  sessionId: number,
  approvalId: number,
) {
  const response = await api.post<AgentChatSession>(
    `/api/ai/chat/sessions/${sessionId}/approvals/${approvalId}/cancel`,
  );
  return response.data;
}
