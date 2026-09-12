import type {
  DropshippingInsight,
  DropshippingInsightSeverity,
} from "../services/analytics";

export type DecisionInsightLocale = "es" | "en" | "pt-BR";
export type DecisionEvidenceFormat = "currency" | "percent" | "days" | "number";

export interface DecisionEvidenceItem {
  key: string;
  label: string;
  value: number | string | null;
  format: DecisionEvidenceFormat;
}

export interface DecisionInsightPresentation {
  title: string;
  reason: string;
  action: string;
  severityLabel: string;
  evidence: DecisionEvidenceItem[];
}

export interface DecisionInsightSectionCopy {
  kicker: string;
  title: string;
  subtitle: string;
  empty: string;
  unavailable: string;
  viewProduct: string;
  recommendedAction: string;
}

type CopyBundle = {
  section: DecisionInsightSectionCopy;
  severities: Record<DropshippingInsightSeverity, string>;
  titles: Record<string, string>;
  reasons: Record<string, string>;
  actions: Record<string, string>;
  evidence: Record<string, { label: string; format: DecisionEvidenceFormat }>;
};

const ES: CopyBundle = {
  section: {
    kicker: "DECISION INTELLIGENCE",
    title: "Qué requiere tu atención",
    subtitle: "Diagnósticos determinísticos basados en rentabilidad, operación, concentración e inventario.",
    empty: "No detectamos alertas ni oportunidades accionables con los datos del período seleccionado.",
    unavailable: "Decision Intelligence no está disponible temporalmente. Las demás analíticas siguen activas.",
    viewProduct: "Ver producto",
    recommendedAction: "Acción recomendada",
  },
  severities: {
    critical: "Crítico",
    warning: "Atención",
    opportunity: "Oportunidad",
    positive: "Positivo",
  },
  titles: {
    negative_margin: "Margen negativo",
    low_margin: "Margen bajo",
    cost_incomplete: "Costos incompletos",
    delivery_risk: "Riesgo de entrega",
    cancellation_risk: "Cancelaciones elevadas",
    return_risk: "Devoluciones elevadas",
    stockout: "Sin inventario",
    stock_runway_critical: "Stock crítico",
    stock_runway_warning: "Stock por agotarse",
    revenue_concentration: "Ingresos concentrados",
    profit_concentration: "Utilidad concentrada",
    winner: "Producto ganador",
    opportunity: "Oportunidad de crecimiento",
  },
  reasons: {
    gross_profit_below_zero: "Las ventas entregadas no cubren el costo registrado del producto.",
    gross_margin_below_threshold: "El margen bruto está por debajo del umbral saludable definido para esta versión.",
    cost_coverage_incomplete: "Faltan costos en ítems entregados, por lo que la rentabilidad aún es parcial.",
    delivery_rate_below_threshold: "La tasa de entrega está por debajo del 60% con una muestra operativa suficiente.",
    cancellation_rate_above_threshold: "Más del 25% de los pedidos del producto terminan cancelados.",
    return_rate_above_threshold: "Más del 15% de los pedidos enviados terminan devueltos.",
    inventory_zero_with_sales: "El producto tuvo unidades entregadas en el período y actualmente no tiene inventario.",
    stock_runway_below_threshold: "El inventario actual alcanzaría para menos de siete días al ritmo observado.",
    revenue_share_above_threshold: "Este producto concentra al menos la mitad de los ingresos entregados de la tienda.",
    profit_share_above_threshold: "Este producto concentra al menos la mitad de la utilidad bruta positiva de la tienda.",
    winner_quality_thresholds_met: "Combina margen, entrega y calidad operativa suficientes para considerarlo un ganador.",
    opportunity_quality_thresholds_met: "Tiene buena calidad operativa y margen, pero todavía representa una porción pequeña de los ingresos.",
  },
  actions: {
    review_price_and_cost: "Revisar precio y costo",
    improve_unit_economics: "Mejorar economía por unidad",
    complete_product_costs: "Completar costos del producto",
    review_fulfillment_quality: "Revisar calidad de fulfillment",
    review_confirmation_and_offer: "Revisar confirmación y oferta",
    review_product_expectations: "Revisar expectativas del producto",
    replenish_stock: "Reponer inventario",
    diversify_product_mix: "Diversificar mezcla de productos",
    diversify_profit_sources: "Diversificar fuentes de utilidad",
    consider_scaling: "Considerar escalar volumen",
    test_more_volume: "Probar más volumen",
  },
  evidence: {
    gross_profit: { label: "Utilidad bruta", format: "currency" },
    gross_margin: { label: "Margen bruto", format: "percent" },
    delivered_revenue: { label: "Ingresos entregados", format: "currency" },
    cost_completeness_pct: { label: "Cobertura de costos", format: "percent" },
    delivered_orders: { label: "Pedidos entregados", format: "number" },
    shipped_orders: { label: "Pedidos enviados", format: "number" },
    delivery_rate: { label: "Tasa de entrega", format: "percent" },
    cancellation_rate: { label: "Tasa de cancelación", format: "percent" },
    cancelled_orders: { label: "Pedidos cancelados", format: "number" },
    total_orders: { label: "Pedidos totales", format: "number" },
    return_rate: { label: "Tasa de devolución", format: "percent" },
    returned_orders: { label: "Pedidos devueltos", format: "number" },
    inventory_quantity: { label: "Inventario actual", format: "number" },
    units_delivered: { label: "Unidades entregadas", format: "number" },
    units_per_day: { label: "Unidades por día", format: "number" },
    stock_runway_days: { label: "Días de inventario", format: "days" },
    revenue_share_pct: { label: "Participación en ingresos", format: "percent" },
    profit_share_pct: { label: "Participación en utilidad", format: "percent" },
  },
};

