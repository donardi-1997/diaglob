import { api } from "./api";
import type { CustomerRiskSummary } from "./customerRisk";
import type { CommerceOrder } from "./integrations";


export interface OrderSalesAttribution {
  actor_type: "human" | "ai";
  actor_id: number | null;
  actor_label: string;
  human_user_id: number | null;
  ai_agent_id: number | null;
  conversation_id: number | null;
  source: string;
}


export interface OrderSalesAttributionChange {
  id: number;
  action: "assign" | "reassign" | "clear";
  changed_by_user_id: number | null;
  changed_by_label: string;
  previous_actor_type: "human" | "ai" | null;
  previous_actor_id: number | null;
  previous_actor_label: string | null;
  new_actor_type: "human" | "ai" | null;
  new_actor_id: number | null;
  new_actor_label: string | null;
  created_at: string;
}


export type AttributedCommerceOrder = CommerceOrder & {
  sales_attribution: OrderSalesAttribution | null;
  customer_id: number | null;
  customer_risk: CustomerRiskSummary;
};


export async function listAttributedCommerceOrders(
  storeId: number,
) {
  const response = await api.get<{
    items: AttributedCommerceOrder[];
    total: number;
  }>(`/api/stores/${storeId}/commerce/orders`);

  return response.data;
}


export async function getOrderSalesAttributionHistory(
  storeId: number,
  orderId: number,
) {
  const response = await api.get<{
    order_id: number;
    items: OrderSalesAttributionChange[];
    total: number;
  }>(
    `/api/stores/${storeId}/commerce/orders/${orderId}/sales-attribution/history`,
  );

  return response.data;
}


export async function updateOrderSalesAttribution(
  storeId: number,
  orderId: number,
  payload: {
    actor_type: "human" | "ai" | null;
    actor_id: number | null;
  },
) {
  const response = await api.patch<{
    order_id: number;
    sales_attribution: OrderSalesAttribution | null;
  }>(
    `/api/stores/${storeId}/commerce/orders/${orderId}/sales-attribution`,
    payload,
  );

  return response.data;
}