import { initializePaddle, type Paddle } from "@paddle/paddle-js";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { getCurrentOrganization,
  updateAutoRenewEnabled,
} from "../services/organizations";
import {
  applyBillingDowngrade,
  applyBillingUpgrade,
  cancelBillingDowngrade,
  createBillingCheckout,
  previewBillingDowngrade,
  previewBillingUpgrade,
  type BillingDowngradePreview,
  type BillingUpgradePreview,
} from "../services/billing";

import AiUsagePackagesSection from "../components/AiUsagePackagesSection";
import { getPaddleInitializationOptions } from "../config/paddle";

import { Check, Crown, Rocket, Sparkles, Store, Zap } from "lucide-react";

const plans = [
  {
    id: "starter",
    name: "Starter",
    prices: {
      1: 19,
      3: 54,
      6: 103,
      12: 190,
    },
    stores: 1,
    icon: Sparkles,
    descriptionKey: "starterDescription",
    featureKeys: [
      "starterFeature1",
      "starterFeature2",
      "starterFeature3",
      "starterFeature4",
      "starterFeature5",
      "starterFeature6",
    ],
  },

  {
    id: "growth",
    name: "Growth",
    prices: {
      1: 49,
      3: 140,
      6: 265,
      12: 490,
    },
    stores: 2,
    icon: Zap,
    descriptionKey: "growthDescription",
    featureKeys: [
      "growthFeature1",
      "growthFeature2",
      "growthFeature3",
      "growthFeature4",
      "growthFeature5",
      "growthFeature6",
    ],
  },

  {
    id: "pro",
    name: "Pro",
    prices: {
      1: 99,
      3: 282,
      6: 535,
      12: 990,
    },
    stores: 5,
    icon: Rocket,
    recommended: true,
    descriptionKey: "proDescription",
    featureKeys: [
      "proFeature1",
      "proFeature2",
      "proFeature3",
      "proFeature4",
      "proFeature5",
      "proFeature6",
    ],
  },

  {
    id: "scale",
    name: "Scale",
    prices: {
      1: 199,
      3: 570,
      6: 1075,
      12: 1990,
    },
    stores: 10,
    icon: Crown,
    descriptionKey: "scaleDescription",
    featureKeys: [
      "scaleFeature1",
      "scaleFeature2",
      "scaleFeature3",
      "scaleFeature4",
      "scaleFeature5",
      "scaleFeature6",
    ],
  },
];

type BillingPeriod = 1 | 3 | 6 | 12;


const billingPeriods: Array<{
  months: BillingPeriod;
  labelKey: string;
  badgeKey?: string;
}> = [
  {
    months: 1,
    labelKey: "billing1Month",
  },
  {
    months: 3,
    labelKey: "billing3Months",
    badgeKey: "billingSave5",
  },
  {
    months: 6,
    labelKey: "billing6Months",
    badgeKey: "billingSave10",
  },
  {
    months: 12,
    labelKey: "billing12Months",
    badgeKey: "billingSave2Months",
  },
];


function getPeriodLabelKey(
  months: BillingPeriod,
) {
  if (months === 1) {
    return "billingI18nUnitMonth";
  }

  if (months === 12) {
    return "billingI18nUnitYear";
  }

  return "billingI18nUnitMonths";
}


const planOrder: Record<string, number> = {
  none: 0,
  starter: 1,
  growth: 2,
  pro: 3,
  scale: 4,
};


function moneyFromMinorUnits(
  amount: string | null | undefined,
  currency = "USD",
) {
  const value = Number(amount || 0) / 100;

  return new Intl.NumberFormat("es-CO", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
  }).format(value);
}


