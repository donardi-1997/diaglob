import { api } from "./api";


export interface OperationsConversation {
  active_24h: number;
  total: number;
  messages_total: number;
  messages_24h: number;
  ai_resolved_pct: number;
}


export interface OperationsOrders {
  total: number;
  last_24h: number;
  total_value: number;
  by_status: Record<string, number>;
}


export interface OperationsAutomations {
  total: number;
  active: number;
  executions_24h: number;
  failed_7d: number;
}


export interface OperationsProducts {
  total: number;
  variants: number;
}


export interface OperationsAgents {
  total: number;
  active: number;
}


export interface OperationsIntegrations {
  whatsapp_connected: boolean;
  shopify_connected: boolean;
}


export interface OperationsAlert {
  type: string;
  severity: "info" | "warning" | "error";
  message: string;
}


export interface OperationsActivity {
  type: string;
  icon: string;
  title: string;
  detail: string;
  timestamp: string | null;
}


export interface OperationsSummary {
  conversations: OperationsConversation;
  orders: OperationsOrders;
  automations: OperationsAutomations;
  products: OperationsProducts;
  agents: OperationsAgents;
  integrations: OperationsIntegrations;
  alerts: OperationsAlert[];
  activity: OperationsActivity[];
}


export async function getOperationsSummary(
  storeId: number,
): Promise<OperationsSummary> {
  const response =
    await api.get<OperationsSummary>(
      `/api/stores/${storeId}/operations/summary`,
    );

  return response.data;
}
