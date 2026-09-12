import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Check, Plus, Save, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  formatUnitEconomicsMoneyLabel,
  getUnitEconomicsConfig,
  replaceUnitEconomicsConfig,
  serializeUnitEconomicsConfig,
  validateUnitEconomicsConfig,
  type UnitEconomicsConfig,
  type UnitEconomicsPaymentMethodRule,
} from "../services/unitEconomics";
import "../unit-economics-settings.css";


interface UnitEconomicsSettingsPanelProps {
  storeId: number;
  currency: string;
  canWrite: boolean;
}


type LocaleKey = "es" | "en" | "pt-BR";


const COPY: Record<LocaleKey, {
  eyebrow: string;
  title: string;
  body: string;
  estimated: string;
  outbound: string;
  returns: string;
  paymentPercent: string;
  paymentFixed: string;
  codPercent: string;
  methodsTitle: string;
  methodsBody: string;
  addMethod: string;
  method: string;
  feePercent: string;
  feeFixed: string;
  isCod: string;
  methodCodPercent: string;
  remove: string;
  save: string;
  saving: string;
  loading: string;
  saved: string;
  loadError: string;
  saveError: string;
  readOnly: string;
  duplicateMethod: string;
  requiredMethod: string;
  invalidMoney: string;
  invalidPercentage: string;
  placeholderMethod: string;
}> = {
  es: {
    eyebrow: "UNIT ECONOMICS",
    title: "Costos operativos estimados",
    body: "Configura supuestos para costos que Diaglob todavía no puede obtener automáticamente. Los valores reales siempre tienen prioridad cuando exista una fuente confiable.",
    estimated: "Estimado",
    outbound: "Envío de salida",
    returns: "Logística de devolución",
    paymentPercent: "Comisión de pago por defecto (%)",
    paymentFixed: "Comisión fija de pago por defecto",
    codPercent: "Comisión contraentrega por defecto (%)",
    methodsTitle: "Reglas por método de pago",
    methodsBody: "Opcional. Sobrescribe campos específicos; los campos vacíos heredan el valor por defecto.",
    addMethod: "Agregar método",
    method: "Método",
    feePercent: "Comisión (%)",
    feeFixed: "Comisión fija",
    isCod: "Es contraentrega",
    methodCodPercent: "Contraentrega (%)",
    remove: "Eliminar",
    save: "Guardar costos",
    saving: "Guardando…",
    loading: "Cargando Unit Economics…",
    saved: "Costos estimados guardados.",
    loadError: "No se pudo cargar la configuración de Unit Economics.",
    saveError: "No se pudo guardar la configuración de Unit Economics.",
    readOnly: "Guarda primero los cambios de moneda de la tienda antes de editar estos costos.",
    duplicateMethod: "Hay métodos de pago duplicados después de normalizar espacios y mayúsculas.",
    requiredMethod: "Cada regla debe tener un método de pago.",
    invalidMoney: "Los costos monetarios deben ser números mayores o iguales a cero.",
    invalidPercentage: "Los porcentajes deben estar entre 0 y 100.",
    placeholderMethod: "ej. cash_on_delivery",
  },
  en: {
    eyebrow: "UNIT ECONOMICS",
    title: "Estimated operating costs",
    body: "Configure assumptions for costs Diaglob cannot obtain automatically yet. Actual values always take priority when a reliable source is available.",
    estimated: "Estimated",
    outbound: "Outbound shipping",
    returns: "Return logistics",
    paymentPercent: "Default payment fee (%)",
    paymentFixed: "Default fixed payment fee",
    codPercent: "Default cash-on-delivery fee (%)",
    methodsTitle: "Payment-method rules",
    methodsBody: "Optional. Override individual fields; blank fields inherit store defaults.",
    addMethod: "Add method",
    method: "Method",
    feePercent: "Fee (%)",
    feeFixed: "Fixed fee",
    isCod: "Cash on delivery",
    methodCodPercent: "COD fee (%)",
    remove: "Remove",
    save: "Save costs",
    saving: "Saving…",
    loading: "Loading Unit Economics…",
    saved: "Estimated costs saved.",
    loadError: "Unable to load Unit Economics configuration.",
    saveError: "Unable to save Unit Economics configuration.",
    readOnly: "Save the store currency change before editing these costs.",
    duplicateMethod: "Payment methods are duplicated after normalizing spaces and casing.",
    requiredMethod: "Every rule must include a payment method.",
    invalidMoney: "Monetary costs must be numbers greater than or equal to zero.",
    invalidPercentage: "Percentages must be between 0 and 100.",
    placeholderMethod: "e.g. cash_on_delivery",
  },
  "pt-BR": {
    eyebrow: "UNIT ECONOMICS",
    title: "Custos operacionais estimados",
    body: "Configure premissas para custos que a Diaglob ainda não consegue obter automaticamente. Valores reais sempre têm prioridade quando houver uma fonte confiável.",
    estimated: "Estimado",
    outbound: "Frete de saída",
    returns: "Logística de devolução",
    paymentPercent: "Taxa de pagamento padrão (%)",
    paymentFixed: "Taxa fixa de pagamento padrão",
    codPercent: "Taxa padrão de pagamento na entrega (%)",
    methodsTitle: "Regras por método de pagamento",
    methodsBody: "Opcional. Sobrescreva campos específicos; campos vazios herdam os valores padrão.",
    addMethod: "Adicionar método",
    method: "Método",
    feePercent: "Taxa (%)",
    feeFixed: "Taxa fixa",
    isCod: "Pagamento na entrega",
    methodCodPercent: "Taxa COD (%)",
    remove: "Remover",
    save: "Salvar custos",
    saving: "Salvando…",
    loading: "Carregando Unit Economics…",
    saved: "Custos estimados salvos.",
    loadError: "Não foi possível carregar a configuração de Unit Economics.",
    saveError: "Não foi possível salvar a configuração de Unit Economics.",
    readOnly: "Salve primeiro a mudança de moeda da loja antes de editar estes custos.",
    duplicateMethod: "Há métodos de pagamento duplicados após normalizar espaços e maiúsculas/minúsculas.",
    requiredMethod: "Cada regra deve ter um método de pagamento.",
    invalidMoney: "Custos monetários devem ser números maiores ou iguais a zero.",
    invalidPercentage: "Percentuais devem estar entre 0 e 100.",
    placeholderMethod: "ex. cash_on_delivery",
  },
};


