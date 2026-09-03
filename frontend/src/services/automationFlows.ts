import { api } from "./api";

export interface AutomationFlow {
  id: number;
  name: string;
  status: "draft" | "active" | "paused" | "archived";
  description: string | null;
  current_version_id: number | null;
  active_version_id: number | null;
  created_by: number | null;
  created_at: string | null;
  updated_at: string | null;
  current_version?: AutomationFlowVersion;
}

export interface AutomationFlowVersion {
  id: number;
  flow_id: number;
  version_number: number;
  graph: Record<string, unknown>;
  published_at: string | null;
  activated_at: string | null;
  created_at: string | null;
}

export interface AutomationFlowRun {
  id: number;
  flow_id: number;
  flow_version_id: number;
  status: "pending" | "running" | "completed" | "partial" | "failed";
  trigger_key: string | null;
  total_recipients: number;
  completed_recipients: number;
  failed_recipients: number;
  started_at: string | null;
  completed_at: string | null;
  created_at: string | null;
  recipients?: AutomationFlowRecipient[];
}

export interface AutomationFlowRecipient {
  id: number;
  flow_run_id: number;
  customer_id: number;
  status: string;
  current_node_id: string | null;
  next_action_at: string | null;
  attempt_count: number;
  error_code: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface AutomationFlowRecipientDetail extends AutomationFlowRecipient {
  node_executions: NodeExecution[];
}

export interface NodeExecution {
  id: number;
  node_id: string;
  node_type: string;
  status: string;
  outcome: string | null;
  provider_message_id: string | null;
  error_code: string | null;
  error_message: string | null;
  metadata: Record<string, unknown> | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface FlowSimulationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  summary?: {
    total_nodes: number;
    message_nodes: number;
    wait_nodes: number;
    condition_nodes: number;
    end_nodes: number;
  };
}

export interface FlowCreatePayload {
  name: string;
  description?: string;
  graph?: Record<string, unknown>;
}

export interface FlowUpdatePayload {
  name?: string;
  description?: string;
  graph?: Record<string, unknown>;
}

export interface FlowRunCreatePayload {
  customer_ids: number[];
  trigger_key?: string;
}

export interface FlowRecipientPage {
  items: AutomationFlowRecipient[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

export async function listFlows(storeId: number, status?: string) {
  const params = status ? `?status=${status}` : "";
  const response = await api.get<AutomationFlow[]>(`/api/stores/${storeId}/automation-flows${params}`);
  return response.data;
}

export async function getFlow(storeId: number, flowId: number) {
  const response = await api.get<AutomationFlow>(`/api/stores/${storeId}/automation-flows/${flowId}`);
  return response.data;
}

export async function createFlow(storeId: number, payload: FlowCreatePayload) {
  const response = await api.post<AutomationFlow>(`/api/stores/${storeId}/automation-flows`, payload);
  return response.data;
}

export async function updateFlow(storeId: number, flowId: number, payload: FlowUpdatePayload) {
  const response = await api.put<AutomationFlow>(`/api/stores/${storeId}/automation-flows/${flowId}`, payload);
  return response.data;
}

export async function archiveFlow(storeId: number, flowId: number) {
  const response = await api.delete<{ status: string; id: number }>(`/api/stores/${storeId}/automation-flows/${flowId}`);
  return response.data;
}

export async function listFlowVersions(storeId: number, flowId: number) {
  const response = await api.get<AutomationFlowVersion[]>(`/api/stores/${storeId}/automation-flows/${flowId}/versions`);
  return response.data;
}

export async function createFlowVersion(storeId: number, flowId: number, graph: Record<string, unknown>) {
  const response = await api.post<AutomationFlowVersion>(`/api/stores/${storeId}/automation-flows/${flowId}/versions`, { graph });
  return response.data;
}

export async function publishFlowVersion(storeId: number, flowId: number, versionId: number) {
  const response = await api.post<AutomationFlowVersion>(`/api/stores/${storeId}/automation-flows/${flowId}/versions/${versionId}/publish`);
  return response.data;
}

export async function activateFlow(storeId: number, flowId: number) {
  const response = await api.post<AutomationFlow>(`/api/stores/${storeId}/automation-flows/${flowId}/activate`);
  return response.data;
}

export async function deactivateFlow(storeId: number, flowId: number) {
  const response = await api.post<AutomationFlow>(`/api/stores/${storeId}/automation-flows/${flowId}/deactivate`);
  return response.data;
}

export async function triggerFlowRun(storeId: number, flowId: number, payload: FlowRunCreatePayload) {
  const response = await api.post<AutomationFlowRun>(`/api/stores/${storeId}/automation-flows/${flowId}/runs`, payload);
  return response.data;
}

export async function listFlowRuns(storeId: number, flowId: number) {
  const response = await api.get<AutomationFlowRun[]>(`/api/stores/${storeId}/automation-flows/${flowId}/runs`);
  return response.data;
}

export async function getFlowRun(storeId: number, flowId: number, runId: number) {
  const response = await api.get<AutomationFlowRun>(`/api/stores/${storeId}/automation-flows/${flowId}/runs/${runId}`);
  return response.data;
}

export async function listFlowRunRecipients(storeId: number, flowId: number, runId: number, params?: Record<string, string | number | undefined>) {
  const query = new URLSearchParams();
  if (params) Object.entries(params).forEach(([key, value]) => { if (value !== undefined && value !== "") query.set(key, String(value)); });
  const qs = query.toString();
  const response = await api.get<FlowRecipientPage>(`/api/stores/${storeId}/automation-flows/${flowId}/runs/${runId}/recipients${qs ? `?${qs}` : ""}`);
  return response.data;
}

export async function getFlowRecipientDetail(storeId: number, flowId: number, runId: number, recipientId: number) {
  const response = await api.get<AutomationFlowRecipientDetail>(`/api/stores/${storeId}/automation-flows/${flowId}/runs/${runId}/recipients/${recipientId}`);
  return response.data;
}

export async function retryFlowRecipient(storeId: number, flowId: number, runId: number, recipientId: number) {
  const response = await api.post<AutomationFlowRecipient>(`/api/stores/${storeId}/automation-flows/${flowId}/runs/${runId}/recipients/${recipientId}/retry`);
  return response.data;
}

export async function simulateFlow(storeId: number, payload: FlowCreatePayload) {
  const response = await api.post<FlowSimulationResult>(`/api/stores/${storeId}/automation-flows/simulate`, payload);
  return response.data;
}
