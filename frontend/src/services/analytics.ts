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
  top_conversations: { conversation_id: number; message_count: number }[];
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
  top_by_executions: { name: string; execution_count: number }[];
  top_by_failures: { name: string; failure_count: number }[];
}

function buildParams(dateFrom?: string, dateTo?: string) {
  const params = new URLSearchParams();
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export async function getAnalyticsSummary(storeId: number, dateFrom?: string, dateTo?: string) {
  const response = await api.get<AnalyticsSummary>(
    `/api/stores/${storeId}/analytics/summary${buildParams(dateFrom, dateTo)}`,
  );
  return response.data;
}

export async function getAnalyticsTimeseries(storeId: number, dateFrom?: string, dateTo?: string) {
  const response = await api.get<TimeseriesPoint[]>(
    `/api/stores/${storeId}/analytics/timeseries${buildParams(dateFrom, dateTo)}`,
  );
  return response.data;
}

export async function getAnalyticsConversations(storeId: number, dateFrom?: string, dateTo?: string) {
  const response = await api.get<ConversationsAnalytics>(
    `/api/stores/${storeId}/analytics/conversations${buildParams(dateFrom, dateTo)}`,
  );
  return response.data;
}

export async function getAnalyticsCommerce(storeId: number, dateFrom?: string, dateTo?: string) {
  const response = await api.get<CommerceAnalytics>(
    `/api/stores/${storeId}/analytics/commerce${buildParams(dateFrom, dateTo)}`,
  );
  return response.data;
}

export async function getAnalyticsAutomations(storeId: number, dateFrom?: string, dateTo?: string) {
  const response = await api.get<AutomationsAnalytics>(
    `/api/stores/${storeId}/analytics/automations${buildParams(dateFrom, dateTo)}`,
  );
  return response.data;
}

export interface DropshippingComparison {
  previous_date_from: string;
  previous_date_to: string;
  total_orders_pct: number | null;
  delivered_orders_pct: number | null;
  delivered_revenue_pct: number | null;
  delivered_aov_pct: number | null;
  delivery_rate_pp: number | null;
  cancellation_rate_pp: number | null;
  gross_profit_pct: number | null;
  gross_margin_pp: number | null;
}

export interface SalesAttributionMetrics {
  total_orders: number;
  delivered_orders: number;
  cancelled_orders: number;
  returned_orders: number;
  gross_order_value: number;
  delivered_revenue: number;
  total_cogs: number;
  gross_profit: number;
  gross_margin: number | null;
  delivered_aov: number | null;
  delivery_rate: number | null;
  cancellation_rate: number | null;
  return_rate: number | null;
  cost_completeness_pct: number;
  profitability_complete: boolean;
}

export interface SalesAttributionActorPerformance extends SalesAttributionMetrics {
  actor_id: number | null;
  actor_label: string;
  order_share_pct: number | null;
  revenue_share_pct: number | null;
}

export interface SalesAttributionAnalytics {
  total_orders: number;
  attributed_orders: number;
  unattributed_orders: number;
  attribution_rate_pct: number;
  overall: SalesAttributionMetrics;
  by_actor_type: {
    human: SalesAttributionMetrics;
    ai: SalesAttributionMetrics;
    unattributed: SalesAttributionMetrics;
  };
  employees: SalesAttributionActorPerformance[];
  ai_agents: SalesAttributionActorPerformance[];
}

export interface DropshippingOverview {
  currency: string;
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
  comparison: DropshippingComparison | null;
  sales_attribution: SalesAttributionAnalytics;
}

export async function getDropshippingOverview(storeId: number, dateFrom?: string, dateTo?: string) {
  const response = await api.get<DropshippingOverview>(
    `/api/stores/${storeId}/analytics/dropshipping/overview${buildParams(dateFrom, dateTo)}`,
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
  cost_completeness_pct: number;
  profitability_complete: boolean;
}

export async function getDropshippingProfitability(storeId: number, dateFrom?: string, dateTo?: string) {
  const response = await api.get<DropshippingProfitability>(
    `/api/stores/${storeId}/analytics/dropshipping/profitability${buildParams(dateFrom, dateTo)}`,
  );
  return response.data;
}

export interface DropshippingProduct {
  product_id: number;
  title: string;
  sku: string | null;
  cost: number | null;
  inventory_quantity: number;
  total_orders: number;
  confirmed_orders: number;
  shipped_orders: number;
  delivered_orders: number;
  cancelled_orders: number;
  returned_orders: number;
  units_delivered: number;
  delivered_revenue: number;
  total_cogs: number;
  gross_profit: number;
  gross_margin: number | null;
  profit_per_unit: number | null;
  delivery_rate: number | null;
  cancellation_rate: number | null;
  return_rate: number | null;
  cost_completeness_pct: number;
  profitability_complete: boolean;
  revenue_share_pct: number;
  profit_share_pct: number;
}

export interface DropshippingProductComparison {
  previous_date_from: string;
  previous_date_to: string;
  total_orders_pct: number | null;
  delivered_orders_pct: number | null;
  units_delivered_pct: number | null;
  delivered_revenue_pct: number | null;
  gross_profit_pct: number | null;
  delivery_rate_pp: number | null;
  cancellation_rate_pp: number | null;
  return_rate_pp: number | null;
  gross_margin_pp: number | null;
}

export interface DropshippingProductTimeseriesPoint {
  date: string;
  total_orders: number;
  delivered_orders: number;
  units_delivered: number;
  delivered_revenue: number;
  gross_profit: number;
}

export interface DropshippingProductVariant {
  variant_id: number | null;
  title: string;
  sku: string | null;
  inventory_quantity: number;
  total_orders: number;
  delivered_orders: number;
  units_delivered: number;
  delivered_revenue: number;
  gross_profit: number;
}

export interface DropshippingProductDetail {
  product: {
    id: number;
    title: string;
    description: string;
  };
  metrics: DropshippingProduct;
  comparison: DropshippingProductComparison | null;
  timeseries: DropshippingProductTimeseriesPoint[];
  variants: DropshippingProductVariant[];
}

export async function getDropshippingProducts(storeId: number, dateFrom?: string, dateTo?: string) {
  const response = await api.get<DropshippingProduct[]>(
    `/api/stores/${storeId}/analytics/dropshipping/products${buildParams(dateFrom, dateTo)}`,
  );
  return response.data;
}

export async function getDropshippingProductDetail(
  storeId: number,
  productId: number,
  dateFrom?: string,
  dateTo?: string,
) {
  const response = await api.get<DropshippingProductDetail>(
    `/api/stores/${storeId}/analytics/dropshipping/products/${productId}${buildParams(dateFrom, dateTo)}`,
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
  unknown: number;
}

export async function getDropshippingOrders(storeId: number, dateFrom?: string, dateTo?: string) {
  const response = await api.get<DropshippingOrders>(
    `/api/stores/${storeId}/analytics/dropshipping/orders${buildParams(dateFrom, dateTo)}`,
  );
  return response.data;
}
