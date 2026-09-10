import type {
  CommercialClassification,
  CustomerValueTier,
} from "../services/customerClassifications";

export type ClassificationLocale = "es" | "en" | "pt-BR";

export const CLASSIFICATION_KEYS: CommercialClassification[] = [
  "champion",
  "loyal",
  "repeat_customer",
  "high_value",
  "recent_buyer",
  "value_at_risk",
  "dormant",
  "prospect",
  "lead",
];

export const VALUE_TIER_KEYS: CustomerValueTier[] = [
  "high",
  "medium",
  "low",
  "none",
];

const CLASSIFICATION_LABELS: Record<
  ClassificationLocale,
  Record<CommercialClassification, string>
> = {
  es: {
    champion: "Champion",
    loyal: "Leal",
    repeat_customer: "Recurrente",
    high_value: "Alto valor",
    recent_buyer: "Comprador reciente",
    value_at_risk: "Valor en riesgo",
    dormant: "Dormido",
    prospect: "Prospecto",
    lead: "Lead",
  },
  en: {
    champion: "Champion",
    loyal: "Loyal",
    repeat_customer: "Repeat customer",
    high_value: "High value",
    recent_buyer: "Recent buyer",
    value_at_risk: "Value at risk",
    dormant: "Dormant",
    prospect: "Prospect",
    lead: "Lead",
  },
  "pt-BR": {
    champion: "Champion",
    loyal: "Leal",
    repeat_customer: "Recorrente",
    high_value: "Alto valor",
    recent_buyer: "Comprador recente",
    value_at_risk: "Valor em risco",
    dormant: "Inativo",
    prospect: "Prospect",
    lead: "Lead",
  },
};

const VALUE_TIER_LABELS: Record<
  ClassificationLocale,
  Record<CustomerValueTier, string>
> = {
  es: { high: "Alto", medium: "Medio", low: "Bajo", none: "Sin compras" },
  en: { high: "High", medium: "Medium", low: "Low", none: "No purchases" },
  "pt-BR": { high: "Alto", medium: "Médio", low: "Baixo", none: "Sem compras" },
};

export function classificationLocale(language: string): ClassificationLocale {
  if (language.toLowerCase().startsWith("pt")) return "pt-BR";
  if (language.toLowerCase().startsWith("en")) return "en";
  return "es";
}

export function classificationLabel(
  value: CommercialClassification,
  locale: ClassificationLocale,
) {
  return CLASSIFICATION_LABELS[locale][value];
}

export function valueTierLabel(
  value: CustomerValueTier,
  locale: ClassificationLocale,
) {
  return VALUE_TIER_LABELS[locale][value];
}
