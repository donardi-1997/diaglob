import { api } from "./api";


export interface AutomationCondition {
  field: string;
  operator: string;
  value: any;
}


export interface AutomationAction {
  type: string;
  [key: string]: any;
}


export interface Automation {
  id: number;
  organization_id: number;
  store_id: number | null;
  name: string;
  description: string | null;
  active: boolean;
  trigger_type: string;
  conditions_json: AutomationCondition[];
  actions_json: AutomationAction[];
  created_by: number | null;
  created_at: string | null;
  updated_at: string | null;
  last_execution: {
    id: number;
    status: string;
    started_at: string | null;
    completed_at: string | null;
  } | null;
}


export interface AutomationPayload {
  name: string;
  description?: string;
  store_id?: number;
  active?: boolean;
  trigger_type?: string;
  conditions_json?: AutomationCondition[];
  actions_json?: AutomationAction[];
}


export interface AutomationExecution {
  id: number;
  automation_id: number;
  automation_name: string;
  status: string;
  event_type: string;
  event_id: string | null;
  input_json: Record<string, any>;
  result_json: Record<string, any>;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface AutomationCampaign {
  id: number;
  name: string;
  automation_type: string;
  status: "draft" | "active" | "paused" | "archived";
  audience_type: "dynamic" | "fixed";
  audience_filters: Record<string, unknown>;
  member_count: number;
  schedule_type: string;
  schedule_config: Record<string, unknown>;
  timezone: string;
  send_window_start: string | null;
  send_window_end: string | null;
  cooldown_days: number;
  channel: string;
  message_template: string;
  message_mode: "free_form" | "template" | "auto";
  whatsapp_template_id: number | null;
  template_variables: Record<string, string[]>;
}

export interface AutomationCampaignPayload {
  name: string;
  automation_type: string;
  status: "draft" | "active" | "paused" | "archived";
  audience_type: "dynamic" | "fixed";
  audience_filters: Record<string, unknown>;
  member_ids: number[];
  selection_mode?: "explicit" | "all_filtered";
  selected_customer_ids?: number[];
  excluded_customer_ids?: number[];
  schedule_type: string;
  schedule_config: Record<string, unknown>;
  timezone?: string;
  send_window_start?: string;
  send_window_end?: string;
  cooldown_days: number;
  channel: "whatsapp";
  message_template: string;
  message_mode: "free_form" | "template" | "auto";
  whatsapp_template_id?: number;
  template_variables: Record<string, string[]>;
}

export interface WhatsAppMessageTemplate {
  id: number;
  provider_template_name: string;
  language_code: string;
  category: string | null;
  status: string;
  components: Record<string, unknown>;
}

export interface AudiencePreview {
  eligible_count: number;
  sample: Array<Record<string, unknown>>;
  segment_distribution?: Record<string, number>;
  country_distribution?: Record<string, number>;
}

export interface AutomationAudienceCustomer {
  customer_id: number;
  name: string;
  phone: string | null;
  email: string | null;
  country_code: string | null;
  primary_segment: string;
  priority: string;
  customer_score: number;
  customer_health: string;
  last_interaction_at: string | null;
  successful_order_count: number;
  spend_by_currency: Record<string, { total: number }>;
  needs_attention: boolean;
}

export interface AutomationAudienceCustomerPage {
  items: AutomationAudienceCustomer[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface CampaignSimulation {
  matched: number;
  eligible: number;
  excluded: number;
  would_send: number;
  exclusion_breakdown: Record<string, number>;
  sample: Array<Record<string, unknown>>;
}


export async function listAutomations(
  storeId: number,
) {
  const response =
    await api.get<{
      items: Automation[];
      total: number;
    }>(
      `/api/stores/${storeId}/automations`,
    );

  return response.data;
}


export async function createAutomation(
  storeId: number,
  payload: AutomationPayload,
) {
  const response =
    await api.post<Automation>(
      `/api/stores/${storeId}/automations`,
      payload,
    );

  return response.data;
}


export async function getAutomation(
  storeId: number,
  automationId: number,
) {
  const response =
    await api.get<Automation>(
      `/api/stores/${storeId}/automations/${automationId}`,
    );

  return response.data;
}


export async function updateAutomation(
  storeId: number,
  automationId: number,
  payload: Partial<AutomationPayload>,
) {
  const response =
    await api.put<Automation>(
      `/api/stores/${storeId}/automations/${automationId}`,
      payload,
    );

  return response.data;
}


export async function deleteAutomation(
  storeId: number,
  automationId: number,
) {
  const response =
    await api.delete<{ ok: boolean }>(
      `/api/stores/${storeId}/automations/${automationId}`,
    );

  return response.data;
}


export async function toggleAutomation(
  storeId: number,
  automationId: number,
) {
  const response =
    await api.post<{
      id: number;
      active: boolean;
      updated_at: string | null;
    }>(
      `/api/stores/${storeId}/automations/${automationId}/toggle`,
    );

  return response.data;
}


export async function runAutomation(
  storeId: number,
  automationId: number,
  payload?: {
    event_type?: string;
    payload?: Record<string, any>;
  },
) {
  const response =
    await api.post<AutomationExecution>(
      `/api/stores/${storeId}/automations/${automationId}/run`,
      {
        event_type:
          payload?.event_type ?? "manual",
        payload: payload?.payload ?? {},
      },
    );

  return response.data;
}


export async function listAutomationExecutions(
  storeId: number,
  automationId: number,
) {
  const response =
    await api.get<{
      items: AutomationExecution[];
      total: number;
    }>(
      `/api/stores/${storeId}/automations/${automationId}/executions`,
    );

  return response.data;
}


export async function listAllAutomationExecutions(
  storeId: number,
) {
  const response =
    await api.get<{
      items: AutomationExecution[];
      total: number;
    }>(
      `/api/stores/${storeId}/automation-executions`,
    );

  return response.data;
}

export async function listAutomationCampaigns(storeId: number) {
  const response = await api.get<{ items: AutomationCampaign[]; total: number }>(`/api/stores/${storeId}/automation-campaigns`);
  return response.data;
}

export async function createAutomationCampaign(storeId: number, payload: AutomationCampaignPayload) {
  const response = await api.post<AutomationCampaign>(`/api/stores/${storeId}/automation-campaigns`, payload);
  return response.data;
}

export async function previewAutomationAudience(storeId: number, payload: Pick<AutomationCampaignPayload, "audience_type" | "audience_filters" | "member_ids">) {
  const response = await api.post<AudiencePreview>(`/api/stores/${storeId}/automation-campaigns/audience/preview`, payload);
  return response.data;
}

export async function listAutomationAudienceCustomers(storeId: number, params: Record<string, string | number | boolean | undefined>) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => { if (value !== undefined && value !== "") query.set(key, String(value)); });
  const response = await api.get<AutomationAudienceCustomerPage>(`/api/stores/${storeId}/automation-campaigns/audience/customers?${query}`);
  return response.data;
}

export async function simulateAutomationCampaign(storeId: number, campaignId: number) {
  const response = await api.post<CampaignSimulation>(`/api/stores/${storeId}/automation-campaigns/${campaignId}/simulate`);
  return response.data;
}

export async function duplicateAutomationCampaign(storeId: number, campaignId: number) {
  const response = await api.post<AutomationCampaign>(`/api/stores/${storeId}/automation-campaigns/${campaignId}/duplicate`);
  return response.data;
}

export async function listWhatsAppTemplates(storeId: number) {
  const response = await api.get<{ items: WhatsAppMessageTemplate[] }>(`/api/stores/${storeId}/whatsapp/templates`);
  return response.data;
}

export interface AutomationRun {
  id: number;
  automation_id: number;
  campaign_name: string | null;
  status: "simulated" | "pending" | "running" | "completed" | "partial" | "failed";
  matched_count: number;
  eligible_count: number;
  sent_count: number;
  failed_count: number;
  excluded_count: number;
  started_at: string | null;
  completed_at: string | null;
  scheduled_for: string | null;
  total_recipients?: number;
  pending_count?: number;
}

export interface AutomationRecipientRow {
  id: number;
  customer_id: number;
  customer_name: string;
  customer_phone: string | null;
  status: string;
  exclusion_reason: string | null;
  attempt_count: number;
  next_attempt_at: string | null;
  sent_at: string | null;
  provider_message_id: string | null;
  error_code: string | null;
  error_message: string | null;
}

export interface AutomationRecipientDetail extends AutomationRecipientRow {
  run_id: number;
  rendered_message: string | null;
  template_data: Record<string, unknown>;
  attempts: AutomationDeliveryAttempt[];
}

export interface AutomationDeliveryAttempt {
  id: number;
  attempt_number: number;
  status: string;
  provider_message_id: string | null;
  error_code: string | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface AutomationRecipientPage {
  items: AutomationRecipientRow[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export async function listCampaignRuns(storeId: number, campaignId: number) {
  const response = await api.get<{ items: AutomationRun[] }>(`/api/stores/${storeId}/automation-campaigns/${campaignId}/runs`);
  return response.data;
}

export async function getCampaignRunDetail(storeId: number, campaignId: number, runId: number) {
  const response = await api.get<AutomationRun>(`/api/stores/${storeId}/automation-campaigns/${campaignId}/runs/${runId}`);
  return response.data;
}

export async function listRunRecipients(storeId: number, campaignId: number, runId: number, params: Record<string, string | number | undefined>) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => { if (value !== undefined && value !== "") query.set(key, String(value)); });
  const response = await api.get<AutomationRecipientPage>(`/api/stores/${storeId}/automation-campaigns/${campaignId}/runs/${runId}/recipients?${query}`);
  return response.data;
}

export async function getRunRecipientDetail(storeId: number, campaignId: number, runId: number, recipientId: number) {
  const response = await api.get<AutomationRecipientDetail>(`/api/stores/${storeId}/automation-campaigns/${campaignId}/runs/${runId}/recipients/${recipientId}`);
  return response.data;
}

export async function retryRunRecipient(storeId: number, campaignId: number, runId: number, recipientId: number) {
  const response = await api.post<{ ok: boolean; status: string }>(`/api/stores/${storeId}/automation-campaigns/${campaignId}/runs/${runId}/recipients/${recipientId}/retry`);
  return response.data;
}