const EN: CopyBundle = {
  section: {
    kicker: "DECISION INTELLIGENCE",
    title: "What needs your attention",
    subtitle: "Deterministic diagnostics based on profitability, operations, concentration and inventory.",
    empty: "No actionable alerts or opportunities were detected for the selected period.",
    unavailable: "Decision Intelligence is temporarily unavailable. The rest of analytics remains active.",
    viewProduct: "View product",
    recommendedAction: "Recommended action",
  },
  severities: {
    critical: "Critical",
    warning: "Attention",
    opportunity: "Opportunity",
    positive: "Positive",
  },
  titles: {
    negative_margin: "Negative margin",
    low_margin: "Low margin",
    cost_incomplete: "Incomplete costs",
    delivery_risk: "Delivery risk",
    cancellation_risk: "High cancellations",
    return_risk: "High returns",
    stockout: "Out of stock",
    stock_runway_critical: "Critical stock",
    stock_runway_warning: "Stock running low",
    revenue_concentration: "Revenue concentration",
    profit_concentration: "Profit concentration",
    winner: "Winning product",
    opportunity: "Growth opportunity",
  },
  reasons: {
    gross_profit_below_zero: "Delivered sales do not cover the product's recorded cost.",
    gross_margin_below_threshold: "Gross margin is below the healthy threshold defined for this version.",
    cost_coverage_incomplete: "Some delivered items are missing costs, so profitability is still partial.",
    delivery_rate_below_threshold: "Delivery rate is below 60% with a sufficient operational sample.",
    cancellation_rate_above_threshold: "More than 25% of this product's orders end up cancelled.",
    return_rate_above_threshold: "More than 15% of shipped orders end up returned.",
    inventory_zero_with_sales: "The product had delivered units in the period and currently has no inventory.",
    stock_runway_below_threshold: "Current inventory would last fewer than seven days at the observed pace.",
    revenue_share_above_threshold: "This product represents at least half of the store's delivered revenue.",
    profit_share_above_threshold: "This product represents at least half of the store's positive gross profit.",
    winner_quality_thresholds_met: "Margin, delivery and operating quality meet the thresholds for a winning product.",
    opportunity_quality_thresholds_met: "Operating quality and margin are strong, but the product still represents a small revenue share.",
  },
  actions: {
    review_price_and_cost: "Review price and cost",
    improve_unit_economics: "Improve unit economics",
    complete_product_costs: "Complete product costs",
    review_fulfillment_quality: "Review fulfillment quality",
    review_confirmation_and_offer: "Review confirmation and offer",
    review_product_expectations: "Review product expectations",
    replenish_stock: "Replenish inventory",
    diversify_product_mix: "Diversify product mix",
    diversify_profit_sources: "Diversify profit sources",
    consider_scaling: "Consider scaling volume",
    test_more_volume: "Test more volume",
  },
  evidence: {
    gross_profit: { label: "Gross profit", format: "currency" },
    gross_margin: { label: "Gross margin", format: "percent" },
    delivered_revenue: { label: "Delivered revenue", format: "currency" },
    cost_completeness_pct: { label: "Cost coverage", format: "percent" },
    delivered_orders: { label: "Delivered orders", format: "number" },
    shipped_orders: { label: "Shipped orders", format: "number" },
    delivery_rate: { label: "Delivery rate", format: "percent" },
    cancellation_rate: { label: "Cancellation rate", format: "percent" },
    cancelled_orders: { label: "Cancelled orders", format: "number" },
    total_orders: { label: "Total orders", format: "number" },
    return_rate: { label: "Return rate", format: "percent" },
    returned_orders: { label: "Returned orders", format: "number" },
    inventory_quantity: { label: "Current inventory", format: "number" },
    units_delivered: { label: "Delivered units", format: "number" },
    units_per_day: { label: "Units per day", format: "number" },
    stock_runway_days: { label: "Inventory days", format: "days" },
    revenue_share_pct: { label: "Revenue share", format: "percent" },
    profit_share_pct: { label: "Profit share", format: "percent" },
  },
};

