import {
  AlertTriangle,
  ArrowRight,
  CircleCheck,
  Lightbulb,
  ShieldAlert,
  Sparkles,
} from "lucide-react";

import type {
  DropshippingDecisionInsightsResponse,
  DropshippingInsight,
} from "../services/analytics";
import {
  getDecisionInsightPresentation,
  getDecisionInsightSectionCopy,
  normalizeDecisionInsightLocale,
  selectedProductIdFromInsight,
  type DecisionEvidenceItem,
  type DecisionInsightPresentation,
} from "../utils/dropshippingDecisionInsights";
import "../dropshipping-decision-insights.css";

interface Props {
  data: DropshippingDecisionInsightsResponse | null;
  unavailable: boolean;
  language: string;
  currency: string;
  onSelectProduct: (productId: number) => void;
}

function safePresentation(
  insight: DropshippingInsight,
  language: string,
): DecisionInsightPresentation | null {
  try {
    return getDecisionInsightPresentation(insight, language);
  } catch {
    return null;
  }
}

function formatEvidence(
  item: DecisionEvidenceItem,
  language: string,
  currency: string,
): string {
  if (item.value === null || item.value === undefined) return "—";
  const locale = normalizeDecisionInsightLocale(language);
  const intlLocale = locale === "es" ? "es-CO" : locale;

  if (item.format === "currency" && typeof item.value === "number") {
    try {
      return new Intl.NumberFormat(intlLocale, {
        style: "currency",
        currency,
        maximumFractionDigits: 0,
      }).format(item.value);
    } catch {
      return `${item.value} ${currency}`;
    }
  }

  if (item.format === "percent") return `${item.value}%`;
  if (item.format === "days") {
    const unit = locale === "en" ? "days" : locale === "pt-BR" ? "dias" : "días";
    return `${item.value} ${unit}`;
  }
  if (typeof item.value === "number") {
    return new Intl.NumberFormat(intlLocale, { maximumFractionDigits: 1 }).format(item.value);
  }
  return String(item.value);
}

function SeverityIcon({ severity }: { severity: DropshippingInsight["severity"] }) {
  if (severity === "critical") return <ShieldAlert size={17} />;
  if (severity === "warning") return <AlertTriangle size={17} />;
  if (severity === "opportunity") return <Lightbulb size={17} />;
  return <CircleCheck size={17} />;
}

export default function DropshippingDecisionInsights({
  data,
  unavailable,
  language,
  currency,
  onSelectProduct,
}: Props) {
  const copy = getDecisionInsightSectionCopy(language);

  if (unavailable) {
    return (
      <section className="decision-insights-shell is-unavailable">
        <div className="decision-insights-heading">
          <div>
            <span>{copy.kicker}</span>
            <h3><Sparkles size={19} /> {copy.title}</h3>
          </div>
        </div>
        <div className="decision-insights-empty">
          <AlertTriangle size={19} />
          <span>{copy.unavailable}</span>
        </div>
      </section>
    );
  }

  if (!data) return null;

  const cards = data.insights
    .map((insight) => ({
      insight,
      presentation: safePresentation(insight, language),
    }))
    .filter(
      (item): item is {
        insight: DropshippingInsight;
        presentation: DecisionInsightPresentation;
      } => item.presentation !== null,
    );

  return (
    <section className="decision-insights-shell">
      <div className="decision-insights-heading">
        <div>
          <span>{copy.kicker}</span>
          <h3><Sparkles size={19} /> {copy.title}</h3>
          <p>{copy.subtitle}</p>
        </div>
        <div className="decision-insights-summary" aria-label={copy.title}>
          {data.summary.critical > 0 && <span className="is-critical">{data.summary.critical}</span>}
          {data.summary.warning > 0 && <span className="is-warning">{data.summary.warning}</span>}
          {data.summary.opportunity > 0 && <span className="is-opportunity">{data.summary.opportunity}</span>}
          {data.summary.positive > 0 && <span className="is-positive">{data.summary.positive}</span>}
        </div>
      </div>

      {cards.length === 0 ? (
        <div className="decision-insights-empty">
          <CircleCheck size={19} />
          <span>{copy.empty}</span>
        </div>
      ) : (
        <div className="decision-insights-grid">
          {cards.map(({ insight, presentation }) => {
            const productId = selectedProductIdFromInsight(insight);
            return (
              <article
                key={insight.id}
                className={`decision-insight-card is-${insight.severity}`}
              >
                <div className="decision-insight-card-top">
                  <span className="decision-insight-severity">
                    <SeverityIcon severity={insight.severity} />
                    {presentation.severityLabel}
                  </span>
                  {insight.product_title && (
                    <span className="decision-insight-product">{insight.product_title}</span>
                  )}
                </div>

                <h4>{presentation.title}</h4>
                <p>{presentation.reason}</p>

                {presentation.evidence.length > 0 && (
                  <div className="decision-insight-evidence">
                    {presentation.evidence.map((item) => (
                      <div key={item.key}>
                        <span>{item.label}</span>
                        <strong>{formatEvidence(item, language, currency)}</strong>
                      </div>
                    ))}
                  </div>
                )}

                <div className="decision-insight-action">
                  <span>{copy.recommendedAction}</span>
                  <strong>{presentation.action}</strong>
                </div>

                {productId !== null && (
                  <button
                    type="button"
                    className="decision-insight-product-link"
                    onClick={() => onSelectProduct(productId)}
                  >
                    {copy.viewProduct}
                    <ArrowRight size={14} />
                  </button>
                )}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
