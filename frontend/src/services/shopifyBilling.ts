import { api } from "./api";

export interface ShopifyBillingVerification {
  id: number;
  organization_id: number;
  store_id: number;
  status: string;
  current_plan: string;
  target_plan: string | null;
  target_billing_period_months: number | null;
  observed_at: string;
  requires_review: true;
  applied: false;
}

export interface ShopifyBillingCheck {
  verification_id: number;
  verified_at: string;
  status: string;
  current_plan: string;
  target_plan: string | null;
  target_billing_period_months: number | null;
  requires_review: true;
  applied: false;
}

export interface ShopifyPlanReview {
  id: number;
  organization_id: number;
  verification_id: number;
  store_id: number;
  baseline_plan: string;
  target_plan: string;
  target_billing_period_months: number;
  status: string;
  expires_at: string;
  requires_review: true;
  applied: false;
}

export interface ShopifyReviewAssessment {
  review_id: number;
  organization_id: number;
  status: "ready_for_manual_review" | "blocked";
  ready_for_manual_review: boolean;
  blockers: string[];
  checked_at: string;
  expires_at: string;
  requires_new_shopify_verification_before_activation: true;
  shopify_reverified_now: false;
  activation_allowed: false;
  applied: false;
}

const tenantHeaders = { "X-Diaglob-Global-Scope": "1" };

export async function getShopifyBillingHistory() {
  const response = await api.get<{
    organization_id: number;
    items: ShopifyBillingVerification[];
    applied: false;
  }>("/api/billing/shopify/reconciliation-history", {
    params: { limit: 20 },
    headers: tenantHeaders,
  });
  return response.data;
}

export async function checkShopifyBilling() {
  const response = await api.post<ShopifyBillingCheck>(
    "/api/billing/shopify/reconciliation-check", {}, { headers: tenantHeaders },
  );
  return response.data;
}

export async function getShopifyPlanReviews() {
  const response = await api.get<{
    organization_id: number;
    items: ShopifyPlanReview[];
    applied: false;
  }>("/api/billing/shopify/transition-proposals", {
    params: { limit: 20 },
    headers: tenantHeaders,
  });
  return response.data;
}

export async function stageShopifyPlanReview(verificationId: number) {
  const response = await api.post<ShopifyPlanReview>(
    "/api/billing/shopify/transition-proposals",
    { verification_id: verificationId },
    { headers: tenantHeaders },
  );
  return response.data;
}

export async function assessShopifyPlanReview(reviewId: number) {
  const response = await api.get<ShopifyReviewAssessment>(
    `/api/billing/shopify/transition-proposals/${reviewId}/assessment`,
    { headers: tenantHeaders },
  );
  return response.data;
}


export interface ShopifyBillingCapabilities {
  organization_id: number;
  shopify_hosted_pricing_configured: boolean;
  verified_entitlement_apply_enabled: boolean;
  paddle_checkout_available: false;
  public_plans: string[];
  trial_days: number;
  billing_period_months: number[];
}

export async function getShopifyBillingCapabilities() {
  const response = await api.get<ShopifyBillingCapabilities>(
    "/api/billing/shopify/capabilities", { headers: tenantHeaders },
  );
  return response.data;
}

export async function getShopifyHostedPlanSelection() {
  const response = await api.get<{
    provider: "shopify";
    hosted_by_shopify: true;
    url: string;
    entitlements_applied: false;
  }>("/api/billing/shopify/hosted-plan-selection", { headers: tenantHeaders });
  return response.data;
}

export async function applyVerifiedShopifyPlan(reviewId: number) {
  const response = await api.post<{
    review_id: number;
    organization_id: number;
    applied: boolean;
    already_applied: boolean;
    plan: string;
    billing_period_months: number;
  }>(`/api/billing/shopify/transition-proposals/${reviewId}/apply`, {}, {
    headers: tenantHeaders,
  });
  return response.data;
}


export async function refreshShopifySubscription() {
  const response = await api.post<{
    organization_id: number;
    subscription_status: "active" | "inactive" | "review_required";
    changed: boolean;
    verified_against_shopify: true;
    verification_id: number;
    plan: string;
    applied: boolean;
  }>("/api/billing/shopify/subscription-refresh", {}, {
    headers: tenantHeaders,
  });
  return response.data;
}