function normalizeLocale(language: string): LocaleKey {
  if (language.toLowerCase().startsWith("pt")) return "pt-BR";
  if (language.toLowerCase().startsWith("en")) return "en";
  return "es";
}


function parseOptionalNumber(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : Number.NaN;
}


function emptyRule(): UnitEconomicsPaymentMethodRule {
  return {
    payment_method: "",
    fee_percent: null,
    fee_fixed: null,
    is_cod: false,
    cod_fee_percent: null,
  };
}


function validationMessage(
  code: string | null,
  copy: (typeof COPY)[LocaleKey],
): string {
  if (code === "duplicate_payment_method") return copy.duplicateMethod;
  if (code === "payment_method_required") return copy.requiredMethod;
  if (code === "invalid_percentage") return copy.invalidPercentage;
  return copy.invalidMoney;
}


export default function UnitEconomicsSettingsPanel({
  storeId,
  currency,
  canWrite,
}: UnitEconomicsSettingsPanelProps) {
  const { i18n } = useTranslation();
  const locale = normalizeLocale(i18n.resolvedLanguage || i18n.language || "es");
  const copy = COPY[locale];
  const [config, setConfig] = useState<UnitEconomicsConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError("");
        setSuccess("");
        const result = await getUnitEconomicsConfig(storeId);
        if (!cancelled) setConfig(result);
      } catch (err) {
        console.error(err);
        if (!cancelled) setError(copy.loadError);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [storeId, copy.loadError]);

  const effectiveCurrency = config?.currency || currency;
  const currencyChanged = useMemo(
    () => Boolean(config && config.currency !== currency),
    [config, currency],
  );
  const editable = canWrite && !currencyChanged;

  function updateConfig<K extends keyof UnitEconomicsConfig>(
    field: K,
    value: UnitEconomicsConfig[K],
  ) {
    setConfig((current) => current ? { ...current, [field]: value } : current);
    setSuccess("");
  }

  function updateRule(
    index: number,
    patch: Partial<UnitEconomicsPaymentMethodRule>,
  ) {
    setConfig((current) => {
      if (!current) return current;
      const rules = current.payment_methods.map((rule, ruleIndex) =>
        ruleIndex === index ? { ...rule, ...patch } : rule,
      );
      return { ...current, payment_methods: rules };
    });
    setSuccess("");
  }

  function removeRule(index: number) {
    setConfig((current) => current
      ? {
          ...current,
          payment_methods: current.payment_methods.filter((_, ruleIndex) => ruleIndex !== index),
        }
      : current,
    );
    setSuccess("");
  }

  async function save() {
    if (!config || !editable) return;
    const validation = validateUnitEconomicsConfig(config);
    if (!validation.valid) {
      setError(validationMessage(validation.error, copy));
      setSuccess("");
      return;
    }

    try {
      setSaving(true);
      setError("");
      setSuccess("");
      const saved = await replaceUnitEconomicsConfig(
        storeId,
        serializeUnitEconomicsConfig(config),
      );
      setConfig(saved);
      setSuccess(copy.saved);
    } catch (err: any) {
      console.error(err);
      const detail = err?.response?.data?.detail;
      if (typeof detail === "string") {
        setError(validationMessage(detail, copy));
      } else {
        setError(copy.saveError);
      }
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <div className="unit-economics-settings is-loading">{copy.loading}</div>;
  }

  if (!config) {
    return (
      <div className="unit-economics-settings">
        <div className="unit-economics-settings-alert is-error">
          <AlertTriangle size={15} />
          {error || copy.loadError}
        </div>
      </div>
    );
  }

  return (
    <section className="unit-economics-settings" aria-label={copy.title}>
      <div className="unit-economics-settings-heading">
        <div>
          <span>{copy.eyebrow}</span>
          <h3>{copy.title}</h3>
          <p>{copy.body}</p>
        </div>
        <span className="unit-economics-settings-badge">{copy.estimated}</span>
      </div>

      {(!editable || currencyChanged) && (
        <div className="unit-economics-settings-alert">
          <AlertTriangle size={15} />
          {copy.readOnly}
        </div>
      )}
      {error && (
        <div className="unit-economics-settings-alert is-error">
          <AlertTriangle size={15} />
          {error}
        </div>
      )}
      {success && (
        <div className="unit-economics-settings-alert is-success">
          <Check size={15} />
          {success}
        </div>
      )}

      <div className="unit-economics-settings-grid">
        <label>
          <span>{formatUnitEconomicsMoneyLabel(copy.outbound, effectiveCurrency)}</span>
          <input
            type="number"
            min="0"
            step="any"
            value={config.outbound_shipping_cost ?? ""}
            onChange={(event) => updateConfig(
              "outbound_shipping_cost",
              parseOptionalNumber(event.target.value),
            )}
            disabled={!editable || saving}
          />
        </label>
        <label>
          <span>{formatUnitEconomicsMoneyLabel(copy.returns, effectiveCurrency)}</span>
          <input
            type="number"
            min="0"
            step="any"
            value={config.return_logistics_cost ?? ""}
            onChange={(event) => updateConfig(
              "return_logistics_cost",
              parseOptionalNumber(event.target.value),
            )}
            disabled={!editable || saving}
          />
        </label>
        <label>
          <span>{copy.paymentPercent}</span>
          <input
            type="number"
            min="0"
            max="100"
            step="any"
            value={config.default_payment_fee_percent ?? ""}
            onChange={(event) => updateConfig(
              "default_payment_fee_percent",
              parseOptionalNumber(event.target.value),
            )}
            disabled={!editable || saving}
          />
        </label>
        <label>
          <span>{formatUnitEconomicsMoneyLabel(copy.paymentFixed, effectiveCurrency)}</span>
          <input
            type="number"
            min="0"
            step="any"
            value={config.default_payment_fee_fixed ?? ""}
            onChange={(event) => updateConfig(
              "default_payment_fee_fixed",
              parseOptionalNumber(event.target.value),
            )}
            disabled={!editable || saving}
          />
        </label>
        <label>
          <span>{copy.codPercent}</span>
          <input
            type="number"
            min="0"
            max="100"
            step="any"
            value={config.default_cod_fee_percent ?? ""}
            onChange={(event) => updateConfig(
              "default_cod_fee_percent",
              parseOptionalNumber(event.target.value),
            )}
            disabled={!editable || saving}
          />
        </label>
      </div>

      <div className="unit-economics-methods-heading">
        <div>
          <h4>{copy.methodsTitle}</h4>
          <p>{copy.methodsBody}</p>
        </div>
        {editable && (
          <button
            type="button"
            className="unit-economics-add"
            onClick={() => updateConfig(
              "payment_methods",
              [...config.payment_methods, emptyRule()],
            )}
            disabled={saving}
          >
            <Plus size={14} />
            {copy.addMethod}
          </button>
        )}
      </div>

      <div className="unit-economics-methods">
        {config.payment_methods.map((rule, index) => (
          <div className="unit-economics-method" key={`${index}-${rule.payment_method}`}>
            <label className="is-method">
              <span>{copy.method}</span>
              <input
                value={rule.payment_method}
                placeholder={copy.placeholderMethod}
                onChange={(event) => updateRule(index, { payment_method: event.target.value })}
                disabled={!editable || saving}
              />
            </label>
            <label>
              <span>{copy.feePercent}</span>
              <input
                type="number"
                min="0"
                max="100"
                step="any"
                value={rule.fee_percent ?? ""}
                onChange={(event) => updateRule(index, {
                  fee_percent: parseOptionalNumber(event.target.value),
                })}
                disabled={!editable || saving}
              />
            </label>
            <label>
              <span>{formatUnitEconomicsMoneyLabel(copy.feeFixed, effectiveCurrency)}</span>
              <input
                type="number"
                min="0"
                step="any"
                value={rule.fee_fixed ?? ""}
                onChange={(event) => updateRule(index, {
                  fee_fixed: parseOptionalNumber(event.target.value),
                })}
                disabled={!editable || saving}
              />
            </label>
            <label className="is-checkbox">
              <span>{copy.isCod}</span>
              <input
                type="checkbox"
                checked={rule.is_cod}
                onChange={(event) => updateRule(index, {
                  is_cod: event.target.checked,
                  cod_fee_percent: event.target.checked ? rule.cod_fee_percent : null,
                })}
                disabled={!editable || saving}
              />
            </label>
            {rule.is_cod && (
              <label>
                <span>{copy.methodCodPercent}</span>
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="any"
                  value={rule.cod_fee_percent ?? ""}
                  onChange={(event) => updateRule(index, {
                    cod_fee_percent: parseOptionalNumber(event.target.value),
                  })}
                  disabled={!editable || saving}
                />
              </label>
            )}
            {editable && (
              <button
                type="button"
                className="unit-economics-remove"
                onClick={() => removeRule(index)}
                disabled={saving}
                aria-label={copy.remove}
              >
                <Trash2 size={14} />
              </button>
            )}
          </div>
        ))}
      </div>

      {editable && (
        <div className="unit-economics-settings-actions">
          <button
            type="button"
            className="unit-economics-save"
            onClick={() => void save()}
            disabled={saving}
          >
            <Save size={15} />
            {saving ? copy.saving : copy.save}
          </button>
        </div>
      )}
    </section>
  );
}
