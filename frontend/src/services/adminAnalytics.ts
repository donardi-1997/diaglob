import { api } from "./api";

export interface AdminGrowthPoint {
  date: string;
  organizations: number;
  users: number;
  ai_responses: number;
  orders: number;
}

export interface AdminRankingItem {
  organization_id: number;
  organization_name: string;
  plan: string;
  ai_responses?: number;
  orders?: number;
  conversations?: number;
}

export interface AdminGrowth {
  window_days: number;
  period: {
    from: string;
    to: string;
  };
  totals: {
    new_organizations: number;
    new_users: number;
    ai_responses: number;
    orders: number;
  };
  daily: AdminGrowthPoint[];
  billing_health: {
    subscription_statuses: Record<string, number>;
    pending_plan_changes: number;
    auto_renew_disabled: number;
    historical_billing_available: boolean;
    historical_billing_reason: string;
  };
  rankings: {
    top_ai_usage: AdminRankingItem[];
    top_orders: AdminRankingItem[];
    top_conversations: AdminRankingItem[];
  };
}

export interface AdminOverview {
  organizations: {
    total: number;
    by_plan: Record<string, number>;
  };
  users: { total: number };
  stores: {
    total: number;
    active: number;
  };
  revenue: {
    mrr: string;
    arr: string;
    currency: string;
  };
  conversations: {
    total: number;
    total_messages: number;
    ai_messages: number;
  };
  orders: { total: number };
  integrations: {
    shopify_connected: number;
    whatsapp_connected: number;
    meta_ads_connected: number;
    knowledge_bases: number;
  };
  automations: { total: number };
  growth: AdminGrowth;
}

export interface AdminAttentionItem {
  organization_id: number;
  organization_name: string;
  plan: string;
  issue: string;
  severity: "CRITICAL" | "WARNING" | "INFO";
  ai_used: number;
  ai_included: number;
}

export async function getAdminStatus() {
  await api.get<AdminOverview>("/api/admin/overview");
  return { platform_admin: true as const };
}

export async function getAdminOverview() {
  const response = await api.get<AdminOverview>("/api/admin/overview");
  return response.data;
}

export async function getAdminAttention() {
  const response = await api.get<AdminAttentionItem[]>("/api/admin/attention");
  return response.data;
}
