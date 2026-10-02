import { api } from "./api";

export type PostSalesCaseType =
  | "warranty"
  | "return"
  | "refund"
  | "damaged"
  | "wrong_product"
  | "delivery_issue"
  | "other";

export type PostSalesStatus =
  | "open"
  | "waiting_customer"
  | "investigating"
  | "approved"
  | "rejected"
  | "resolved"
  | "closed";

export type PostSalesPriority = "low" | "normal" | "high" | "urgent";

export interface PostSalesCase {
  id: number;
  store_id: number;
  order_id?: number | null;
  customer_id?: number | null;
  assigned_agent_id?: number | null;
  case_type: PostSalesCaseType;
  status: PostSalesStatus;
  priority: PostSalesPriority;
  title: string;
  description: string;
  resolution?: string | null;
  amount?: number | null;
  currency?: string | null;
  evidence_refs: string[];
  source_channel?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  resolved_at?: string | null;
}

export interface PostSalesSummary {
  total: number;
  open: number;
  urgent: number;
  waiting_customer: number;
  resolved: number;
  by_type: Record<string, number>;
}

export async function getPostSalesSummary(storeId: number) {
  const response = await api.get<PostSalesSummary>(
    `/api/stores/${storeId}/post-sales/summary`,
  );
  return response.data;
}

export async function getPostSalesCases(storeId: number) {
  const response = await api.get<{ items: PostSalesCase[]; total: number }>(
    `/api/stores/${storeId}/post-sales/cases`,
  );
  return response.data;
}

export async function createPostSalesCase(
  storeId: number,
  payload: {
    case_type: PostSalesCaseType;
    priority: PostSalesPriority;
    title: string;
    description?: string;
    order_id?: number;
    customer_id?: number;
  },
) {
  const response = await api.post<PostSalesCase>(
    `/api/stores/${storeId}/post-sales/cases`,
    payload,
  );
  return response.data;
}

export async function updatePostSalesCase(
  storeId: number,
  caseId: number,
  payload: {
    status?: PostSalesStatus;
    priority?: PostSalesPriority;
    resolution?: string;
    note?: string;
  },
) {
  const response = await api.patch<PostSalesCase>(
    `/api/stores/${storeId}/post-sales/cases/${caseId}`,
    payload,
  );
  return response.data;
}
