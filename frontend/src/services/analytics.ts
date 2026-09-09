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


// ============================================================
// DROPSHIPPING ANALYTICS
// ============================================================


export interface DropshippingOverview {
  total_orders: number;
  confirmed_orders: number;
  shipped_orders: number;
  delivered_orders: number;
  cancelled_orders: number;
  returned_orders: number;
  unknown_orders: number;
  confirmation_rate: number | null;
  delivery_rate: number | null;
  cancellation_rate: number | null;
  return_rate: number | null;
  gross_order_value: number;
  delivered_revenue: number;
  delivered_aov: number | null;
}


export async function getDropshippingOverview(
  storeId: number,
  dateFrom?: string,
  dateTo?: string,
) {
  const qs = buildParams(dateFrom, dateTo);

  const response =
    await api.get<DropshippingOverview>(
      `/api/stores/${storeId}/analytics/dropshipping/overview${qs}`,
    );

  return response.data;
}


export interface DropshippingProfitability {
  delivered_revenue: number;
  total_cogs: number;
  gross_profit: number;
  gross_margin: number | null;
  profit_per_delivered_order: number | null;
  delivered_orders_count: number;
  cost_completeness_pct: number | null;
}


export async function getDropshippingProfitability(
  storeId: number,
  dateFrom?: string,
  dateTo?: string,
) {
  const qs = buildParams(dateFrom, dateTo);

  const response =
    await api.get<DropshippingProfitability>(
      `/api/stores/${storeId}/analytics/dropshipping/profitability${qs}`,
    );

  return response.data;
}


export interface DropshippingProduct {
  product_id: number;
  title: string;
  sku: string | null;
  cost: number | null;
  units_ordered: number;
  total_cogs: number;
}


export async function getDropshippingProducts(
  storeId: number,
  dateFrom?: string,
  dateTo?: string,
) {
  const qs = buildParams(dateFrom, dateTo);

  const response =
    await api.get<DropshippingProduct[]>(
      `/api/stores/${storeId}/analytics/dropshipping/products${qs}`,
    );

  return response.data;
}


export interface DropshippingOrders {
  total: number;
  confirmed: number;
  shipped: number;
  delivered: number;
  cancelled: number;
  returned: number;
}


export async function getDropshippingOrders(
  storeId: number,
  dateFrom?: string,
  dateTo?: string,
) {
  const qs = buildParams(dateFrom, dateTo);

  const response =
    await api.get<DropshippingOrders>(
      `/api/stores/${storeId}/analytics/dropshipping/orders${qs}`,
    );

  return response.data;
}
