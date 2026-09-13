import { api } from "./api";
import type {
  UnitEconomicsConfig,
  UnitEconomicsConfigPayload,
} from "../utils/unitEconomicsConfig";

export {
  MAX_UNIT_ECONOMICS_PAYMENT_METHOD_LENGTH,
  formatUnitEconomicsMoneyLabel,
  isValidUnitEconomicsMoney,
  isValidUnitEconomicsPercentage,
  normalizeUnitEconomicsPaymentMethod,
  serializeUnitEconomicsConfig,
  validateUnitEconomicsConfig,
} from "../utils/unitEconomicsConfig";
export type {
  UnitEconomicsConfig,
  UnitEconomicsConfigPayload,
  UnitEconomicsPaymentMethodRule,
  UnitEconomicsValidationResult,
} from "../utils/unitEconomicsConfig";


const globalHeaders = {
  "X-Diaglob-Global-Scope": "1",
};


export async function getUnitEconomicsConfig(storeId: number) {
  const response = await api.get<UnitEconomicsConfig>(
    `/api/stores/${storeId}/unit-economics/config`,
    { headers: globalHeaders },
  );
  return response.data;
}


export async function replaceUnitEconomicsConfig(
  storeId: number,
  payload: UnitEconomicsConfigPayload,
) {
  const response = await api.put<UnitEconomicsConfig>(
    `/api/stores/${storeId}/unit-economics/config`,
    payload,
    { headers: globalHeaders },
  );
  return response.data;
}
