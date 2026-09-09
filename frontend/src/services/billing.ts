import { api } from "./api";


export interface BillingCheckoutResponse {
  plan: string;
  transaction_id: string;
  checkout_url: string;
}


export interface BillingUpgradeSummaryAmount {
  amount: string;
  currency_code: string;
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


export interface BillingUpgradePayableAmount {
  amount: string;
  currencyCode: string;
}


export function getBillingUpgradePayableAmount(
  preview: BillingUpgradePreview,
): BillingUpgradePayableAmount | null {
  const result = preview.update_summary?.result;
  const resultAmount = Number(result?.amount ?? "");

  if (
    result &&
    result.action === "charge" &&
    Number.isFinite(resultAmount) &&
    resultAmount > 0
  ) {
    return {
      amount: String(Math.trunc(resultAmount)),
      currencyCode:
        result.currency_code ||
        preview.currency_code ||
        "USD",
    };
  }

  const amountDue = Number(preview.amount_due ?? "");

  if (
    Number.isFinite(amountDue) &&
    amountDue > 0
  ) {
    return {
      amount: String(Math.trunc(amountDue)),
      currencyCode:
        preview.currency_code ||
        result?.currency_code ||
        "USD",
    };
  }

  const charge = preview.update_summary?.charge;
  const chargeAmount = Number(charge?.amount ?? "");

  if (
    charge &&
    Number.isFinite(chargeAmount) &&
    chargeAmount > 0
  ) {
    return {
      amount: String(Math.trunc(chargeAmount)),
      currencyCode:
        charge.currency_code ||
        preview.currency_code ||
        "USD",
    };
  }

  return null;
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

  return response.data;
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
