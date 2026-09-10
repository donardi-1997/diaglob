import { api } from "./api";
import {
  getBillingUpgradePayableAmount,
  normalizeBillingUpgradePreview,
  type BillingUpgradePayableAmount,
  type BillingUpgradeSummaryAmount,
} from "./billingPreview";

export type {
  BillingUpgradePayableAmount,
  BillingUpgradeSummaryAmount,
};

export { getBillingUpgradePayableAmount };


export interface BillingCheckoutResponse {
  plan: string;
  transaction_id: string;
  checkout_url: string;
}


export interface BillingUpgradePreview {
  current_plan: string;
  target_plan: string;
  subscription_id: string;
  next_billed_at: string | null;
  currency_code: string | null;
  amount_due: string | null;
  subtotal: string | null;
  tax: string | null;
  _source?: "paddle" | "local";

  update_summary?: {
    credit?: BillingUpgradeSummaryAmount;
    charge?: BillingUpgradeSummaryAmount;
    result?: {
      action: string;
      amount: string;
      currency_code: string;
    };
  };

  immediate_transaction?: unknown;
  next_transaction?: unknown;
}


export interface BillingUpgradeResponse {
  ok: boolean;
  current_plan: string;
  target_plan: string;
  subscription_id: string;
  paddle_status: string | null;
  next_billed_at: string | null;
  message: string;
}


export async function createBillingCheckout(
  plan: string,
  billingPeriodMonths: number = 1,
): Promise<BillingCheckoutResponse> {
  const response =
    await api.post<BillingCheckoutResponse>(
      "/api/billing/checkout",
      {
        plan,
        billing_period_months:
          billingPeriodMonths,
      },
    );

  return response.data;
}


export async function previewBillingUpgrade(
  plan: string,
): Promise<BillingUpgradePreview> {
  const response =
    await api.post<BillingUpgradePreview>(
      "/api/billing/upgrade/preview",
      {
        plan,
      },
    );

  return normalizeBillingUpgradePreview(
    response.data,
  );
}


export async function applyBillingUpgrade(
  plan: string,
): Promise<BillingUpgradeResponse> {
  const response =
    await api.post<BillingUpgradeResponse>(
      "/api/billing/upgrade",
      {
        plan,
      },
    );

  return response.data;
}


export interface BillingDowngradeStore {
  id: number;
  name: string;
  active: boolean;
  active_since: string | null;
}


export interface BillingDowngradePreview {
  ok: boolean;
  current_plan: string;
  target_plan: string;

  current_billing_period_months: number;
  target_billing_period_months: number;

  subscription_id: string;
  effective_at: string | null;
  next_billed_at: string | null;

  target_store_limit: number;
  requires_store_selection: boolean;
  available_stores: BillingDowngradeStore[];

  immediate_transaction?: unknown;
  next_transaction?: unknown;
}


export interface BillingDowngradeResponse {
  ok: boolean;
  current_plan: string;
  pending_plan: string;
  pending_billing_period_months: number;
  effective_at: string | null;
  subscription_id: string;
  paddle_status: string | null;
  next_billed_at?: string | null;
  message: string;
}


export async function previewBillingDowngrade(
  plan: string,
  billingPeriodMonths: number,
): Promise<BillingDowngradePreview> {
  const response =
    await api.post<BillingDowngradePreview>(
      "/api/billing/downgrade/preview",
      {
        plan,
        billing_period_months:
          billingPeriodMonths,
      },
    );

  return response.data;
}


export async function applyBillingDowngrade(
  plan: string,
  billingPeriodMonths: number,
  storeIds: number[] = [],
): Promise<BillingDowngradeResponse> {
  const response =
    await api.post<BillingDowngradeResponse>(
      "/api/billing/downgrade",
      {
        plan,
        billing_period_months:
          billingPeriodMonths,
        store_ids: storeIds,
      },
    );

  return response.data;
}


export async function cancelBillingDowngrade(): Promise<{
  ok: boolean;
  pending_plan: string | null;
  message?: string;
}> {
  const response =
    await api.delete(
      "/api/billing/downgrade",
    );

  return response.data;
}


export interface AiUsagePackage {
  key: string;
  responses: number;
  price_usd: string;
  currency: string;
  configured: boolean;
}

export interface AiUsageSummary {
  plan: string;
  included_ai_responses: number;
  used_ai_responses: number;
  remaining_included_ai_responses: number;
  extra_ai_responses_purchased: number;
  extra_ai_responses_remaining: number;
  remaining_ai_responses: number;
  usage_percent: number;
  overage_ai_responses: number;
  status: string;
  usage_period_start: string | null;
  usage_period_end: string | null;
}

export interface AiUsagePackagesResponse {
  packages: AiUsagePackage[];
  usage: AiUsageSummary;
}

export interface AiUsagePackageCheckoutResponse {
  package_key: string;
  responses: number;
  price_usd: string;
  currency: string;
  transaction_id: string;
  checkout_url: string;
}

export async function getAiUsagePackages(): Promise<AiUsagePackagesResponse> {
  const response = await api.get<AiUsagePackagesResponse>(
    "/api/billing/ai-packages",
  );
  return response.data;
}

export async function createAiUsagePackageCheckout(
  packageKey: string,
): Promise<AiUsagePackageCheckoutResponse> {
  const response = await api.post<AiUsagePackageCheckoutResponse>(
    "/api/billing/ai-packages/checkout",
    { package_key: packageKey },
  );
  return response.data;
}
