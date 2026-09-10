import { useCallback, useEffect, useState } from "react";
import type { Paddle } from "@paddle/paddle-js";
import { BrainCircuit, RefreshCw, Sparkles, Zap } from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  createAiUsagePackageCheckout,
  getAiUsagePackages,
  type AiUsagePackage,
  type AiUsageSummary,
} from "../services/billing";

import "./AiUsagePackagesSection.css";


interface AiUsagePackagesSectionProps {
  paddle?: Paddle;
  enabled: boolean;
}


function formatNumber(value: number | null | undefined) {
  return new Intl.NumberFormat().format(Number(value || 0));
}


export default function AiUsagePackagesSection({
  paddle,
  enabled,
}: AiUsagePackagesSectionProps) {
  const { t } = useTranslation();
  const [packages, setPackages] = useState<AiUsagePackage[]>([]);
  const [usage, setUsage] = useState<AiUsageSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [buying, setBuying] = useState<string | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!enabled) {
      setPackages([]);
      setUsage(null);
      return;
    }

    try {
      setLoading(true);
      setError("");
      const data = await getAiUsagePackages();
      setPackages(data.packages);
      setUsage(data.usage);
    } catch (requestError) {
      console.error("Unable to load AI usage packages", requestError);
      setError(t("aiPackagesLoadError"));
    } finally {
      setLoading(false);
    }
  }, [enabled, t]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }

    const refreshOnFocus = () => {
      void load();
    };

    window.addEventListener("focus", refreshOnFocus);
    return () => window.removeEventListener("focus", refreshOnFocus);
  }, [enabled, load]);

  async function handlePurchase(packageKey: string) {
    if (!paddle || buying) {
      if (!paddle) {
        setError(t("plansPaddleNotReady"));
      }
      return;
    }

    try {
      setBuying(packageKey);
      setError("");
      const checkout = await createAiUsagePackageCheckout(packageKey);
      paddle.Checkout.open({ transactionId: checkout.transaction_id });
    } catch (requestError: any) {
      const detail = requestError?.response?.data?.detail;
      if (typeof detail === "string") {
        setError(detail);
      } else if (typeof detail?.message === "string") {
        setError(detail.message);
      } else {
        setError(t("aiPackagesCheckoutError"));
      }
    } finally {
      setBuying(null);
    }
  }

  if (!enabled) {
    return null;
  }

  const included = usage?.included_ai_responses || 0;
  const used = usage?.used_ai_responses || 0;
  const includedUsed = Math.min(used, included);
  const progress = included > 0
    ? Math.min((includedUsed / included) * 100, 100)
    : 0;

  return (
    <section className="ai-packages-section">
      <div className="ai-packages-heading">
        <div>
          <span className="eyebrow">{t("aiPackagesEyebrow")}</span>
          <h2>{t("aiPackagesTitle")}</h2>
          <p>{t("aiPackagesSubtitle")}</p>
        </div>

        <button
          type="button"
          className="ai-packages-refresh"
          disabled={loading}
          onClick={() => void load()}
          aria-label={t("aiPackagesRefresh")}
        >
          <RefreshCw size={16} className={loading ? "spinning" : ""} />
          <span>{t("aiPackagesRefresh")}</span>
        </button>
      </div>

      {usage && (
        <div className="ai-usage-overview">
          <div className="ai-usage-main">
            <div className="ai-usage-icon">
              <BrainCircuit size={22} />
            </div>
            <div className="ai-usage-copy">
              <span>{t("aiPackagesThisMonth")}</span>
              <strong>
                {formatNumber(includedUsed)} / {formatNumber(included)}
              </strong>
              <div className="ai-usage-progress" aria-hidden="true">
                <span style={{ width: `${progress}%` }} />
              </div>
            </div>
          </div>

          <div className="ai-usage-extra-balance">
            <Sparkles size={18} />
            <div>
              <span>{t("aiPackagesExtraBalance")}</span>
              <strong>
                {formatNumber(usage.extra_ai_responses_remaining)}
              </strong>
            </div>
          </div>

          <div className="ai-usage-total-balance">
            <Zap size={18} />
            <div>
              <span>{t("aiPackagesAvailableNow")}</span>
              <strong>
                {formatNumber(usage.remaining_ai_responses)}
              </strong>
            </div>
          </div>
        </div>
      )}

      {error && <div className="ai-packages-error">{error}</div>}

      <div className="ai-packages-grid">
        {packages.map((item, index) => (
          <article
            key={item.key}
            className={index === 1 ? "ai-package-card featured" : "ai-package-card"}
          >
            {index === 1 && (
              <span className="ai-package-badge">{t("aiPackagesPopular")}</span>
            )}

            <div className="ai-package-card-top">
              <div className="ai-package-spark">
                <Sparkles size={18} />
              </div>
              <span>{t("aiPackagesOneTime")}</span>
            </div>

            <strong className="ai-package-responses">
              +{formatNumber(item.responses)}
            </strong>
            <span className="ai-package-unit">{t("aiPackagesResponses")}</span>

            <div className="ai-package-price">
              <strong>US${Number(item.price_usd).toFixed(2)}</strong>
              <span>{t("aiPackagesNoExpiration")}</span>
            </div>

            <button
              type="button"
              disabled={!item.configured || !paddle || buying !== null}
              onClick={() => void handlePurchase(item.key)}
            >
              {buying === item.key
                ? t("plansOpeningPayment")
                : item.configured
                  ? t("aiPackagesBuy")
                  : t("aiPackagesUnavailable")}
            </button>
          </article>
        ))}
      </div>

      <p className="ai-packages-footnote">
        {t("aiPackagesFootnote")}
      </p>
    </section>
  );
}
