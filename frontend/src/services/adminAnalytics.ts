import { api } from "./api";

export interface AdminStatus {
  platform_admin: boolean;
  email: string;
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
  const response = await api.get<AdminStatus>("/api/admin/status");
  return response.data;
}

export async function getAdminOverview() {
  const response = await api.get<AdminOverview>("/api/admin/overview");
  return response.data;
}

export async function getAdminAttention() {
  const response = await api.get<AdminAttentionItem[]>("/api/admin/attention");
  return response.data;
}
