import type {
  DropshippingUnitEconomicsResponse,
  UnitEconomicsSource,
  UnitEconomicsStatus,
} from "../services/analytics";


type LocaleKey = "es" | "en" | "pt-BR";


function normalizeLocale(language: string): LocaleKey {
  if (language.toLowerCase().startsWith("pt")) return "pt-BR";
  if (language.toLowerCase().startsWith("en")) return "en";
  return "es";
}


const SOURCE_COPY: Record<LocaleKey, Record<UnitEconomicsSource, string>> = {
  es: {
    actual: "Real",
    estimated: "Estimado",
    missing: "Ausente",
    not_applicable: "No aplica",
  },
  en: {
    actual: "Actual",
    estimated: "Estimated",
    missing: "Missing",
    not_applicable: "Not applicable",
  },
  "pt-BR": {
    actual: "Real",
    estimated: "Estimado",
    missing: "Ausente",
    not_applicable: "Não se aplica",
  },
};


const REASON_COPY: Record<LocaleKey, Record<string, string>> = {
  es: {
    cogs_incomplete: "Faltan costos de producto en algunos ítems entregados.",
    shipping_estimate_missing: "Configura el costo estimado de envío de salida.",
    payment_fee_rule_missing: "Falta una regla de comisión para uno o más métodos de pago.",
    cod_fee_rule_missing: "Falta la comisión contraentrega para uno o más métodos configurados como COD.",
    return_cost_missing: "Configura el costo estimado de logística de devolución.",
    meta_not_connected: "Conecta Meta Ads para incluir el gasto publicitario real.",
    bounded_date_range_required: "Selecciona un rango de fechas completo para consultar Meta Ads.",
    currency_unknown: "Meta Ads no reportó una moneda utilizable para la cuenta conectada.",
    currency_mismatch: "La moneda de Meta Ads no coincide con la moneda de la tienda.",
    provider_error: "Meta Ads no pudo devolver el gasto publicitario en este momento.",
    credentials_unavailable: "La conexión de Meta Ads necesita reconectarse.",
  },
  en: {
    cogs_incomplete: "Product cost is missing for some delivered items.",
    shipping_estimate_missing: "Configure an estimated outbound shipping cost.",
    payment_fee_rule_missing: "A payment-fee rule is missing for one or more payment methods.",
    cod_fee_rule_missing: "A COD fee is missing for one or more methods configured as cash on delivery.",
    return_cost_missing: "Configure an estimated return-logistics cost.",
    meta_not_connected: "Connect Meta Ads to include actual advertising spend.",
    bounded_date_range_required: "Select a complete date range to query Meta Ads.",
    currency_unknown: "Meta Ads did not report a usable currency for the connected account.",
    currency_mismatch: "The Meta Ads currency does not match the store currency.",
    provider_error: "Meta Ads could not return advertising spend right now.",
    credentials_unavailable: "The Meta Ads connection needs to be reconnected.",
  },
  "pt-BR": {
    cogs_incomplete: "Falta custo de produto em alguns itens entregues.",
    shipping_estimate_missing: "Configure um custo estimado de frete de saída.",
    payment_fee_rule_missing: "Falta uma regra de taxa para um ou mais métodos de pagamento.",
    cod_fee_rule_missing: "Falta a taxa COD para um ou mais métodos configurados como pagamento na entrega.",
    return_cost_missing: "Configure um custo estimado de logística de devolução.",
    meta_not_connected: "Conecte o Meta Ads para incluir o gasto publicitário real.",
    bounded_date_range_required: "Selecione um intervalo de datas completo para consultar o Meta Ads.",
    currency_unknown: "O Meta Ads não informou uma moeda utilizável para a conta conectada.",
    currency_mismatch: "A moeda do Meta Ads não coincide com a moeda da loja.",
    provider_error: "O Meta Ads não conseguiu retornar o gasto publicitário agora.",
    credentials_unavailable: "A conexão do Meta Ads precisa ser reconectada.",
  },
};


const FALLBACK_REASON: Record<LocaleKey, string> = {
  es: "Falta información para completar este costo.",
  en: "More information is required to complete this cost.",
  "pt-BR": "Faltam informações para completar este custo.",
};


const META_INTEGRATION_ACTION_REASONS = new Set([
  "meta_not_connected",
  "currency_unknown",
  "currency_mismatch",
  "provider_error",
  "credentials_unavailable",
]);


const CONFIGURABLE_COST_REASONS = new Set([
  "shipping_estimate_missing",
  "payment_fee_rule_missing",
  "cod_fee_rule_missing",
  "return_cost_missing",
]);


export function unitEconomicsSourceLabel(
  source: UnitEconomicsSource,
  language: string,
): string {
  return SOURCE_COPY[normalizeLocale(language)][source];
}


export function unitEconomicsReasonCopy(
  reason: string | null,
  language: string,
): string {
  const locale = normalizeLocale(language);
  if (!reason) return FALLBACK_REASON[locale];
  return REASON_COPY[locale][reason] || FALLBACK_REASON[locale];
}


type ContributionPresentationInput = {
  data_quality: Pick<DropshippingUnitEconomicsResponse["data_quality"], "status">;
  contribution_profit: number | null;
  contribution_margin: number | null;
  known_cost_subtotal: number;
};


export function getUnitEconomicsContributionValues(
  data: ContributionPresentationInput,
): { profit: number | null; margin: number | null; complete: boolean } {
  const complete = data.data_quality.status === "complete";
  return {
    profit: complete ? data.contribution_profit : null,
    margin: complete ? data.contribution_margin : null,
    complete,
  };
}


type GrossProfitPresentationInput = {
  gross_profit: number;
  components: {
    cogs: {
      status: UnitEconomicsStatus;
    };
  };
};


export function getUnitEconomicsGrossProfitValue(
  data: GrossProfitPresentationInput,
): number | null {
  return data.components.cogs.status === "missing" ? null : data.gross_profit;
}


export function isMetaIntegrationActionReason(reason: string | null): boolean {
  return META_INTEGRATION_ACTION_REASONS.has(reason || "");
}


export function isConfigurableUnitEconomicsReason(reason: string | null): boolean {
  return CONFIGURABLE_COST_REASONS.has(reason || "");
}
