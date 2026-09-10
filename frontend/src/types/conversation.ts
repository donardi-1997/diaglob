import type { CustomerRiskSummary } from "../services/customerRisk";

export type ConversationMode =
  "ai" | "human";

export type MessageSender =
  "customer" | "ai" | "human";


export interface ConversationStore {
  id: number;
  name: string;
}


export interface ConversationAgent {
  id: number;
  name: string;
  role: string;
}


export interface ConversationalCheckoutSummary {
  id: number;
  status: string;
  product_id: number | null;
  variant_id: number | null;
  product_title: string | null;
  variant_title: string | null;
  quantity: number;
  currency: string;
  total: number | null;
  payment_method: string;
  address_line: string | null;
  address_complement: string | null;
  neighborhood: string | null;
  city: string | null;
  region: string | null;
  country_code: string;
  delivery_reference: string | null;
  address_confidence_score: number;
  address_validation_status: string;
  address_confirmed: boolean;
  address_confirmed_at: string | null;
  customer_confirmed: boolean;
  customer_confirmed_at: string | null;
  created_order_id: number | null;
  failure_reason: string | null;
  expires_at: string;
}


export interface ConversationSummary {
  id: number;
  customer_id: number;
  name: string;
  preview: string;
  time: string;
  unread: number;

  channel: string;
  phone: string;
  email: string;

  country_code: string;
  currency: string;

  store: ConversationStore | null;
  agent: ConversationAgent | null;

  orders: number;
  total_spent: number;
  last_order: string;

  mode: ConversationMode;
  tags: string[];
  customer_risk: CustomerRiskSummary;
}


export interface ConversationMessage {
  id: number;
  sender: MessageSender;
  text: string;
  time: string;

  agent?:
    | string
    | ConversationAgent
    | null;
}


export interface ConversationDetail
  extends ConversationSummary {

  messages: ConversationMessage[];
  checkout: ConversationalCheckoutSummary | null;
}


export interface ConversationListResponse {
  items: ConversationSummary[];
  total: number;
}
