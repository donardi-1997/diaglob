import { api } from "./api";

export type CommercialClassification =
  | "champion"
  | "loyal"
  | "repeat_customer"
  | "high_value"
  | "recent_buyer"
  | "value_at_risk"
  | "dormant"
  | "prospect"
  | "lead";

export type CustomerValueTier = "high" | "medium" | "low" | "none";

export interface CustomerClassificationItem {
  customer_id: number;
  name: string;
  phone: string;
  email: string | null;
  country_code: string | null;
  currency: string;
  commercial_classification: CommercialClassification;
  value_tier: CustomerValueTier;
  rfm_recency_days: number | null;
  rfm_frequency: number;
  rfm_monetary_value: number;
  rfm_recency_score: number;
  rfm_frequency_score: number;
  rfm_monetary_score: number;
  rfm_score: number;
  last_delivered_at: string | null;
  last_interaction_at: string | null;
  classification_reasons: string[];
}

export interface CustomerClassificationSummary {
  total_customers: number;
  buyers: number;
  repeat_buyers: number;
  repeat_buyer_rate: number | null;
  lifetime_delivered_revenue: number;
  classification_counts: Record<CommercialClassification, number>;
  value_tier_counts: Record<CustomerValueTier, number>;
}

export interface CustomerClassificationPage {
  items: CustomerClassificationItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  summary: CustomerClassificationSummary;
}

export interface ClassificationDistributionItem {
  classification: CommercialClassification;
  customers: number;
  customer_share_pct: number;
  period_delivered_orders: number;
  period_delivered_revenue: number;
  revenue_share_pct: number;
  avg_order_value: number | null;
}

export interface ValueTierDistributionItem {
  value_tier: CustomerValueTier;
  customers: number;
  customer_share_pct: number;
}

export interface CustomerClassificationAnalytics {
  currency: string;
  total_customers: number;
  customers_with_delivered_orders: number;
  repeat_customer_rate: number | null;
  period_delivered_orders: number;
  period_delivered_revenue: number;
  classification_distribution: ClassificationDistributionItem[];
  value_tier_distribution: ValueTierDistributionItem[];
  top_customers: Array<CustomerClassificationItem & {
    period_delivered_orders: number;
    period_delivered_revenue: number;
  }>;
  classification_basis: string;
  period_basis: string;
}

export interface ClassifiedAudienceCustomer {
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
  commercial_classification: CommercialClassification;
  value_tier: CustomerValueTier;
  rfm_recency_days: number | null;
  rfm_frequency: number;
  rfm_monetary_value: number;
  rfm_score: number;
}

export interface ClassifiedAudiencePage {
  items: ClassifiedAudienceCustomer[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

function buildQuery(params: Record<string, string | number | boolean | undefined>) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") query.set(key, String(value));
  });
  const value = query.toString();
  return value ? `?${value}` : "";
}

export async function getCustomerClassifications(
  storeId: number,
  params: {
    classification?: string;
    valueTier?: string;
    search?: string;
    page?: number;
    pageSize?: number;
    sort?: string;
  } = {},
) {
  const response = await api.get<CustomerClassificationPage>(
    `/api/stores/${storeId}/customers/classifications${buildQuery({
      classification: params.classification,
      value_tier: params.valueTier,
      search: params.search,
      page: params.page,
      page_size: params.pageSize,
      sort: params.sort,
    })}`,
  );
  return response.data;
}

export async function getCustomerClassificationAnalytics(
  storeId: number,
  dateFrom?: string,
  dateTo?: string,
) {
  const response = await api.get<CustomerClassificationAnalytics>(
    `/api/stores/${storeId}/analytics/customers${buildQuery({
      date_from: dateFrom,
      date_to: dateTo,
    })}`,
  );
  return response.data;
}

export async function listClassifiedAudienceCustomers(
  storeId: number,
  params: Record<string, string | number | boolean | undefined>,
) {
  const response = await api.get<ClassifiedAudiencePage>(
    `/api/stores/${storeId}/customers/audience${buildQuery(params)}`,
  );
  return response.data;
}
