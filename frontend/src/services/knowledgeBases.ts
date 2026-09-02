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

export type KnowledgeBaseProvisioningStatus =
  | "pending"
  | "provisioning"
  | "retrying"
  | "ready"
  | "failed"
  | "deleting";

export type KnowledgeBaseProvisioningStage =
  | "queued"
  | "creating_vector_index"
  | "creating_knowledge_base"
  | "creating_data_source"
  | "finalizing"
  | "retrying"
  | "ready"
  | "failed"
  | "deleting";

export interface KnowledgeBase {
  id: number;
  organization_id: number;
  name: string;
  scope: "organization" | "selected_stores";
  external_id: string | null;
  external_status: KnowledgeBaseProvisioningStatus;
  external_last_error: string | null;
  provisioning_stage: KnowledgeBaseProvisioningStage | null;
  provisioning_started_at: string | null;
  provisioning_stage_started_at: string | null;
  active: boolean;
  stores: KnowledgeBaseStore[];
  agents: KnowledgeBaseAgent[];
}

export interface KnowledgeBasePayload {
  name: string;
  scope: "organization" | "selected_stores";
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

export async function retryKnowledgeBaseProvisioning(
  id: number,
) {
  const response = await api.post<KnowledgeBase>(
    `/api/knowledge-bases/${id}/retry-provisioning`,
  );

  return response.data;
}

export async function deleteKnowledgeBase(id: number) {
  await api.delete(`/api/knowledge-bases/${id}`);
}
