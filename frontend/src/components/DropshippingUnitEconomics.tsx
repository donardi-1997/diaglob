import { AlertTriangle, CheckCircle2, ExternalLink, WalletCards } from "lucide-react";

import type {
  DropshippingUnitEconomicsResponse,
  UnitEconomicsCostComponent,
} from "../services/analytics";
import {
  getUnitEconomicsContributionValues,
  getUnitEconomicsGrossProfitValue,
  isConfigurableUnitEconomicsReason,
  isMetaIntegrationActionReason,
  unitEconomicsReasonCopy,
  unitEconomicsSourceLabel,
} from "../utils/unitEconomics";
import "../unit-economics-analytics.css";


interface Props {
  data: DropshippingUnitEconomicsResponse | null;
  unavailable: boolean;
  language: string;
  currency: string;
  onConfigureCosts?: () => void;
  onOpenIntegrations?: () => void;
}


type LocaleKey = "es" | "en" | "pt-BR";


const COPY: Record<LocaleKey, {
  eyebrow: string;
  title: string;
  body: string;
  contributionProfit: string;
  contributionMargin: string;
  recognizedRevenue: string;
  grossProfit: string;
  knownCosts: string;
  knownCostsHelp: string;
  complete: string;
  incomplete: string;
  incompleteBody: string;
  unavailable: string;
  configureCosts: string;
  openIntegrations: string;
  components: Record<string, string>;
}> = {
  es: {
    eyebrow: "UNIT ECONOMICS V2.2",
    title: "Margen de contribución",
    body: "Ingresos entregados menos producto, logística, pagos, contraentrega, devoluciones y publicidad disponible.",
    contributionProfit: "Utilidad de contribución",
    contributionMargin: "Margen de contribución",
    recognizedRevenue: "Ingresos reconocidos",
    grossProfit: "Utilidad bruta",
    knownCosts: "Costos conocidos",
    knownCostsHelp: "Subtotal informativo; no es utilidad cuando faltan costos.",
    complete: "Completo",
    incomplete: "Incompleto",
    incompleteBody: "No mostramos una utilidad parcial como si fuera final. Completa los costos marcados como ausentes.",
    unavailable: "Unit Economics no está disponible temporalmente. El resto de Analytics sigue activo.",
    configureCosts: "Configurar costos",
    openIntegrations: "Abrir Integraciones",
    components: {
      cogs: "Costo de producto (COGS)",
      outbound_shipping: "Envío de salida",
      payment_fees: "Comisiones de pago",
      cod_fees: "Comisiones contraentrega",
      reverse_logistics: "Logística de devolución",
      ad_spend: "Meta Ads",
    },
  },
  en: {
    eyebrow: "UNIT ECONOMICS V2.2",
    title: "Contribution margin",
    body: "Delivered revenue minus product, logistics, payments, COD, returns and available advertising costs.",
    contributionProfit: "Contribution profit",
    contributionMargin: "Contribution margin",
    recognizedRevenue: "Recognized revenue",
    grossProfit: "Gross profit",
    knownCosts: "Known costs",
    knownCostsHelp: "Informational subtotal; it is not profit when costs are missing.",
    complete: "Complete",
    incomplete: "Incomplete",
    incompleteBody: "We do not present partial profit as final. Complete the costs marked as missing.",
    unavailable: "Unit Economics is temporarily unavailable. The rest of Analytics remains active.",
    configureCosts: "Configure costs",
    openIntegrations: "Open Integrations",
    components: {
      cogs: "Product cost (COGS)",
      outbound_shipping: "Outbound shipping",
      payment_fees: "Payment fees",
      cod_fees: "Cash-on-delivery fees",
      reverse_logistics: "Return logistics",
      ad_spend: "Meta Ads",
    },
  },
  "pt-BR": {
    eyebrow: "UNIT ECONOMICS V2.2",
    title: "Margem de contribuição",
    body: "Receita entregue menos produto, logística, pagamentos, COD, devoluções e publicidade disponível.",
    contributionProfit: "Lucro de contribuição",
    contributionMargin: "Margem de contribuição",
    recognizedRevenue: "Receita reconhecida",
    grossProfit: "Lucro bruto",
    knownCosts: "Custos conhecidos",
    knownCostsHelp: "Subtotal informativo; não é lucro quando faltam custos.",
    complete: "Completo",
    incomplete: "Incompleto",
    incompleteBody: "Não mostramos lucro parcial como se fosse final. Complete os custos marcados como ausentes.",
    unavailable: "Unit Economics está temporariamente indisponível. O restante do Analytics continua ativo.",
    configureCosts: "Configurar custos",
    openIntegrations: "Abrir Integrações",
    components: {
      cogs: "Custo do produto (COGS)",
      outbound_shipping: "Frete de saída",
      payment_fees: "Taxas de pagamento",
      cod_fees: "Taxas de pagamento na entrega",
      reverse_logistics: "Logística de devolução",
      ad_spend: "Meta Ads",
    },
  },
};