const PT: CopyBundle = {
  section: {
    kicker: "DECISION INTELLIGENCE",
    title: "O que precisa da sua atenção",
    subtitle: "Diagnósticos determinísticos baseados em rentabilidade, operação, concentração e estoque.",
    empty: "Nenhum alerta ou oportunidade acionável foi detectado no período selecionado.",
    unavailable: "Decision Intelligence está temporariamente indisponível. As demais análises continuam ativas.",
    viewProduct: "Ver produto",
    recommendedAction: "Ação recomendada",
  },
  severities: {
    critical: "Crítico",
    warning: "Atenção",
    opportunity: "Oportunidade",
    positive: "Positivo",
  },
  titles: {
    negative_margin: "Margem negativa",
    low_margin: "Margem baixa",
    cost_incomplete: "Custos incompletos",
    delivery_risk: "Risco de entrega",
    cancellation_risk: "Cancelamentos elevados",
    return_risk: "Devoluções elevadas",
    stockout: "Sem estoque",
    stock_runway_critical: "Estoque crítico",
    stock_runway_warning: "Estoque próximo do fim",
    revenue_concentration: "Receita concentrada",
    profit_concentration: "Lucro concentrado",
    winner: "Produto vencedor",
    opportunity: "Oportunidade de crescimento",
  },
  reasons: {
    gross_profit_below_zero: "As vendas entregues não cobrem o custo registrado do produto.",
    gross_margin_below_threshold: "A margem bruta está abaixo do limite saudável definido para esta versão.",
    cost_coverage_incomplete: "Há itens entregues sem custo, então a rentabilidade ainda é parcial.",
    delivery_rate_below_threshold: "A taxa de entrega está abaixo de 60% com uma amostra operacional suficiente.",
    cancellation_rate_above_threshold: "Mais de 25% dos pedidos deste produto terminam cancelados.",
    return_rate_above_threshold: "Mais de 15% dos pedidos enviados terminam devolvidos.",
    inventory_zero_with_sales: "O produto teve unidades entregues no período e atualmente está sem estoque.",
    stock_runway_below_threshold: "O estoque atual duraria menos de sete dias no ritmo observado.",
    revenue_share_above_threshold: "Este produto representa pelo menos metade da receita entregue da loja.",
    profit_share_above_threshold: "Este produto representa pelo menos metade do lucro bruto positivo da loja.",
    winner_quality_thresholds_met: "Margem, entrega e qualidade operacional atingem os limites de um produto vencedor.",
    opportunity_quality_thresholds_met: "Qualidade operacional e margem são fortes, mas o produto ainda representa uma pequena parcela da receita.",
  },
  actions: {
    review_price_and_cost: "Revisar preço e custo",
    improve_unit_economics: "Melhorar economia por unidade",
    complete_product_costs: "Completar custos do produto",
    review_fulfillment_quality: "Revisar qualidade do fulfillment",
    review_confirmation_and_offer: "Revisar confirmação e oferta",
    review_product_expectations: "Revisar expectativas do produto",
    replenish_stock: "Repor estoque",
    diversify_product_mix: "Diversificar mix de produtos",
    diversify_profit_sources: "Diversificar fontes de lucro",
    consider_scaling: "Considerar escalar volume",
    test_more_volume: "Testar mais volume",
  },
  evidence: {
    gross_profit: { label: "Lucro bruto", format: "currency" },
    gross_margin: { label: "Margem bruta", format: "percent" },
    delivered_revenue: { label: "Receita entregue", format: "currency" },
    cost_completeness_pct: { label: "Cobertura de custos", format: "percent" },
    delivered_orders: { label: "Pedidos entregues", format: "number" },
    shipped_orders: { label: "Pedidos enviados", format: "number" },
    delivery_rate: { label: "Taxa de entrega", format: "percent" },
    cancellation_rate: { label: "Taxa de cancelamento", format: "percent" },
    cancelled_orders: { label: "Pedidos cancelados", format: "number" },
    total_orders: { label: "Pedidos totais", format: "number" },
    return_rate: { label: "Taxa de devolução", format: "percent" },
    returned_orders: { label: "Pedidos devolvidos", format: "number" },
    inventory_quantity: { label: "Estoque atual", format: "number" },
    units_delivered: { label: "Unidades entregues", format: "number" },
    units_per_day: { label: "Unidades por dia", format: "number" },
    stock_runway_days: { label: "Dias de estoque", format: "days" },
    revenue_share_pct: { label: "Participação na receita", format: "percent" },
    profit_share_pct: { label: "Participação no lucro", format: "percent" },
  },
};

