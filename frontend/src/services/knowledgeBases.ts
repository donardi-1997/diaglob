import { api } from "./api";

export interface KnowledgeBaseStore {
  id: number;
  name: string;
  country_code: string;
  currency: string;
}

export interface KnowledgeBaseAgent {
  id: number;
  name: string;
  role: string;
  active: boolean;
}

export interface KnowledgeBase {
  id: number;
  organization_id: number;
  name: string;
  scope: "organization" | "selected_stores";
  external_id: string | null;
  active: boolean;
  stores: KnowledgeBaseStore[];
  agents: KnowledgeBaseAgent[];
}

export interface KnowledgeBasePayload {
  name: string;
  scope: "organization" | "selected_stores";
  external_id?: string | null;
  active?: boolean;
  store_ids: number[];
}

export async function getKnowledgeBases() {
  const response = await api.get<{
    items: KnowledgeBase[];
    total: number;
  }>("/api/knowledge-bases");

  return response.data;
}

export async function createKnowledgeBase(
  payload: KnowledgeBasePayload,
) {
  const response = await api.post<KnowledgeBase>(
    "/api/knowledge-bases",
    payload,
  );

  return response.data;
}

export async function updateKnowledgeBase(
  id: number,
  payload: Partial<KnowledgeBasePayload>,
) {
  const response = await api.patch<KnowledgeBase>(
    `/api/knowledge-bases/${id}`,
    payload,
  );

  return response.data;
}
