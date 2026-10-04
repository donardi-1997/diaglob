import { apiRequest } from "./api";

export interface CommerceOrder {
  id: number;
  order_number: string;
  total_amount: number;
  currency: string;
  financial_status: string | null;
  fulfillment_status: string | null;
  source: string | null;
  external_creation_status: string | null;
  created_at: string | null;
}

export interface CommerceSummary {
  connected: boolean;
  provider: string | null;
  total_products: number;
  total_variants: number;
  total_orders: number;
  orders_by_status: {
    pending: number;
    created: number;
    failed: number;
    unknown: number;
  };
  total_order_value: number;
  currency: string;
  recent_orders: CommerceOrder[];
  recent_products: {
    id: number;
    title: string;
    image_url: string | null;
    active: boolean;
    updated_at: string | null;
  }[];
}

export async function getCommerceSummary(
  storeId: number,
) {
  return apiRequest<CommerceSummary>(
    `/api/stores/${storeId}/commerce/summary`,
    { storeId: String(storeId) },
  );
}

export async function listCommerceOrders(
  storeId: number,
) {
  return apiRequest<{
    items: CommerceOrder[];
    total: number;
  }>(
    `/api/stores/${storeId}/commerce/orders`,
    { storeId: String(storeId) },
  );
}