const COPY: Record<DecisionInsightLocale, CopyBundle> = {
  es: ES,
  en: EN,
  "pt-BR": PT,
};

export function normalizeDecisionInsightLocale(language: string): DecisionInsightLocale {
  const normalized = (language || "").toLowerCase();
  if (normalized.startsWith("pt")) return "pt-BR";
  if (normalized.startsWith("en")) return "en";
  return "es";
}

function requiredCopy(map: Record<string, string>, key: string): string {
  const value = map[key];
  if (!value) {
    throw new Error(`Unknown decision insight copy key: ${key}`);
  }
  return value;
}

export function getDecisionInsightSectionCopy(language: string): DecisionInsightSectionCopy {
  return COPY[normalizeDecisionInsightLocale(language)].section;
}

export function getDecisionInsightPresentation(
  insight: DropshippingInsight,
  language: string,
): DecisionInsightPresentation {
  const bundle = COPY[normalizeDecisionInsightLocale(language)];
  const evidence = Object.entries(insight.evidence)
    .flatMap(([key, value]) => {
      const metadata = bundle.evidence[key];
      return metadata ? [{ key, label: metadata.label, value, format: metadata.format }] : [];
    })
    .slice(0, 3);

  return {
    title: requiredCopy(bundle.titles, insight.title_key),
    reason: requiredCopy(bundle.reasons, insight.reason_key),
    action: requiredCopy(bundle.actions, insight.action_key),
    severityLabel: bundle.severities[insight.severity],
    evidence,
  };
}

export function selectedProductIdFromInsight(insight: DropshippingInsight): number | null {
  return typeof insight.product_id === "number" ? insight.product_id : null;
}

export function nextSelectedProductId(
  currentProductId: number | null,
  requestedProductId: number,
): number | null {
  return currentProductId === requestedProductId ? null : requestedProductId;
}
