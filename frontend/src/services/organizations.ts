import { api } from "./api";

export interface Organization {
  id: number;
  name: string;
  slug: string;
  active: boolean;
  auto_renew_enabled: boolean;

  plan: string;
  plan_name: string;
  subscription_status: string | null;
  trial: {
    status: string;
    started_at: string | null;
    ends_at: string | null;
    days_remaining: number | null;
    ai_response_limit: number;
  };
  billing_period_months: number;
  next_billed_at: string | null;

  pending_plan: string | null;
  pending_billing_period_months: number | null;
  pending_plan_effective_at: string | null;

  active_stores: number;
  active_store_limit: number;

  role: string;
  all_stores: boolean;
  permissions: string[];
}

export async function getCurrentOrganization() {
  const response =
    await api.get<Organization>(
      "/api/organization",
    );

  return response.data;
}


export async function updateAutoRenewEnabled(
  enabled: boolean,
) {
  const response =
    await api.patch<{
      auto_renew_enabled: boolean;
    }>(
      "/api/billing/auto-renew",
      {
        enabled,
      },
    );

  return response.data;
}