function normalizeLocale(language: string): LocaleKey {
  if (language.toLowerCase().startsWith("pt")) return "pt-BR";
  if (language.toLowerCase().startsWith("en")) return "en";
  return "es";
}


function componentRows(data: DropshippingUnitEconomicsResponse) {
  return Object.entries(data.components) as [string, UnitEconomicsCostComponent][];
}


export default function DropshippingUnitEconomics({
  data,
  unavailable,
  language,
  currency,
  onConfigureCosts,
  onOpenIntegrations,
}: Props) {
  const locale = normalizeLocale(language);
  const copy = COPY[locale];

  const formatCurrency = (value: number | null) => {
    if (value === null || value === undefined) return "—";
    try {
      return new Intl.NumberFormat(locale === "pt-BR" ? "pt-BR" : locale === "en" ? "en-US" : "es-CO", {
        style: "currency",
        currency,
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
      }).format(value);
    } catch {
      return `${value} ${currency}`;
    }
  };

  if (unavailable) {
    return (
      <section className="unit-economics-analytics">
        <div className="unit-economics-analytics-empty">
          <AlertTriangle size={17} />
          <span>{copy.unavailable}</span>
        </div>
      </section>
    );
  }

  if (!data) return null;

  const contribution = getUnitEconomicsContributionValues(data);
  const grossProfit = getUnitEconomicsGrossProfitValue(data);
  const missingReasons = Object.values(data.data_quality.missing_reasons).filter(
    (reason): reason is string => Boolean(reason),
  );
  const hasMetaMissing = missingReasons.some(isMetaIntegrationActionReason);
  const hasConfigurableMissing = missingReasons.some(isConfigurableUnitEconomicsReason);

  return (
    <section className="unit-economics-analytics">
      <div className="unit-economics-analytics-header">
        <div>
          <span className="unit-economics-analytics-kicker">{copy.eyebrow}</span>
          <h3><WalletCards size={18} /> {copy.title}</h3>
          <p>{copy.body}</p>
        </div>
        <span className={`unit-economics-quality ${contribution.complete ? "is-complete" : "is-incomplete"}`}>
          {contribution.complete ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}
          {contribution.complete ? copy.complete : copy.incomplete}
        </span>
      </div>

      <div className="unit-economics-summary">
        <div>
          <span>{copy.contributionProfit}</span>
          <strong>{contribution.complete ? formatCurrency(contribution.profit) : "—"}</strong>
        </div>
        <div>
          <span>{copy.contributionMargin}</span>
          <strong>{contribution.complete && contribution.margin !== null ? `${contribution.margin.toFixed(1)}%` : "—"}</strong>
        </div>
        <div>
          <span>{copy.recognizedRevenue}</span>
          <strong>{formatCurrency(data.recognized_revenue)}</strong>
        </div>
        <div>
          <span>{copy.grossProfit}</span>
          <strong>{formatCurrency(grossProfit)}</strong>
        </div>
        <div className="is-known-costs">
          <span>{copy.knownCosts}</span>
          <strong>{formatCurrency(data.known_cost_subtotal)}</strong>
          {!contribution.complete && <small>{copy.knownCostsHelp}</small>}
        </div>
      </div>

      {!contribution.complete && (
        <div className="unit-economics-incomplete">
          <AlertTriangle size={16} />
          <span>{copy.incompleteBody}</span>
        </div>
      )}

      <div className="unit-economics-components">
        {componentRows(data).map(([name, component]) => (
          <div className={`unit-economics-component is-${component.source}`} key={name}>
            <div className="unit-economics-component-top">
              <span>{copy.components[name] || name}</span>
              <span className="unit-economics-source">
                {unitEconomicsSourceLabel(component.source, locale)}
              </span>
            </div>
            <strong>{component.amount === null ? "—" : formatCurrency(component.amount)}</strong>
            {component.status === "missing" && (
              <small>{unitEconomicsReasonCopy(component.reason, locale)}</small>
            )}
          </div>
        ))}
      </div>

      {(hasConfigurableMissing || hasMetaMissing) && (
        <div className="unit-economics-actions">
          {hasConfigurableMissing && onConfigureCosts && (
            <button type="button" onClick={onConfigureCosts}>
              {copy.configureCosts}
              <ExternalLink size={13} />
            </button>
          )}
          {hasMetaMissing && onOpenIntegrations && (
            <button type="button" onClick={onOpenIntegrations}>
              {copy.openIntegrations}
              <ExternalLink size={13} />
            </button>
          )}
        </div>
      )}
    </section>
  );
}
