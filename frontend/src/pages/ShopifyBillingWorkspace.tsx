import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertCircle, ArrowRight, CheckCircle2, Clock3, RefreshCw, ShieldCheck,
} from "lucide-react";

import type { Organization } from "../services/organizations";
import { schedulePaddleCancellation, type PaddleBillingStatus } from "../services/billing";
import {
  assessShopifyPlanReview,
  applyVerifiedShopifyPlan,
  checkShopifyBilling,
  getShopifyBillingCapabilities,
  getShopifyHostedPlanSelection,
  refreshShopifySubscription,
  getShopifyBillingHistory,
  getShopifyPlanReviews,
  stageShopifyPlanReview,
  verifyShopifyTrial,
  type ShopifyBillingCapabilities,
  type ShopifyBillingCheck,
  type ShopifyBillingVerification,
  type ShopifyPlanReview,
  type ShopifyReviewAssessment,
  type ShopifyTrialVerification,
} from "../services/shopifyBilling";
import { parseShopifyHostedPricingReturn } from "../services/shopifyBillingReturn";
import {
  BILLING_COPY,
  BILLING_DATE_LOCALE,
  normalizeBillingLocale,
  type BillingCopy,
} from "./shopifyBillingCopy";

interface Props {
  organization: Organization;
  paddleMigrationStatus?: PaddleBillingStatus | null;
  onPaddleMigrationRefresh?: () => void;
}

function billingErrorMessage(error: unknown, copy: BillingCopy): string {
  if (error && typeof error === "object" && "response" in error) {
    const response = (error as { response?: { data?: { detail?: { code?: string } | string }; status?: number } }).response;
    const detail = response?.data?.detail;
    const code = typeof detail === "object" && detail ? detail.code : detail;
    if (typeof code === "string" && Object.prototype.hasOwnProperty.call(copy.knownErrorCodes, code)) {
      return copy.knownErrorCodes[code];
    }
    if (response?.status === 403) return copy.errorForbidden;
    if (response?.status === 409) return copy.errorConflict;
    if (response?.status === 503) return copy.errorUnavailable;
  }
  return copy.errorGeneric;
}

