import { api } from "./api";


export type CustomerRiskSeverity = "none" | "notice" | "elevated" | "high";
export type CustomerRiskReason =
  | "suspected_fraud"
  | "payment_abuse"
  | "delivery_claim"
  | "identity_mismatch"
  | "abusive_behavior"
  | "other";


export interface CustomerRiskOwnReport {
  id: number;
  reason: CustomerRiskReason;
  status: "pending" | "confirmed" | "disputed";
  notes: string | null;
  evidence_reference: string | null;
  created_at: string | null;
  updated_at: string | null;
}


export interface CustomerRiskSummary {
  available: boolean;
  alert: boolean;
  severity: CustomerRiskSeverity;
  reporting_organizations: number;
  external_reporting_organizations: number;
  confirmed_reports: number;
  pending_reports: number;
  disputed_reports: number;
  reason_counts: Partial<Record<CustomerRiskReason, number>>;
  last_reported_at: string | null;
  matched_on: Array<"phone" | "email">;
  reported_by_current_organization: boolean;
  current_organization_report: CustomerRiskOwnReport | null;
}


export interface CustomerRiskReportPayload {
  reason: CustomerRiskReason;
  notes?: string;
  evidence_reference?: string;
  store_id?: number;
}


export async function getCustomerRisk(customerId: number) {
  const response = await api.get<CustomerRiskSummary>(
    `/api/customers/${customerId}/risk`,
  );
  return response.data;
}


export async function reportCustomerRisk(
  customerId: number,
  payload: CustomerRiskReportPayload,
) {
  const response = await api.post<CustomerRiskSummary>(
    `/api/customers/${customerId}/risk/reports`,
    payload,
  );
  return response.data;
}


export async function dismissCustomerRiskReport(customerId: number) {
  const response = await api.delete<CustomerRiskSummary>(
    `/api/customers/${customerId}/risk/reports/mine`,
  );
  return response.data;
}
