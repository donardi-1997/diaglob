export interface UnitEconomicsPaymentMethodRule {
  payment_method: string;
  fee_percent: number | null;
  fee_fixed: number | null;
  is_cod: boolean;
  cod_fee_percent: number | null;
}


export interface UnitEconomicsConfig {
  store_id: number;
  currency: string;
  outbound_shipping_cost: number | null;
  return_logistics_cost: number | null;
  default_payment_fee_percent: number | null;
  default_payment_fee_fixed: number | null;
  default_cod_fee_percent: number | null;
  payment_methods: UnitEconomicsPaymentMethodRule[];
}


export type UnitEconomicsConfigPayload = Omit<
  UnitEconomicsConfig,
  "store_id" | "currency"
>;


export interface UnitEconomicsValidationResult {
  valid: boolean;
  error: string | null;
}


export const MAX_UNIT_ECONOMICS_PAYMENT_METHOD_LENGTH = 50;


export function normalizeUnitEconomicsPaymentMethod(value: string): string {
  return value.trim().toLowerCase();
}


export function isValidUnitEconomicsMoney(value: number | null): boolean {
  return value === null || (Number.isFinite(value) && value >= 0);
}


export function isValidUnitEconomicsPercentage(value: number | null): boolean {
  return value === null || (Number.isFinite(value) && value >= 0 && value <= 100);
}


export function formatUnitEconomicsMoneyLabel(label: string, currency: string): string {
  return `${label} (${currency})`;
}


export function validateUnitEconomicsConfig(
  config: UnitEconomicsConfig,
): UnitEconomicsValidationResult {
  const moneyValues = [
    config.outbound_shipping_cost,
    config.return_logistics_cost,
    config.default_payment_fee_fixed,
  ];
  if (moneyValues.some((value) => !isValidUnitEconomicsMoney(value))) {
    return { valid: false, error: "invalid_money" };
  }

  const percentageValues = [
    config.default_payment_fee_percent,
    config.default_cod_fee_percent,
  ];
  if (percentageValues.some((value) => !isValidUnitEconomicsPercentage(value))) {
    return { valid: false, error: "invalid_percentage" };
  }

  const methods = new Set<string>();
  for (const rule of config.payment_methods) {
    const method = normalizeUnitEconomicsPaymentMethod(rule.payment_method);
    if (!method) {
      return { valid: false, error: "payment_method_required" };
    }
    if (method.length > MAX_UNIT_ECONOMICS_PAYMENT_METHOD_LENGTH) {
      return { valid: false, error: "payment_method_too_long" };
    }
    if (methods.has(method)) {
      return { valid: false, error: "duplicate_payment_method" };
    }
    methods.add(method);

    if (!isValidUnitEconomicsMoney(rule.fee_fixed)) {
      return { valid: false, error: "invalid_money" };
    }
    if (!isValidUnitEconomicsPercentage(rule.fee_percent)) {
      return { valid: false, error: "invalid_percentage" };
    }
    if (rule.is_cod && !isValidUnitEconomicsPercentage(rule.cod_fee_percent)) {
      return { valid: false, error: "invalid_percentage" };
    }
  }

  return { valid: true, error: null };
}


export function serializeUnitEconomicsConfig(
  config: UnitEconomicsConfig,
): UnitEconomicsConfigPayload {
  return {
    outbound_shipping_cost: config.outbound_shipping_cost,
    return_logistics_cost: config.return_logistics_cost,
    default_payment_fee_percent: config.default_payment_fee_percent,
    default_payment_fee_fixed: config.default_payment_fee_fixed,
    default_cod_fee_percent: config.default_cod_fee_percent,
    payment_methods: config.payment_methods.map((rule) => ({
      payment_method: normalizeUnitEconomicsPaymentMethod(rule.payment_method),
      fee_percent: rule.fee_percent,
      fee_fixed: rule.fee_fixed,
      is_cod: rule.is_cod,
      cod_fee_percent: rule.is_cod ? rule.cod_fee_percent : null,
    })),
  };
}
