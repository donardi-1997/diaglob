import { api } from "./api";

export interface AgentStore {
  id: number;
  name: string;
  country_code: string;
  currency: string;
}

export interface AgentKnowledgeBase {
  id: number;
  name: string;
  scope: string;
  active: boolean;
}

export interface Agent {
  id: number;
  organization_id: number;
  name: string;
  role: string;
  active: boolean;
  stores: AgentStore[];
  knowledge_bases: AgentKnowledgeBase[];
}

export interface AgentPayload {
  name: string;
  role: string;
  active?: boolean;
  store_ids: number[];
  knowledge_base_ids: number[];
}

export async function getAgents() {
  const response = await api.get<{
    items: Agent[];
    total: number;
  }>("/api/agents");

  return response.data;
}

export async function createAgent(
  payload: AgentPayload,
) {
  const response = await api.post<Agent>(
    "/api/agents",
    payload,
  );

  return response.data;
}

export async function updateAgent(
  id: number,
  payload: Partial<AgentPayload>,
) {
  const response = await api.patch<Agent>(
    `/api/agents/${id}`,
    payload,
  );

  return response.data;
}
