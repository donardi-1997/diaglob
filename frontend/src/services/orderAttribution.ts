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
