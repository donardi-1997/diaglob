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
}


export interface ConversationListResponse {
  items: ConversationSummary[];
  total: number;
}
