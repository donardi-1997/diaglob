import { api } from "./api";


export interface AnalyticsSummary {
  total_conversations: number;
  total_messages: number;
  total_products: number;
  total_variants: number;
  total_orders: number;
  total_order_value: number;
  avg_order_value: number;
  active_automations: number;
  total_executions: number;
  success_executions: number;
  automation_success_rate: number;
  avg_messages_per_conversation: number;
}


export interface TimeseriesPoint {
  date: string;
  conversations: number;
  messages: number;
  orders: number;
  order_value: number;
  executions: number;
}


export interface ConversationsAnalytics {
  total_conversations: number;
  total_messages: number;
  avg_messages_per_conversation: number;
  by_channel: Record<string, number>;
  by_mode: Record<string, number>;
  sender_distribution: Record<string, number>;
  top_conversations: {
    conversation_id: number;
    message_count: number;
  }[];
}


export interface CommerceAnalytics {
  total_orders: number;
  total_value: number;
  avg_ticket: number;
  by_status: Record<string, number>;
  by_source: Record<string, number>;
  top_products: {
    title: string;
    total_units: number;
    order_count: number;
    total_value: number;
  }[];
}


export interface AutomationsAnalytics {
  total_automations: number;
  active_automations: number;
  inactive_automations: number;
  total_executions: number;
  by_status: Record<string, number>;
  success_rate: number;
  avg_duration_seconds: number | null;
  by_trigger: Record<string, number>;
  top_by_executions: {
    name: string;
    execution_count: number;
  }[];
  top_by_failures: {
    name: string;
    failure_count: number;
  }[];
}


function buildParams(
  dateFrom?: string,
  dateTo?: string,
) {
  const params = new URLSearchParams();

  if (dateFrom) {
    params.set("date_from", dateFrom);
  }

  if (dateTo) {
    params.set("date_to", dateTo);
  }

  const qs = params.toString();

  return qs ? `?${qs}` : "";
}


export async function getAnalyticsSummary(
  storeId: number,
  dateFrom?: string,
  dateTo?: string,
) {
  const qs = buildParams(dateFrom, dateTo);

  const response =
    await api.get<AnalyticsSummary>(
      `/api/stores/${storeId}/analytics/summary${qs}`,
    );

  return response.data;
}


export async function getAnalyticsTimeseries(
  storeId: number,
  dateFrom?: string,
  dateTo?: string,
) {
  const qs = buildParams(dateFrom, dateTo);

  const response =
    await api.get<TimeseriesPoint[]>(
      `/api/stores/${storeId}/analytics/timeseries${qs}`,
    );

  return response.data;
}


export async function getAnalyticsConversations(
  storeId: number,
  dateFrom?: string,
  dateTo?: string,
) {
  const qs = buildParams(dateFrom, dateTo);

  const response =
    await api.get<ConversationsAnalytics>(
      `/api/stores/${storeId}/analytics/conversations${qs}`,
    );

  return response.data;
}


export async function getAnalyticsCommerce(
  storeId: number,
  dateFrom?: string,
  dateTo?: string,
) {
  const qs = buildParams(dateFrom, dateTo);

  const response =
    await api.get<CommerceAnalytics>(
      `/api/stores/${storeId}/analytics/commerce${qs}`,
    );

  return response.data;
}


export async function getAnalyticsAutomations(
  storeId: number,
  dateFrom?: string,
  dateTo?: string,
) {
  const qs = buildParams(dateFrom, dateTo);

  const response =
    await api.get<AutomationsAnalytics>(
      `/api/stores/${storeId}/analytics/automations${qs}`,
    );

  return response.data;
}