export default function ShopifyBillingWorkspace({
  organization,
  paddleMigrationStatus = null,
  onPaddleMigrationRefresh,
}: Props) {
  const { i18n } = useTranslation();
  const locale = normalizeBillingLocale(i18n.resolvedLanguage || i18n.language);
  const copy = BILLING_COPY[locale];
  // A ref keeps async callbacks in effects on the latest language without
  // re-triggering billing requests when the locale changes.
  const copyRef = useRef(copy);
  useEffect(() => {
    copyRef.current = copy;
  }, [copy]);

  const formatDate = useCallback((value: string) => {
    const date = new Date(value);
    return Number.isNaN(date.getTime())
      ? copy.dateUnavailable
      : new Intl.DateTimeFormat(BILLING_DATE_LOCALE[locale], { dateStyle: "medium", timeStyle: "short" }).format(date);
  }, [copy, locale]);

  const labelStatus = (value: string) => copy.statusLabels[value] ?? copy.reviewRequired;

  const hasBillingAccess = organization.role === "owner" || organization.role === "manager";
  const isOwner = organization.role === "owner";

  const hostedReturnHandled = useRef(false);
  const [history, setHistory] = useState<ShopifyBillingVerification[]>([]);
  const [reviews, setReviews] = useState<ShopifyPlanReview[]>([]);
  const [latestCheck, setLatestCheck] = useState<ShopifyBillingCheck | null>(null);
  const [capabilities, setCapabilities] = useState<ShopifyBillingCapabilities | null>(null);
  const [hostedPricingUrl, setHostedPricingUrl] = useState<string | null>(null);
  const [assessment, setAssessment] = useState<ShopifyReviewAssessment | null>(null);
  const [trialVerification, setTrialVerification] = useState<ShopifyTrialVerification | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"refresh" | "check" | "stage" | "assess" | "hosted" | "apply" | "subscription" | "trial" | "return" | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [migrationBusy, setMigrationBusy] = useState(false);

  async function stopPaddleRenewal() {
    if (!isOwner || migrationBusy || paddleMigrationStatus?.auto_renew_enabled === false) return;
    setMigrationBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await schedulePaddleCancellation();
      if (result.auto_renew_enabled !== false) throw new Error("Renewal remains enabled");
      setNotice(result.effective_at
        ? copy.paddleCancelledOn(formatDate(result.effective_at))
        : copy.paddleRenewalDisabled);
      onPaddleMigrationRefresh?.();
    } catch {
      setError(copy.paddleCancelFailed);
    } finally {
      setMigrationBusy(false);
    }
  }

  const refreshHistory = useCallback(async () => {
    const [checks, proposals] = await Promise.all([
      getShopifyBillingHistory(),
      getShopifyPlanReviews(),
    ]);
    // The API enforces the org scope; discard responses inconsistent with
    // the currently displayed organization as an additional UI guard.
    if (checks.organization_id !== organization.id || proposals.organization_id !== organization.id) {
      throw new Error("Mismatched billing tenant");
    }
    setHistory(checks.items);
    setReviews(proposals.items);
  }, [organization.id]);

  useEffect(() => {
    let mounted = true;
    if (!hasBillingAccess) {
      setLoading(false);
      return () => { mounted = false; };
    }
    setLoading(true);
    Promise.all([
      getShopifyBillingHistory(),
      getShopifyPlanReviews(),
      getShopifyBillingCapabilities(),
    ])
      .then(([checks, proposals, flags]) => {
        if (!mounted) return;
        if (checks.organization_id !== organization.id || proposals.organization_id !== organization.id) {
          setError(copyRef.current.orgMismatch);
          return;
        }
        if (flags.organization_id !== organization.id || flags.paddle_checkout_available !== false) {
          setError(copyRef.current.channelMismatch);
          return;
        }
        setCapabilities(flags);
        setHistory(checks.items);
        setReviews(proposals.items);
      })
      .catch((cause: unknown) => { if (mounted) setError(billingErrorMessage(cause, copyRef.current)); })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, [hasBillingAccess, organization.id]);

  async function run(
    action: "refresh" | "check" | "stage" | "assess" | "hosted" | "apply" | "subscription" | "trial",
    reviewId?: number,
  ) {
    if (!hasBillingAccess || busy) return;
    if ((action === "stage" || action === "apply") && !isOwner) return;
    if (action === "apply" && (
      !capabilities?.verified_entitlement_apply_enabled ||
      !assessment?.ready_for_manual_review ||
      assessment.review_id !== reviewId
    )) return;
    if (action === "apply" && !window.confirm(copy.applyConfirm)) return;
    setBusy(action);
    setError("");
    setNotice("");
    try {
      if (action === "trial") {
        const result = await verifyShopifyTrial();
        if (
          result.organization_id !== organization.id ||
          result.verified_against_shopify !== true ||
          result.applied !== false
        ) {
          throw new Error("Invalid trial verification");
        }
        setTrialVerification(result);
        setNotice(
          result.matches_expected
            ? copy.trialMatches(result.observed_trial_days)
            : copy.trialMismatch(
              result.observed_trial_days === null || result.observed_trial_days === undefined
                ? copy.noTrial
                : `${result.observed_trial_days}${copy.daysSuffix}`,
              result.expected_trial_days,
            ),
        );
      } else if (action === "subscription") {
        const result = await refreshShopifySubscription();
        if (result.organization_id !== organization.id
          || result.verified_against_shopify !== true) {
          throw new Error("Invalid tenant billing state");
        }
        setNotice(result.subscription_status === "active"
          ? copy.subscriptionActive
          : result.subscription_status === "inactive"
            ? copy.subscriptionInactive
            : copy.subscriptionDifferent);
        setAssessment(null);
        await refreshHistory();
      } else if (action === "hosted") {
        const result = await getShopifyHostedPlanSelection();
        if (
          result.provider !== "shopify" || result.hosted_by_shopify !== true ||
          result.entitlements_applied !== false ||
          !result.url.startsWith("https://admin.shopify.com/store/")
        ) throw new Error("Invalid Shopify redirect");
        setHostedPricingUrl(result.url);
        setNotice(copy.openHostedNotice);
      } else if (action === "apply" && reviewId) {
        const result = await applyVerifiedShopifyPlan(reviewId);
        if (result.organization_id !== organization.id) throw new Error("Wrong tenant");
        setAssessment(null);
        await refreshHistory();
        setNotice(result.applied ? copy.planApplied : copy.planAlreadyApplied);
      } else if (action === "check") {
        const result = await checkShopifyBilling();
        if (result.applied !== false || result.requires_review !== true) {
          throw new Error("Unsafe provider response");
        }
        setLatestCheck(result);
        setAssessment(null);
        setNotice(copy.checkRegistered);
        await refreshHistory();
      } else if (action === "stage") {
        const latest = history[0];
        if (!latest || latest.status !== "plan_transition_requires_review" || !latest.target_plan) {
          setError(copy.noTransitionVerification);
          return;
        }
        const result = await stageShopifyPlanReview(latest.id);
        if (result.applied !== false || result.requires_review !== true) {
          throw new Error("Unsafe review response");
        }
        setNotice(copy.reviewPrepared);
        setAssessment(null);
        await refreshHistory();
      } else if (action === "assess" && reviewId) {
        const result = await assessShopifyPlanReview(reviewId);
        if (result.activation_allowed !== false || result.applied !== false || result.shopify_reverified_now !== false) {
          throw new Error("Unsafe assessment response");
        }
        setAssessment(result);
      } else {
        await refreshHistory();
        setAssessment(null);
        setNotice(copy.historyUpdated);
      }
    } catch (cause) {
      setError(billingErrorMessage(cause, copy));
    } finally {
      setBusy(null);
    }
  }

  useEffect(() => {
    if (
      loading ||
      !capabilities ||
      !hasBillingAccess ||
      hostedReturnHandled.current
    ) return;

    // Shopify appends plan_handle to the configured welcome link. Its value is
    // intentionally NOT trusted; presence only triggers fresh Partner checks.
    const hostedReturn = parseShopifyHostedPricingReturn(window.location.search);
    if (!hostedReturn.shouldReverify) return;
    hostedReturnHandled.current = true;

    const cleanedQuery = hostedReturn.cleanedSearch;
    window.history.replaceState(
      {},
      "",
      `${window.location.pathname}${cleanedQuery ? `?${cleanedQuery}` : ""}${window.location.hash}`,
    );

    void (async () => {
      const text = copyRef.current;
      setBusy("return");
      setError("");
      setNotice(text.returnVerifying);
      try {
        const check = await checkShopifyBilling();
        if (check.organization_id !== organization.id || check.applied !== false) {
          throw new Error("Invalid Shopify billing return");
        }
        setLatestCheck(check);
        await refreshHistory();

        if (check.status !== "plan_transition_requires_review") {
          setNotice(check.has_pending_update ? text.returnScheduledChange : text.returnPlanConfirmed);
          return;
        }

        if (!isOwner || !capabilities.verified_entitlement_apply_enabled) {
          setNotice(text.returnOwnerActivation);
          return;
        }

        const review = await stageShopifyPlanReview(check.verification_id);
        const freshAssessment = await assessShopifyPlanReview(review.id);
        if (!freshAssessment.ready_for_manual_review) {
          setAssessment(freshAssessment);
          setNotice(text.returnNeedsRecheck);
          return;
        }

        const applied = await applyVerifiedShopifyPlan(review.id);
        if (applied.organization_id !== organization.id) {
          throw new Error("Wrong tenant on Shopify billing return");
        }
        setAssessment(null);
        await refreshHistory();
        setNotice(applied.applied ? text.returnApplied(applied.plan) : text.returnAlreadyApplied(applied.plan));
      } catch (cause) {
        setError(billingErrorMessage(cause, copyRef.current));
      } finally {
        setBusy(null);
      }
    })();
  }, [
    capabilities,
    hasBillingAccess,
    isOwner,
    loading,
    organization.id,
    refreshHistory,
  ]);

  const first = history[0];
  const mayStage = isOwner && first?.status === "plan_transition_requires_review" && !!first.target_plan;
  const activeReview = reviews.find((item) => item.status === "pending_review");

  return (
    <main className="content shopify-billing-workspace">
      <header className="shopify-billing-heading">
        <div>
          <p className="shopify-billing-eyebrow">DIAGLOB · SHOPIFY APP PRICING</p>
          <h1>{copy.title}</h1>
          <p>{paddleMigrationStatus?.migration_required ? copy.subtitleMigration : copy.subtitle}</p>
        </div>
        <span className="shopify-billing-source"><ShieldCheck size={17} /> {copy.managedInShopify}</span>
      </header>

      <div className="shopify-billing-caution" role="note">
        <AlertCircle size={20} aria-hidden="true" />
        <div>
          <strong>{capabilities?.verified_entitlement_apply_enabled
            ? copy.cautionApplyEnabled
            : copy.cautionApplyDisabled}</strong>
          <p>{copy.cautionBody}</p>
        </div>
      </div>

      {paddleMigrationStatus?.migration_required && (
        <section className="shopify-billing-panel" aria-labelledby="paddle-migration-heading">
          <div className="shopify-billing-panel-title">
            <div>
              <h2 id="paddle-migration-heading">{copy.migrationTitle}</h2>
              <p>{copy.migrationBody}</p>
              <p className="shopify-billing-muted">{copy.paddleStatus}: {paddleMigrationStatus.subscription_status || copy.reviewNeeded}{paddleMigrationStatus.auto_renew_enabled === false ? copy.renewalDisabledSuffix : copy.renewalActiveSuffix}</p>
            </div>
            <button type="button" className="shopify-billing-primary"
              disabled={!isOwner || migrationBusy || paddleMigrationStatus.auto_renew_enabled === false}
              onClick={() => { void stopPaddleRenewal(); }}>
              {paddleMigrationStatus.auto_renew_enabled === false ? copy.renewalDisabledButton : migrationBusy ? copy.renewalCancelling : copy.renewalCancelButton}
            </button>
          </div>
          {error && <p className="shopify-billing-error" role="alert">{error}</p>}
          {notice && <p className="shopify-billing-notice" role="status">{notice}</p>}
        </section>
      )}

      <div className="shopify-billing-stats">
        <section>
          <span>{copy.currentPlan}</span>
          <strong>{organization.plan_name || organization.plan}</strong>
        </section>
        <section>
          <span>{copy.currentStatus}</span>
          <strong>{organization.subscription_status || copy.notConfirmed}</strong>
          <small>{copy.notCurrentVerification}</small>
        </section>
        <section>
          <span>{copy.lastVerification}</span>
          <strong>{first ? formatDate(first.observed_at) : copy.noVerifications}</strong>
        </section>
      </div>

      {!hasBillingAccess ? (
        <section className="shopify-billing-panel">
          <h2>{copy.restrictedTitle}</h2>
          <p>{copy.restrictedBody}</p>
        </section>
      ) : (
        <>
          <section className="shopify-billing-panel">
            <div className="shopify-billing-panel-title">
              <div>
                <h2>{copy.hostedTitle}</h2>
                <p>{copy.hostedBody}</p>
                {capabilities && (
                  <p className="shopify-billing-muted">
                    {copy.plansLabel}: {capabilities.public_plans.map((plan) => (
                      plan.charAt(0).toUpperCase() + plan.slice(1)
                    )).join(" · ")}
                    {" · "}{copy.freeTrial(capabilities.trial_days)}
                    {" · "}{copy.billingLabel(capabilities.billing_period_months.includes(12) ? copy.billingMonthlyOrAnnual : copy.billingMonthly)}.
                  </p>
                )}
              </div>
              <button type="button" className="shopify-billing-primary"
                disabled={Boolean(busy) || loading || !capabilities?.shopify_hosted_pricing_configured}
                onClick={() => { void run("hosted"); }}>
                {busy === "hosted" ? copy.verifyingStore : copy.openShopifyPlans}
              </button>
            </div>
            {hostedPricingUrl && (
              <p className="shopify-billing-notice">
                <a href={hostedPricingUrl} target="_blank" rel="noopener noreferrer">
                  {copy.goToShopifyPlans}
                </a>
              </p>
            )}
            {!capabilities?.shopify_hosted_pricing_configured && (
              <p className="shopify-billing-muted">{copy.hostedNotConfigured}</p>
            )}
          </section>

          <section className="shopify-billing-panel">
            <div className="shopify-billing-panel-title">
              <div>
                <h2>{copy.verificationTitle}</h2>
                <p>{copy.verificationBody}</p>
              </div>
              <div className="shopify-billing-actions">
                <button type="button" className="shopify-billing-secondary" disabled={Boolean(busy) || loading} onClick={() => { void run("refresh"); }}>
                  <RefreshCw size={16} /> {copy.refreshHistory}
                </button>
                {capabilities?.verified_entitlement_apply_enabled && (
                  <button type="button" className="shopify-billing-secondary"
                    disabled={Boolean(busy) || loading || !capabilities?.public_plans.includes(organization.plan)}
                    onClick={() => { void run("subscription"); }}>
                    <RefreshCw size={16} />
                    {busy === "subscription" ? copy.checkingAccess : copy.checkAccess}
                  </button>
                )}
                <button type="button" className="shopify-billing-secondary" disabled={Boolean(busy) || loading} onClick={() => { void run("trial"); }}>
                  <Clock3 size={16} /> {busy === "trial" ? copy.verifyingTrial : copy.verifyTrial(capabilities?.trial_days ?? 3)}
                </button>
                <button type="button" className="shopify-billing-primary" disabled={Boolean(busy) || loading} onClick={() => { void run("check"); }}>
                  <ShieldCheck size={17} /> {busy === "check" ? copy.verifying : copy.verifySubscription}
                </button>
              </div>
            </div>
            {error && <p className="shopify-billing-error" role="alert">{error}</p>}
            {notice && <p className="shopify-billing-notice" role="status">{notice}</p>}
            {loading ? <p role="status">{copy.loadingHistory}</p> : (
              <div className="shopify-billing-list">
                {history.length === 0 && <p>{copy.noHistory}</p>}
                {history.map((item) => (
                  <article key={item.id} className="shopify-billing-record">
                    <div>
                      <strong>{labelStatus(item.status)}</strong>
                      <small>{copy.checkLine(item.id, formatDate(item.observed_at), item.store_id)}</small>
                      <p>{copy.planLabel}: {item.current_plan} {item.target_plan ? <><ArrowRight size={14} aria-hidden="true" /> {item.target_plan}</> : copy.noConfirmedPlan}</p>
                    </div>
                    <span className="shopify-billing-review-pill">{copy.reviewRequired}</span>
                  </article>
                ))}
              </div>
            )}
            {latestCheck && <p className="shopify-billing-muted">{copy.lastSessionCheck(latestCheck.verification_id, formatDate(latestCheck.verified_at))}</p>}
            {trialVerification && (
              <div className="shopify-billing-assessment" role="status">
                <strong>
                  {copy.trialStatus(Boolean(trialVerification.matches_expected))}
                </strong>
                <p>
                  {copy.trialDetails(
                    trialVerification.expected_trial_days,
                    trialVerification.observed_trial_days !== null && trialVerification.observed_trial_days !== undefined
                      ? `${trialVerification.observed_trial_days}${copy.daysSuffix}`
                      : copy.notConfigured,
                    trialVerification.trial_days_remaining !== null && trialVerification.trial_days_remaining !== undefined
                      ? String(trialVerification.trial_days_remaining)
                      : "—",
                  )}
                </p>
                <small>
                  {copy.planLabel} {trialVerification.plan} · {trialVerification.billing_period_months === 12 ? copy.annual : copy.monthly}
                  {trialVerification.trial_ends_at ? copy.endsOn(formatDate(trialVerification.trial_ends_at)) : ""}
                </small>
              </div>
            )}
          </section>

          <section className="shopify-billing-panel">
            <div className="shopify-billing-panel-title">
              <div>
                <h2>{copy.proposalsTitle}</h2>
                <p>{copy.proposalsBody}</p>
              </div>
              {isOwner && (
                <button
                  type="button"
                  className="shopify-billing-secondary"
                  disabled={Boolean(busy) || loading || !mayStage || Boolean(activeReview)}
                  onClick={() => { void run("stage"); }}
                >
                  <Clock3 size={16} /> {busy === "stage" ? copy.preparing : copy.prepareReview}
                </button>
              )}
            </div>
            {isOwner && !mayStage && <p className="shopify-billing-muted">{copy.prepareHint}</p>}
            <div className="shopify-billing-list">
              {reviews.length === 0 && <p>{copy.noProposals}</p>}
              {reviews.map((review) => (
                <article className="shopify-billing-record" key={review.id}>
                  <div>
                    <strong>{labelStatus(review.status)}</strong>
                    <small>{copy.reviewLine(review.id, formatDate(review.expires_at))}</small>
                    <p>{review.baseline_plan} <ArrowRight size={14} aria-hidden="true" /> {review.target_plan} · {review.target_billing_period_months === 12 ? copy.annualCap : copy.monthlyCap}</p>
                  </div>
                  <button type="button" className="shopify-billing-secondary" disabled={Boolean(busy)} onClick={() => { void run("assess", review.id); }}>
                    {copy.checkValidity}
                  </button>
                </article>
              ))}
            </div>
            {assessment && (
              <div className="shopify-billing-assessment" role="status">
                <strong>{copy.assessmentTitle(assessment.review_id, Boolean(assessment.ready_for_manual_review))}</strong>
                <p>{assessment.ready_for_manual_review ? copy.assessmentReady : copy.assessmentBlocked}</p>
                {assessment.blockers.length > 0 && (
                  <ul>{assessment.blockers.map((code) => <li key={code}>{copy.explanations[code] ?? copy.newVerificationRequired}</li>)}</ul>
                )}
                <small>{copy.checkedAt(formatDate(assessment.checked_at))}</small>
                {isOwner && capabilities?.verified_entitlement_apply_enabled && assessment.ready_for_manual_review && (
                  <button type="button" className="shopify-billing-primary"
                    disabled={Boolean(busy)}
                    onClick={() => { void run("apply", assessment.review_id); }}>
                    {busy === "apply" ? copy.confirmingWithShopify : copy.applyVerifiedPlan}
                  </button>
                )}
              </div>
            )}
          </section>
        </>
      )}

      <footer className="shopify-billing-footer">
        <CheckCircle2 size={18} aria-hidden="true" />
        <span>{copy.footer}</span>
      </footer>
    </main>
  );
}
