import { apiRequest } from "./api";

export interface CustomerSummary {
  total_customers: number;
  new_customers: number;
  buyers: number;
  repeat_buyers: number;
  vip: number;
  at_risk: number;
  high_priority: number;
  needs_followup: number;
}

export interface CustomerItem {
  id: number;
  name: string;
  phone: string;
  email: string | null;
  store_id: number | null;
  successful_order_count: number;
  primary_segment: string;
  priority: string;
  customer_health: string;
  next_best_action: string;
  needs_attention: boolean;
  customer_score: number;
}

export async function getCustomerSummary(
  storeId: number,
) {
  return apiRequest<CustomerSummary>(
    `/api/customers/summary?store_id=${storeId}`,
    { storeId: String(storeId) },
  );
}

export async function getCustomerList(
  storeId: number,
  search = "",
) {
  const params = new URLSearchParams({
    store_id: String(storeId),
    page: "1",
    page_size: "40",
    sort: "-customer_score",
  });

  if (search.trim()) {
    params.set("search", search.trim());
  }

  return apiRequest<{
    items: CustomerItem[];
    total: number;
    page: number;
    page_size: number;
    total_pages: number;
  }>(
    `/api/customers?${params.toString()}`,
    { storeId: String(storeId) },
  );
}
