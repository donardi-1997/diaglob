import { api } from "./api";
import type { CustomerRiskReason } from "./customerRisk";


export type RiskReportStatus = "pending" | "confirmed" | "disputed" | "dismissed";
export type RiskDisputeStatus = "open" | "accepted" | "rejected" | "withdrawn";
export type ReporterReputationLevel = "new" | "trusted" | "watch" | "established";

export interface ReporterReputation {
  score: number;
  level: ReporterReputationLevel;
  moderated_reports: number;
  confirmed_reports: number;
  dismissed_reports: number;
  disputed_reports: number;
  pending_reports: number;
}

export interface AdminRiskStats {
  reports: {
    total: number;
    pending: number;
    confirmed: number;
    disputed: number;
    dismissed: number;
  };
  disputes: {
    total: number;
    open: number;
    accepted: number;
    rejected: number;
    withdrawn: number;
  };
  limits: {
    report_writes_24h: number;
    dispute_writes_24h: number;
  };
}

export interface AdminRiskModerationAnalytics {
  window: {
    days: number;
    from: string;
    to: string;
  };
  summary: {
    reports_created: number;
    moderated_reports: number;
    moderation_actions: number;
    disputes_created: number;
    disputes_resolved: number;
    average_report_resolution_hours: number | null;
    average_dispute_resolution_hours: number | null;
    confirmation_rate: number;
    appeal_acceptance_rate: number;
  };
  outcomes: {
    reports: {
      confirmed: number;
      dismissed: number;
      disputed: number;
      reset_pending: number;
    };
    disputes: {
      accepted: number;
      rejected: number;
    };
  };
  backlog: {
    pending_reports: number;
    disputed_reports: number;
    open_disputes: number;
    pending_reports_over_24h: number;
    open_disputes_over_24h: number;
  };
  daily: Array<{
    date: string;
    reports_created: number;
    reports_moderated: number;
    disputes_created: number;
    disputes_resolved: number;
  }>;
  reason_breakdown: Array<{
    reason: CustomerRiskReason;
    count: number;
    percentage: number;
  }>;
  reporting_organizations: Array<{
    organization_id: number;
    organization_name: string | null;
    report_count: number;
    evidence_rate: number;
    confirmed: number;
    dismissed: number;
    disputed: number;
    pending: number;
    dismissal_rate: number;
  }>;
  governance_note: string;
}

export interface AdminRiskReportListItem {
  id: number;
  status: RiskReportStatus;
  reason: CustomerRiskReason;
  reporter_organization_id: number;
  reporter_organization_name: string | null;
  reporter_user_id: number | null;
  reporter_label: string | null;
  has_notes: boolean;
  has_evidence: boolean;
  open_disputes: number;
  reporter_reputation: ReporterReputation;
  priority_score: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface AdminRiskDisputeListItem {
  id: number;
  status: RiskDisputeStatus;
  requester_organization_id: number;
  requester_organization_name: string | null;
  requester_user_id: number | null;
  requester_label: string | null;
  local_customer_id: number | null;
  statement: string;
  evidence_reference: string | null;
  resolution_note: string | null;
  resolved_by_user_id: number | null;
  resolved_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface RiskAuditEvent {
  id: number;
  actor_role: string;
  actor_user_id: number | null;
  actor_label: string | null;
  action: string;
  from_status: string | null;
  to_status: string | null;
  note: string | null;
  created_at: string | null;
}

export interface AdminRiskReportDetail {
  id: number;
  status: RiskReportStatus;
  reason: CustomerRiskReason;
  notes: string | null;
  evidence_reference: string | null;
  reporter: {
    organization_id: number;
    organization_name: string | null;
    user_id: number | null;
    user_label: string | null;
    store_id: number | null;
    reputation: ReporterReputation;
  };
  customer: {
    id: number;
    name: string;
    email_masked: string | null;
    phone_masked: string | null;
    country_code: string | null;
  } | null;
  disputes: AdminRiskDisputeListItem[];
  audit: RiskAuditEvent[];
  created_at: string | null;
  updated_at: string | null;
}

export interface AdminRiskDisputeDetail extends AdminRiskDisputeListItem {
  customer: AdminRiskReportDetail["customer"];
  matching_reports: Array<{
    id: number;
    status: RiskReportStatus;
    reason: CustomerRiskReason;
    reporter_organization_id: number;
    reporter_organization_name: string | null;
    has_evidence: boolean;
    updated_at: string | null;
  }>;
  audit: RiskAuditEvent[];
}

export async function getAdminRiskStats() {
  const response = await api.get<AdminRiskStats>("/api/admin/customer-risk/stats");
  return response.data;
}

export async function getAdminRiskAnalytics(days = 30) {
  const response = await api.get<AdminRiskStats & { analytics: AdminRiskModerationAnalytics }>(
    "/api/admin/customer-risk/stats",
    { params: { analytics_days: days } },
  );
  return response.data.analytics;
}

export async function listAdminRiskReports(params?: {
  page?: number;
  page_size?: number;
  status?: RiskReportStatus | "";
  reason?: CustomerRiskReason | "";
}) {
  const response = await api.get<{
    items: AdminRiskReportListItem[];
    total: number;
    page: number;
    page_size: number;
  }>("/api/admin/customer-risk/reports", { params });
  return response.data;
}

export async function getAdminRiskReport(reportId: number) {
  const response = await api.get<AdminRiskReportDetail>(
    `/api/admin/customer-risk/reports/${reportId}`,
  );
  return response.data;
}

export async function moderateAdminRiskReport(
  reportId: number,
  payload: {
    action: "confirm" | "dismiss" | "mark_disputed" | "reset_pending";
    note: string;
  },
) {
  const response = await api.patch<AdminRiskReportDetail>(
    `/api/admin/customer-risk/reports/${reportId}/moderation`,
    payload,
  );
  return response.data;
}

export async function listAdminRiskDisputes(params?: {
  page?: number;
  page_size?: number;
  status?: RiskDisputeStatus | "";
}) {
  const response = await api.get<{
    items: AdminRiskDisputeListItem[];
    total: number;
    page: number;
    page_size: number;
  }>("/api/admin/customer-risk/disputes", { params });
  return response.data;
}

export async function getAdminRiskDispute(disputeId: number) {
  const response = await api.get<AdminRiskDisputeDetail>(
    `/api/admin/customer-risk/disputes/${disputeId}`,
  );
  return response.data;
}

export async function resolveAdminRiskDispute(
  disputeId: number,
  payload: { outcome: "accepted" | "rejected"; note: string },
) {
  const response = await api.patch<AdminRiskDisputeDetail>(
    `/api/admin/customer-risk/disputes/${disputeId}/resolution`,
    payload,
  );
  return response.data;
}