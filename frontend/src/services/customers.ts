import { api } from "./api";


export interface SpendByCurrency {
  total: number;
  avg_order_value: number;
}


export interface ScoreFactor {
  code: string;
  impact: number;
}


export interface CustomerSummary {
  total_customers: number;
  new_customers: number;
  interested: number;
  high_intent: number;
  buyers: number;
  repeat_buyers: number;
  vip: number;
  at_risk: number;
  inactive: number;
  high_priority: number;
  needs_followup: number;
  active_health: number;
  at_risk_health: number;
  inactive_health: number;
}


export interface CustomerItem {
  id: number;
  name: string;
  phone: string;
  email: string | null;
  country_code: string | null;
  created_at: string;
  store_name: string | null;
  store_id: number | null;
  conversation_count: number;
  message_count: number;
  first_interaction_at: string | null;
  last_interaction_at: string | null;
  successful_order_count: number;
  last_order_at: string | null;
  spend_by_currency: Record<string, SpendByCurrency>;
  primary_segment: string;
  flags: string[];
  days_since_last_interaction: number | null;
  days_since_last_purchase: number | null;
  customer_score: number;
  score_factors: ScoreFactor[];
  priority: string;
  priority_reasons: string[];
  customer_health: string;
  opportunities: string[];
  risks: string[];
  next_best_action: string;
  next_best_action_reasons: string[];
  failed_order_count: number;
  unknown_order_count: number;
  last_failed_order_days: number | null;
  needs_attention: boolean;
}


export interface CustomerListResponse {
  items: CustomerItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}


export interface ConversationSummary {
  id: number;
  channel: string;
  mode: string;
  preview: string;
  updated_at: string | null;
}


export interface OrderSummary {
  id: number;
  order_number: string;
  total_amount: number;
  currency: string;
  external_creation_status: string;
  financial_status: string | null;
  created_at: string | null;
}


export interface TimelineEvent {
  type: string;
  timestamp: string | null;
  conversation_id?: number;
  order_id?: number;
  customer_id?: number;
  channel?: string;
  preview?: string;
  order_number?: string;
  total_amount?: number;
  currency?: string;
}


export interface CustomerDetail extends CustomerItem {
  recent_conversations: ConversationSummary[];
  recent_orders: OrderSummary[];
  timeline: TimelineEvent[];
}


export async function getCustomerSummary(
  storeId?: number,
): Promise<CustomerSummary> {
  const params = new URLSearchParams();

  if (storeId) {
    params.set("store_id", String(storeId));
  }

  const qs = params.toString();
  const url = `/api/customers/summary${qs ? `?${qs}` : ""}`;

  const response =
    await api.get<CustomerSummary>(url);

  return response.data;
}


export async function getCustomerList(params: {
  storeId?: number;
  segment?: string;
  flag?: string;
  search?: string;
  hasOrders?: boolean;
  page?: number;
  pageSize?: number;
  sort?: string;
  priority?: string;
  health?: string;
  needsAttention?: boolean;
}): Promise<CustomerListResponse> {
  const searchParams = new URLSearchParams();

  if (params.storeId) {
    searchParams.set(
      "store_id",
      String(params.storeId),
    );
  }

  if (params.segment) {
    searchParams.set("segment", params.segment);
  }

  if (params.flag) {
    searchParams.set("flag", params.flag);
  }

  if (params.search) {
    searchParams.set("search", params.search);
  }

  if (params.hasOrders !== undefined) {
    searchParams.set(
      "has_orders",
      String(params.hasOrders),
    );
  }

  if (params.page) {
    searchParams.set("page", String(params.page));
  }

  if (params.pageSize) {
    searchParams.set(
      "page_size",
      String(params.pageSize),
    );
  }

  if (params.sort) {
    searchParams.set("sort", params.sort);
  }

  if (params.priority) {
    searchParams.set("priority", params.priority);
  }

  if (params.health) {
    searchParams.set("health", params.health);
  }

  if (params.needsAttention !== undefined) {
    searchParams.set(
      "needs_attention",
      String(params.needsAttention),
    );
  }

  const qs = searchParams.toString();
  const url = `/api/customers${qs ? `?${qs}` : ""}`;

  const response =
    await api.get<CustomerListResponse>(url);

  return response.data;
}


export async function getCustomerDetail(
  customerId: number,
  storeId?: number,
): Promise<CustomerDetail> {
  const params = new URLSearchParams();

  if (storeId) {
    params.set("store_id", String(storeId));
  }

  const qs = params.toString();
  const url = `/api/customers/${customerId}${qs ? `?${qs}` : ""}`;

  const response =
    await api.get<CustomerDetail>(url);

  return response.data;
}