function formatBillingDate(
  value: string | null | undefined,
  locale = "es-CO",
) {
  if (!value) {
    return "—";
  }

  return new Intl.DateTimeFormat(locale, {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date(value));
}


function getDaysUntilBilling(
  value: string | null | undefined,
) {
  if (!value) {
    return null;
  }

  const target = new Date(value);

  if (Number.isNaN(target.getTime())) {
    return null;
  }

  const remainingMs =
    target.getTime() - Date.now();

  if (remainingMs <= 0) {
    return 0;
  }

  return Math.ceil(
    remainingMs / (
      1000 *
      60 *
      60 *
      24
    ),
  );
}


export default function PlansPage() {
  const { t, i18n } = useTranslation();
  const [currentPlan, setCurrentPlan] = useState<string | null>(null);

  const [selectedPlan, setSelectedPlan] =
    useState<string>("pro");

  const [
    currentBillingPeriod,
    setCurrentBillingPeriod,
  ] = useState<BillingPeriod>(1);

  const [
    nextBilledAt,
    setNextBilledAt,
  ] = useState<string | null>(null);

  const [
    selectedBillingPeriod,
    setSelectedBillingPeriod,
  ] = useState<BillingPeriod>(1);


  const [pendingPlan, setPendingPlan] =
    useState<string | null>(null);

  const [
    pendingBillingPeriod,
    setPendingBillingPeriod,
  ] = useState<number | null>(null);

  const [
    autoRenewEnabled,
    setAutoRenewEnabled,
  ] = useState(false);

  const [
    autoRenewSaving,
    setAutoRenewSaving,
  ] = useState(false);


  const [pendingPlanEffectiveAt, setPendingPlanEffectiveAt] =
    useState<string | null>(null);

  const [cancelingDowngrade, setCancelingDowngrade] =
    useState(false);

  const [loadingPlan, setLoadingPlan] = useState(true);

  const [checkoutPlan, setCheckoutPlan] = useState<string | null>(null);

  const [checkoutError, setCheckoutError] = useState("");

  const [paddle, setPaddle] = useState<Paddle | undefined>(undefined);

  const [upgradePreview, setUpgradePreview] =
    useState<BillingUpgradePreview | null>(
      null,
    );

  const [upgradePlan, setUpgradePlan] =
    useState<string | null>(null);

  const [upgradeSubmitting, setUpgradeSubmitting] =
    useState(false);

  const [upgradePrices, setUpgradePrices] =
    useState<Record<string, string>>({});

  const [upgradePreviewStatus, setUpgradePreviewStatus] =
    useState<Record<string, "loading" | "ready" | "error">>({});

  const [downgradePreview, setDowngradePreview] =
    useState<BillingDowngradePreview | null>(
      null,
    );

  const [downgradePlan, setDowngradePlan] =
    useState<string | null>(null);

  const [downgradeSubmitting, setDowngradeSubmitting] =
    useState(false);

  const [downgradeStoreIds, setDowngradeStoreIds] =
    useState<number[]>([]);

  const billingLocale =
    i18n.language?.toLowerCase().startsWith("en")
      ? "en-US"
      : "es-CO";

  const daysUntilRenewal =
    getDaysUntilBilling(
      nextBilledAt,
    );

  const getBillingPeriodLabel = (
    period: number,
  ) => {
    if (period === 1) {
      return t("billing1Month");
    }

    if (period === 3) {
      return t("billing3Months");
    }

    if (period === 6) {
      return t("billing6Months");
    }

    return t("billing12Months");
  };

  const currentBillingPeriodLabel =
    getBillingPeriodLabel(
      currentBillingPeriod,
    );


  async function handleToggleAutoRenew() {
    if (autoRenewSaving) {
      return;
    }

    const nextValue =
      !autoRenewEnabled;

    try {
      setAutoRenewSaving(true);
      setCheckoutError("");

      const result =
        await updateAutoRenewEnabled(
          nextValue,
        );

      setAutoRenewEnabled(
        result.auto_renew_enabled,
      );

    } catch (error: any) {
      console.error(
        "Unable to update auto-renew",
        error,
      );

      setCheckoutError(
        error?.response?.data?.detail
        || t("plansAutoRenewUpdateError"),
      );
    } finally {
      setAutoRenewSaving(false);
    }
  }


  async function handleChoosePlan(plan: string) {
    try {
      setCheckoutError("");

      const normalizedCurrent =
        (currentPlan || "none").toLowerCase();

      const currentRank =
        planOrder[normalizedCurrent] ?? 0;

      const targetRank =
        planOrder[plan] ?? 0;

      // ======================================================
      // CAMBIO DE PERIODO
      // ======================================================
      // La prorrata SOLO puede aplicarse cuando el nuevo plan
      // conserva exactamente el mismo periodo de facturación.
      //
      // Ejemplo permitido:
      // Starter 1M -> Growth 1M
      //
      // Ejemplo NO permitido como upgrade inmediato:
      // Starter 1M -> Growth 3M
      // ======================================================


      // ======================================================
      // PLAN ACTUAL
      // ======================================================

      if (plan === normalizedCurrent) {
        return;
      }

      // ======================================================
      // DOWNGRADE
      // ======================================================

      if (
        currentRank > 0 &&
        targetRank < currentRank
      ) {
        setCheckoutPlan(plan);

        const preview =
          await previewBillingDowngrade(
            plan,
            currentBillingPeriod,
          );

        setDowngradePreview(
          preview,
        );

        if (
          preview.requires_store_selection
        ) {
          setDowngradeStoreIds(
            preview.available_stores
              .filter(
                (store) => store.active,
              )
              .slice(
                0,
                preview.target_store_limit,
              )
              .map(
                (store) => store.id,
              ),
          );
        } else {
          setDowngradeStoreIds([]);
        }

        setDowngradePlan(
          plan,
        );

        setCheckoutPlan(null);

        return;
      }

      // ======================================================
      // UPGRADE DE SUSCRIPCIÓN EXISTENTE
      // ======================================================

      if (
        currentRank > 0 &&
        targetRank > currentRank
      ) {
        setCheckoutPlan(plan);

        const preview =
          await previewBillingUpgrade(plan);

        setUpgradePreview(preview);
        setUpgradePlan(plan);
        setCheckoutPlan(null);

        return;
      }

      // ======================================================
      // PRIMERA CONTRATACIÓN
      // ======================================================

      setCheckoutPlan(plan);

      const checkout =
        await createBillingCheckout(
          plan,
          selectedBillingPeriod,
        );

      if (!checkout.checkout_url) {
        throw new Error(
          t("plansMissingCheckoutUrl"),
        );
      }

      if (!paddle) {
        throw new Error(
          t("plansPaddleNotReady"),
        );
      }

      paddle.Checkout.open({
        transactionId:
          checkout.transaction_id,
      });

    } catch (error: any) {
      const detail =
        error?.response?.data?.detail;

      if (typeof detail === "string") {
        setCheckoutError(detail);
      } else if (
        typeof detail?.message === "string"
      ) {
        setCheckoutError(
          detail.message,
        );
      } else {
        setCheckoutError(
          t("plansPlanChangeError"),
        );
      }

      setCheckoutPlan(null);
    }
  }


  async function handleConfirmUpgrade() {
    if (!upgradePlan) {
      return;
    }

    try {
      setCheckoutError("");
      setUpgradeSubmitting(true);

      await applyBillingUpgrade(
        upgradePlan,
      );

      setUpgradePreview(null);
      setUpgradePlan(null);

      // Paddle confirmará el cambio mediante webhook.
      // Damos un pequeño margen y volvemos a consultar.
      window.setTimeout(
        async () => {
          try {
            const organization =
              await getCurrentOrganization();

            setCurrentPlan(
              organization.plan,
            );
          } catch (error) {
            console.error(
              "Unable to refresh plan",
              error,
            );
          }
        },
        2000,
      );

    } catch (error: any) {
      const detail =
        error?.response?.data?.detail;

      if (typeof detail === "string") {
        setCheckoutError(detail);
      } else if (
        typeof detail?.message === "string"
      ) {
        setCheckoutError(
          detail.message,
        );
      } else {
        setCheckoutError(
          t("plansUpgradeError"),
        );
      }

    } finally {
      setUpgradeSubmitting(false);
    }
  }


  async function handleCancelScheduledDowngrade() {
    try {
      setCheckoutError("");
      setCancelingDowngrade(true);

      await cancelBillingDowngrade();

      const organization =
        await getCurrentOrganization();

      setCurrentPlan(
        organization.plan,
      );

      setAutoRenewEnabled(
        Boolean(
          organization.auto_renew_enabled
        ),
      );

      setNextBilledAt(
        organization.next_billed_at || null,
      );

      setPendingPlan(
        organization.pending_plan,
      );

      setPendingBillingPeriod(
        organization.pending_billing_period_months
          ?? null,
      );

      setPendingPlanEffectiveAt(
        organization.pending_plan_effective_at,
      );

      setCheckoutError(
        t("plansScheduledChangeCanceled"),
      );

    } catch (error: any) {
      const detail =
        error?.response?.data?.detail;

      if (typeof detail === "string") {
        setCheckoutError(detail);
      } else if (
        typeof detail?.message === "string"
      ) {
        setCheckoutError(
          detail.message,
        );
      } else {
        setCheckoutError(
          t("plansScheduledChangeCancelError"),
        );
      }

    } finally {
      setCancelingDowngrade(false);
    }
  }


  async function handleConfirmDowngrade() {
    if (!downgradePlan) {
      return;
    }

    try {
      setCheckoutError("");
      setDowngradeSubmitting(true);

      await applyBillingDowngrade(
        downgradePlan,
        downgradePreview
          ?.target_billing_period_months
          ?? currentBillingPeriod,
        downgradeStoreIds,
      );

      setDowngradePreview(null);
      setDowngradePlan(null);

      const organization =
        await getCurrentOrganization();

      setCurrentPlan(
        organization.plan,
      );

      setAutoRenewEnabled(
        Boolean(
          organization.auto_renew_enabled
        ),
      );

      setNextBilledAt(
        organization.next_billed_at || null,
      );

      setPendingPlan(
        organization.pending_plan,
      );

      setPendingBillingPeriod(
        organization.pending_billing_period_months
          ?? null,
      );

      setPendingPlanEffectiveAt(
        organization.pending_plan_effective_at,
      );

      setCheckoutError(
        t("plansScheduledChangeSuccess"),
      );

    } catch (error: any) {
      const detail =
        error?.response?.data?.detail;

      if (typeof detail === "string") {
        setCheckoutError(detail);
      } else if (
        typeof detail?.message === "string"
      ) {
        setCheckoutError(
          detail.message,
        );
      } else {
        setCheckoutError(
          t("plansDowngradeScheduleError"),
        );
      }

    } finally {
      setDowngradeSubmitting(false);
    }
  }


  useEffect(() => {
    if (!currentPlan) {
      return;
    }

    const normalizedCurrent =
      currentPlan.toLowerCase();

    const currentRank =
      planOrder[normalizedCurrent] ?? 0;

    if (currentRank <= 0) {
      setUpgradePrices({});
      return;
    }

    let mounted = true;

    async function loadUpgradePrices() {
      setUpgradePrices({});

      const nextPrices:
        Record<string, string> = {};

      const nextStatus:
        Record<string, "loading" | "ready" | "error"> = {};

      for (const plan of plans) {
        const targetRank =
          planOrder[plan.id] ?? 0;

        if (targetRank <= currentRank) {
          continue;
        }

        if (
          selectedBillingPeriod !==
          currentBillingPeriod
        ) {
          continue;
        }

        nextStatus[plan.id] = "loading";

        try {
          const preview =
            await previewBillingUpgrade(
              plan.id,
            );

          const result =
            preview.update_summary?.result;

          if (
            !result ||
            result.action !== "charge" ||
            Number(result.amount) <= 0
          ) {
            nextStatus[plan.id] = "error";
            continue;
          }

          const currency =
            preview.currency_code ||
            preview.update_summary
              ?.result
              ?.currency_code ||
            "USD";

          nextPrices[plan.id] =
            moneyFromMinorUnits(
              preview.amount_due,
              currency,
            );

          nextStatus[plan.id] = "ready";

        } catch (error) {
          nextStatus[plan.id] = "error";

          console.error(
            `Unable to calculate upgrade to ${plan.id}`,
            error,
          );
        }
      }

      if (mounted) {
        setUpgradePrices(
          nextPrices,
        );

        setUpgradePreviewStatus(
          nextStatus,
        );
      }
    }

    loadUpgradePrices();

    return () => {
      mounted = false;
    };
  }, [
    currentPlan,
    currentBillingPeriod,
    selectedBillingPeriod,
  ]);


  useEffect(() => {
    try {
      const options = getPaddleInitializationOptions(
        import.meta.env.VITE_PADDLE_ENVIRONMENT,
        import.meta.env.VITE_PADDLE_CLIENT_TOKEN,
      );

      initializePaddle(options)
        .then((instance) => {
          setPaddle(instance);
        })
        .catch((error) => {
          console.error("Unable to initialize Paddle", error);
        });
    } catch (error) {
      console.error("Invalid Paddle frontend configuration", error);
    }
  }, []);

  useEffect(() => {
    let mounted = true;

    async function loadPlan() {
      try {
        const organization = await getCurrentOrganization();

        if (mounted) {
          setCurrentPlan(
            organization.plan,
          );

          const organizationPeriod =
            (
              [1, 3, 6, 12].includes(
                Number(
                  organization.billing_period_months
                ),
              )
                ? Number(
                    organization.billing_period_months
                  )
                : 1
            ) as BillingPeriod;

          const normalizedPlan =
            (
              organization.plan
              || "none"
            ).toLowerCase();

          const hasActivePlan =
            normalizedPlan !== "none";

          if (hasActivePlan) {
            setCurrentBillingPeriod(
              organizationPeriod,
            );

            setSelectedBillingPeriod(
              organizationPeriod,
            );

            setSelectedPlan(
              normalizedPlan,
            );
          } else {
            setCurrentBillingPeriod(1);
            setSelectedBillingPeriod(1);

            // Sin suscripción:
            // Pro es la opción mostrada por defecto.
            setSelectedPlan("pro");
          }

          setAutoRenewEnabled(
            Boolean(
              organization.auto_renew_enabled
            ),
          );

          setNextBilledAt(
            organization.next_billed_at || null,
          );

          setPendingPlan(
            organization.pending_plan,
          );

          setPendingBillingPeriod(
            organization.pending_billing_period_months
              ?? null,
          );

          setPendingPlanEffectiveAt(
            organization.pending_plan_effective_at,
          );
        }
      } catch (error) {
        console.error("Unable to load current plan", error);
      } finally {
        if (mounted) {
          setLoadingPlan(false);
        }
      }
    }

    loadPlan();

    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div className="content plans-page">
      <section className="page-heading">
        <div>
          <span className="eyebrow">DIAGLOB COMMERCE</span>

          <h1>{t("plansTitle")}</h1>

          <p>{t("plansSubtitle")}</p>
        </div>
      </section>

      {pendingPlan && (
        <div className="scheduled-plan-banner">
          <div className="scheduled-plan-banner-icon">
            !
          </div>

          <div className="scheduled-plan-banner-content">
            <span className="scheduled-plan-banner-kicker">
              {t("plansI18nScheduledBannerTitle")}
            </span>

            <strong>
              {t("plansI18nYourPlanWillChangeFrom")}{" "}
              {plans.find(
                (plan) =>
                  plan.id ===
                  currentPlan?.toLowerCase(),
              )?.name || currentPlan}
              {" · "}
              {getBillingPeriodLabel(
                currentBillingPeriod,
              )}
              {" "}{t("plansChangeToConnector")}{" "}
              {plans.find(
                (plan) =>
                  plan.id === pendingPlan,
              )?.name || pendingPlan}
              {" · "}
              {getBillingPeriodLabel(
                pendingBillingPeriod
                  ?? currentBillingPeriod,
              )}
            </strong>

            <p>
              {t("plansChangeDate")}{" "}
              <b>
                {formatBillingDate(
                  pendingPlanEffectiveAt,
                )}
              </b>
              {" "}
              {t("plansI18nKeepCurrentFeaturesUntilThen")}
            </p>
          </div>

          <button
            type="button"
            className="scheduled-plan-cancel"
            disabled={cancelingDowngrade}
            onClick={handleCancelScheduledDowngrade}
          >
            {cancelingDowngrade
              ? t("plansCanceling")
              : t("plansCancelScheduledChange")}
          </button>
        </div>
      )}

      {currentPlan?.toLowerCase() === "none" && (
        <div className="plans-current-status">
          <strong>{t("plansNoActivePlan")}</strong>
          <br></br>
          <span>{t("plansNoActivePlanHelp")}</span>
        </div>
      )}

      {checkoutError && (
        <div className="plans-checkout-error">{checkoutError}</div>
      )}

      <section className="billing-period-section">
        <div className="billing-period-heading">
          <div>
            <span className="eyebrow">
              {t("plansBillingEyebrow")}
            </span>

            <h2>
              {t("plansChoosePayment")}
            </h2>

            <p>
              {t("plansPaymentHelp")}
            </p>
          </div>

          {currentPlan &&
            currentPlan.toLowerCase() !== "none" && (
              <div className="billing-current-period">
                <span>{t("plansCurrentPeriod")}</span>
                <strong>
                  {currentBillingPeriodLabel}
                </strong>
              </div>
            )}
        </div>

        <div className="billing-period-selector">
          {billingPeriods.map((period) => {
            const active =
              selectedBillingPeriod ===
              period.months;

            const periodLocked =
              Boolean(
                currentPlan &&
                currentPlan.toLowerCase() !== "none" &&
                period.months !== currentBillingPeriod
              );

            return (
              <button
                key={period.months}
                type="button"
                className={[
                  "billing-period-option",
                  active ? "active" : "",
                  periodLocked ? "locked" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                disabled={periodLocked}
                title={
                  periodLocked
                    ? t("plansBillingPeriodLockedTitle")
                    : undefined
                }
                onClick={() => {
                  if (!periodLocked) {
                    setSelectedBillingPeriod(
                      period.months,
                    );
                  }
                }}
              >
                <strong>
                  {t(period.labelKey)}
                </strong>

                {period.badgeKey && (
                  <span>
                    {t(period.badgeKey)}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {currentPlan &&
          currentPlan.toLowerCase() !== "none" && (
            <div className="billing-period-locked-note">
              <span>
                {t("plansCurrentPeriodLockedPrefix")}{" "}
                <strong>
                  {currentBillingPeriodLabel}
                </strong>
                .
              </span>

              <small>
                {t("plansCurrentPeriodLockedHelp")}
              </small>

              {nextBilledAt &&
                daysUntilRenewal !== null && (
                  <small className="billing-period-renewal-info">
                    <strong>
                      {daysUntilRenewal === 0
                        ? t("plansRenewsToday")
                        : daysUntilRenewal === 1
                          ? t(
                              "plansOneDayRemaining",
                            )
                          : t(
                              "plansDaysRemaining",
                              {
                                count:
                                  daysUntilRenewal,
                              },
                            )}
                    </strong>

                    {" · "}

                    {t("plansNextRenewalDate", {
                      date: formatBillingDate(
                        nextBilledAt,
                        billingLocale,
                      ),
                    })}
                  </small>
                )}
            </div>
          )}
      </section>

      <div className="plans-grid">
        {plans.map((plan) => {
          const Icon = plan.icon;

          const isCurrent =
            currentPlan?.toLowerCase() === plan.id;

          const isPending =
            pendingPlan === plan.id;

          const normalizedCurrent =
            (currentPlan || "none").toLowerCase();

          const currentRank =
            planOrder[normalizedCurrent] ?? 0;

          const targetRank =
            planOrder[plan.id] ?? 0;

          const isUpgrade =
            currentRank > 0 &&
            targetRank > currentRank;

          const isImmediateUpgrade =
            isUpgrade;

          const isDowngrade =
            currentRank > 0 &&
            targetRank < currentRank;

          return (
            <article
              key={plan.id}
              className={[
                "plan-card",
                plan.recommended
                  ? "recommended"
                  : "",
                plan.id === selectedPlan
                  ? "selected"
                  : "",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              {plan.recommended && (
                <div className="plan-recommended">{t("plansRecommended")}</div>
              )}

              {isPending && (
                <div className="plan-pending-badge">
                  {t("plansI18nScheduledBadge")}
                </div>
              )}

              <div className="plan-card-icon">
                <Icon size={22} />
              </div>

              <h2>{plan.name}</h2>

              <p className="plan-description">{t(plan.descriptionKey)}</p>

              <div className="plan-price-block">
                <div className="plan-normal-price">
                  <span className="plan-normal-label">
                    {selectedBillingPeriod === 1
                      ? t("plansMonthlyPrice")
                      : t("plansPeriodPrice")}
                  </span>

                  <span className="plan-normal-value">
                    ${
                      plan.prices[
                        selectedBillingPeriod
                      ]
                    }
                    <small>
                      /
                      {t(
                        getPeriodLabelKey(
                          selectedBillingPeriod,
                        ),
                        {
                          count:
                            selectedBillingPeriod,
                        },
                      )}
                    </small>
                  </span>

                  {selectedBillingPeriod > 1 && (
                    <small className="plan-period-equivalent">
                      US$
                      {(
                        plan.prices[
                          selectedBillingPeriod
                        ] /
                        selectedBillingPeriod
                      ).toFixed(2)}
                      {" "}al mes
                    </small>
                  )}

                  {selectedBillingPeriod === 3 && (
                    <span className="plan-period-saving">
                      {t("billingSave5")}
                    </span>
                  )}

                  {selectedBillingPeriod === 6 && (
                    <span className="plan-period-saving">
                      {t("billingSave10")}
                    </span>
                  )}

                  {selectedBillingPeriod === 12 && (
                    <span className="plan-period-saving best">
                      {t("billingSave2Months")}
                    </span>
                  )}
                </div>

                {currentPlan &&
                  !isPending &&
                  currentPlan.toLowerCase() !== "none" &&
                  isImmediateUpgrade && (
                    <div className="plan-upgrade-price">
                      <span className="plan-upgrade-label">
                        {t("plansImmediateUpgrade")}
                      </span>

                      {upgradePreviewStatus[plan.id] ===
                        "loading" && (
                        <>
                          <strong>
                            {t("plansCalculating")}
                          </strong>

                          <small className="plan-upgrade-note">
                            {t("plansCheckingProration")}
                          </small>
                        </>
                      )}

                      {upgradePreviewStatus[plan.id] ===
                        "ready" && (
                        <>
                          <strong>
                            {upgradePrices[plan.id]}
                          </strong>

                          <small className="plan-upgrade-note">
                            {t("plansPayDifferenceToday")}
                          </small>

                          <small className="plan-upgrade-note">
                            {t("plansNextRenewalFullPrice")}
                          </small>
                        </>
                      )}

                      {upgradePreviewStatus[plan.id] ===
                        "error" && (
                        <>
                          <strong className="plan-upgrade-unavailable">
                            {t("plansPriceUnavailable")}
                          </strong>

                          <small className="plan-upgrade-note">
                            {t("plansProrationUnavailable")}
                          </small>
                        </>
                      )}
                    </div>
                  )}
              </div>

              {isDowngrade && (
                <div className="plan-change-rule scheduled">
                  <strong>
                    {t("plansI18nChangeAtRenewal")}
                  </strong>

                  <span>
                    {t("plansI18nDowngradeRenewalHelp")}
                  </span>
                </div>
              )}

              <div className="plan-store-limit">
                <Store size={17} />

                <strong>{plan.stores}</strong>

                <span>
                  {plan.stores === 1 ? t("plansActiveStore") : t("plansActiveStores")}
                </span>
              </div>

              <div className="plan-features">
                {plan.featureKeys.map((feature) => (
                  <div key={t(feature)} className="plan-feature">
                    <Check size={15} />

                    <span>{t(feature)}</span>
                  </div>
                ))}
              </div>

              <button
                type="button"
                className={isCurrent ? "plan-button current" : "plan-button"}
                disabled={
                  isCurrent ||
                  loadingPlan ||
                  checkoutPlan !== null
                }
                onClick={() => handleChoosePlan(plan.id)}
              >
                {loadingPlan
                  ? t("commonLoading")
                  : isCurrent
                    ? t("plansCurrentPlan")
                    : checkoutPlan === plan.id
                      ? (
                          currentPlan &&
                          currentPlan.toLowerCase() !== "none"
                            ? t("plansCalculating")
                            : t("plansOpeningPayment")
                        )
                      : isPending
                        ? t("plansScheduledChange")
                        : (
                            currentPlan &&
                            planOrder[currentPlan.toLowerCase()] >
                              planOrder[plan.id]
                              ? t("plansDowngrade")
                              : currentPlan &&
                                  currentPlan.toLowerCase() !== "none"
                                ? t("plansUpgrade")
                                : t("plansChoosePlan")
                          )}
              </button>
            </article>
          );
        })}
      </div>

      <AiUsagePackagesSection
        paddle={paddle}
        enabled={Boolean(
          currentPlan && currentPlan.toLowerCase() !== "none"
        )}
      />

      <section className="auto-renew-plan-section">
        <div className="auto-renew-plan-copy">
          <span className="eyebrow">
            {t("plansRenewalEyebrow")}
          </span>

          <h2>
            {t("plansAutoRenewTitle")}
          </h2>

          <p>
            {t("plansAutoRenewHelp")}
          </p>
        </div>

        <div className="auto-renew-plan-control">
          <div>
            <strong>
              {autoRenewEnabled
                ? t("plansAutoRenewEnabled")
                : t("plansAutoRenewDisabled")}
            </strong>

            <span>
              {autoRenewEnabled
                ? t("plansAutoRenewEnabledHelp")
                : t("plansAutoRenewDisabledHelp")}
            </span>
          </div>

          <button
            type="button"
            className={
              autoRenewEnabled
                ? "auto-renew-switch active"
                : "auto-renew-switch"
            }
            role="switch"
            aria-checked={autoRenewEnabled}
            disabled={autoRenewSaving}
            onClick={handleToggleAutoRenew}
          >
            <span />
          </button>
        </div>
      </section>


      {upgradePreview && upgradePlan && (
        <div className="billing-upgrade-backdrop">
          <div className="billing-upgrade-modal">
            <div className="billing-upgrade-header">
              <div>
                <span className="billing-upgrade-eyebrow">
                  {t("plansUpgrade")}
                </span>

                <h2>
                  {t("plansConfirmUpgrade")}
                </h2>
              </div>

              <button
                type="button"
                className="billing-upgrade-close"
                disabled={upgradeSubmitting}
                onClick={() => {
                  setUpgradePreview(null);
                  setUpgradePlan(null);
                }}
              >
                ×
              </button>
            </div>

            <div className="billing-upgrade-plan-change">
              <div>
                <span>{t("plansCurrentPlanLabel")}</span>
                <strong>
                  {
                    plans.find(
                      (item) =>
                        item.id ===
                        upgradePreview.current_plan,
                    )?.name ||
                    upgradePreview.current_plan
                  }
                </strong>
              </div>

              <div className="billing-upgrade-arrow">
                →
              </div>

              <div>
                <span>{t("plansNewPlanLabel")}</span>
                <strong>
                  {
                    plans.find(
                      (item) =>
                        item.id ===
                        upgradePreview.target_plan,
                    )?.name ||
                    upgradePreview.target_plan
                  }
                </strong>
              </div>
            </div>

            <div className="billing-upgrade-total">
              <span>
                {t("plansPayToday")}
              </span>

              <strong>
                {moneyFromMinorUnits(
                  upgradePreview.amount_due,
                  upgradePreview.currency_code ||
                    upgradePreview.update_summary
                      ?.result
                      ?.currency_code ||
                    "USD",
                )}
              </strong>

              <small>
                {t("plansProrationExplanation")}
              </small>

              <small>
                {t("plansNextRenewalFullPrice")}
              </small>
            </div>

            <div className="billing-upgrade-breakdown">
              <div>
                <span>
                  {t("plansNewPlanProratedCharge")}
                </span>

                <strong>
                  {moneyFromMinorUnits(
                    upgradePreview.update_summary
                      ?.charge?.amount,
                    upgradePreview.update_summary
                      ?.charge?.currency_code ||
                      "USD",
                  )}
                </strong>
              </div>

              <div>
                <span>
                  {t("plansCurrentPlanCredit")}
                </span>

                <strong>
                  {moneyFromMinorUnits(
                    upgradePreview.update_summary
                      ?.credit?.amount,
                    upgradePreview.update_summary
                      ?.credit?.currency_code ||
                      "USD",
                  )}
                </strong>
              </div>

              <div>
                <span>
                  {t("plansNextRenewal")}
                </span>

                <strong>
                  {formatBillingDate(
                    upgradePreview.next_billed_at,
                    billingLocale,
                  )}
                </strong>
              </div>

              <div>
                <span>
                  {t("plansNextMonthlyPrice")}
                </span>

                <strong>
                  {
                    moneyFromMinorUnits(
                      String(
                        (
                          plans.find(
                            (item) =>
                              item.id ===
                              upgradePlan,
                          )?.prices[
                              currentBillingPeriod
                            ] || 0
                        ) * 100,
                      ),
                      "USD",
                    )
                  }
                </strong>
              </div>
            </div>

            <div className="billing-upgrade-actions">
              <button
                type="button"
                className="billing-upgrade-cancel"
                disabled={upgradeSubmitting}
                onClick={() => {
                  setUpgradePreview(null);
                  setUpgradePlan(null);
                }}
              >
                {t("commonCancel")}
              </button>

              <button
                type="button"
                className="billing-upgrade-confirm"
                disabled={upgradeSubmitting}
                onClick={
                  handleConfirmUpgrade
                }
              >
                {upgradeSubmitting
                  ? t("plansProcessing")
                  : t("plansConfirmUpgrade")}
              </button>
            </div>
          </div>
        </div>
      )}

      {downgradePreview && downgradePlan && (
        <div className="billing-upgrade-overlay">
          <div className="billing-upgrade-modal">
            <div className="billing-upgrade-header">
              <div>
                <span className="billing-upgrade-kicker">
                  {t("plansPlanChange")}
                </span>

                <h2>
                  {t("plansScheduleChangeTitle")}
                </h2>
              </div>

              <button
                type="button"
                className="billing-upgrade-close"
                onClick={() => {
                  if (!downgradeSubmitting) {
                    setDowngradePreview(null);
                    setDowngradePlan(null);
                  }
                }}
              >
                ×
              </button>
            </div>

            <div className="billing-upgrade-summary">
              <div className="billing-upgrade-row">
                <span>{t("plansCurrentPlanLabel")}</span>
                <strong>
                  {plans.find(
                    (plan) =>
                      plan.id ===
                      downgradePreview.current_plan,
                  )?.name ||
                    downgradePreview.current_plan}
                  {" · "}
                  {getBillingPeriodLabel(
                    downgradePreview
                      .current_billing_period_months,
                  )}
                </strong>
              </div>

              <div className="billing-upgrade-row">
                <span>{t("plansNewPlanLabel")}</span>
                <strong>
                  {plans.find(
                    (plan) =>
                      plan.id ===
                      downgradePreview.target_plan,
                  )?.name ||
                    downgradePreview.target_plan}
                  {" · "}
                  {getBillingPeriodLabel(
                    downgradePreview
                      .target_billing_period_months,
                  )}
                </strong>
              </div>

              <div className="billing-upgrade-row">
                <span>{t("plansAdditionalChargeToday")}</span>
                <strong>US$0.00</strong>
              </div>

              <div className="billing-upgrade-row">
                <span>{t("plansChangeDate")}</span>
                <strong>
                  {formatBillingDate(
                    downgradePreview.effective_at,
                    billingLocale,
                  )}
                </strong>
              </div>
            </div>

            {downgradePreview.requires_store_selection && (
              <div className="downgrade-store-selector">
                <div className="downgrade-store-selector-header">
                  <strong>
                    {t("plansSelectActiveStores")}
                  </strong>

                  <span>
                    {t(
                      "plansSelectUpToStores",
                      {
                        count:
                          downgradePreview.target_store_limit,
                        stores:
                          downgradePreview.target_store_limit === 1
                            ? t("storeSingular")
                            : t("storePlural"),
                      },
                    )}
                  </span>
                </div>

                <div className="downgrade-store-list">
                  {downgradePreview.available_stores.map(
                    (store) => {
                      const selected =
                        downgradeStoreIds.includes(
                          store.id,
                        );

                      return (
                        <button
                          key={store.id}
                          type="button"
                          className={
                            selected
                              ? "downgrade-store-option selected"
                              : "downgrade-store-option"
                          }
                          onClick={() => {
                            setDowngradeStoreIds(
                              (current) => {
                                if (
                                  current.includes(
                                    store.id,
                                  )
                                ) {
                                  return current.filter(
                                    (id) =>
                                      id !== store.id,
                                  );
                                }

                                if (
                                  current.length >=
                                  downgradePreview.target_store_limit
                                ) {
                                  return [
                                    ...current.slice(
                                      1,
                                    ),
                                    store.id,
                                  ];
                                }

                                return [
                                  ...current,
                                  store.id,
                                ];
                              },
                            );
                          }}
                        >
                          <span className="downgrade-store-radio">
                            {selected ? "✓" : ""}
                          </span>

                          <span className="downgrade-store-info">
                            <strong>
                              {store.name}
                            </strong>

                            <small>
                              {store.active
                                ? store.active_since
                                  ? t(
                                      "plansStoreActiveSince",
                                      {
                                        date:
                                          formatBillingDate(
                                            store.active_since,
                                            billingLocale,
                                          ),
                                      },
                                    )
                                  : t("storeActive")
                                : t("storeSuspended")}
                            </small>
                          </span>
                        </button>
                      );
                    },
                  )}
                </div>

                <p className="downgrade-store-fallback">
                  {t("plansDowngradeStoreSelectionHelp")}
                </p>
              </div>
            )}

            <div className="billing-downgrade-note">
              <strong>
                {t("plansKeepCurrentUntilRenewal")}
              </strong>

              <span>
                {t("plansNewStoreLimitHelp")}
              </span>

              <span>
                {t("plansNoStoresSuspendedToday")}
              </span>

              <span>
                {t("plansSuspendedStoresRenewalHelp")}
              </span>
            </div>

            <div className="billing-upgrade-actions">
              <button
                type="button"
                className="billing-upgrade-secondary"
                disabled={downgradeSubmitting}
                onClick={() => {
                  setDowngradePreview(null);
                  setDowngradePlan(null);
                }}
              >
                {t("plansI18nCancel")}
              </button>

              <button
                type="button"
                className="billing-upgrade-primary"
                disabled={downgradeSubmitting}
                onClick={handleConfirmDowngrade}
              >
                {downgradeSubmitting
                  ? t("plansScheduling")
                  : t("plansScheduleForRenewal")}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

