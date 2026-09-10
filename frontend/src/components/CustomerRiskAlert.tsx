import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, LoaderCircle, ShieldAlert, X } from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  dismissCustomerRiskReport,
  reportCustomerRisk,
  type CustomerRiskReason,
  type CustomerRiskSummary,
} from "../services/customerRisk";
import "../customer-risk-alert.css";


type LocaleKey = "es" | "en" | "pt-BR";

interface Props {
  customerId: number;
  risk?: CustomerRiskSummary | null;
  storeId?: number;
  canReport?: boolean;
  compact?: boolean;
  onChanged?: (risk: CustomerRiskSummary) => void;
}

const COPY = {
  es: {
    caution: "Señal de riesgo compartida",
    high: "Precaución alta",
    elevated: "Precaución",
    notice: "Señal reportada",
    reportedBy: "organizaciones independientes han reportado señales sobre este cliente",
    reportedByOne: "organización ha reportado una señal sobre este cliente",
    private: "Diaglob no muestra quién realizó los reportes ni comparte sus notas o evidencia privadas.",
    notVerdict: "Esta alerta es una señal preventiva, no una determinación de fraude ni culpabilidad.",
    report: "Reportar señal",
    update: "Actualizar mi reporte",
    withdraw: "Retirar mi reporte",
    formTitle: "Reportar señal de riesgo",
    formHelp: "Describe hechos observados. Evita insultos o afirmaciones de delitos que no puedas sustentar.",
    reason: "Motivo",
    notes: "Notas internas (opcional)",
    evidence: "Referencia de evidencia (opcional)",
    evidenceHint: "Ej. ID de pedido, ticket interno o enlace autorizado",
    save: "Guardar reporte",
    saving: "Guardando...",
    cancel: "Cancelar",
    failed: "No se pudo guardar el reporte.",
    withdrawFailed: "No se pudo retirar el reporte.",
    noSignals: "Sin señales compartidas",
    noSignalsHelp: "No hay reportes activos coincidentes con los identificadores de este cliente.",
    reasons: {
      suspected_fraud: "Posible fraude",
      payment_abuse: "Problema de pago o contracargo",
      delivery_claim: "Reclamo de entrega inconsistente",
      identity_mismatch: "Datos o identidad inconsistentes",
      abusive_behavior: "Comportamiento abusivo",
      other: "Otro",
    },
  },
  en: {
    caution: "Shared risk signal",
    high: "High caution",
    elevated: "Caution",
    notice: "Reported signal",
    reportedBy: "independent organizations have reported signals about this customer",
    reportedByOne: "organization has reported a signal about this customer",
    private: "Diaglob does not reveal who submitted reports or share their private notes or evidence.",
    notVerdict: "This alert is a preventive signal, not a determination of fraud or guilt.",
    report: "Report signal",
    update: "Update my report",
    withdraw: "Withdraw my report",
    formTitle: "Report a risk signal",
    formHelp: "Describe observed facts. Avoid insults or allegations of crimes you cannot substantiate.",
    reason: "Reason",
    notes: "Internal notes (optional)",
    evidence: "Evidence reference (optional)",
    evidenceHint: "E.g. order ID, internal ticket or authorized link",
    save: "Save report",
    saving: "Saving...",
    cancel: "Cancel",
    failed: "The report could not be saved.",
    withdrawFailed: "The report could not be withdrawn.",
    noSignals: "No shared signals",
    noSignalsHelp: "There are no active reports matching this customer's identifiers.",
    reasons: {
      suspected_fraud: "Suspected fraud",
      payment_abuse: "Payment or chargeback issue",
      delivery_claim: "Inconsistent delivery claim",
      identity_mismatch: "Inconsistent identity or data",
      abusive_behavior: "Abusive behavior",
      other: "Other",
    },
  },
  "pt-BR": {
    caution: "Sinal de risco compartilhado",
    high: "Alta precaução",
    elevated: "Precaução",
    notice: "Sinal reportado",
    reportedBy: "organizações independentes reportaram sinais sobre este cliente",
    reportedByOne: "organização reportou um sinal sobre este cliente",
    private: "O Diaglob não mostra quem enviou os relatos nem compartilha notas ou evidências privadas.",
    notVerdict: "Este alerta é um sinal preventivo, não uma determinação de fraude ou culpa.",
    report: "Reportar sinal",
    update: "Atualizar meu relato",
    withdraw: "Retirar meu relato",
    formTitle: "Reportar sinal de risco",
    formHelp: "Descreva fatos observados. Evite insultos ou acusações de crimes que você não possa sustentar.",
    reason: "Motivo",
    notes: "Notas internas (opcional)",
    evidence: "Referência de evidência (opcional)",
    evidenceHint: "Ex. ID do pedido, ticket interno ou link autorizado",
    save: "Salvar relato",
    saving: "Salvando...",
    cancel: "Cancelar",
    failed: "Não foi possível salvar o relato.",
    withdrawFailed: "Não foi possível retirar o relato.",
    noSignals: "Sem sinais compartilhados",
    noSignalsHelp: "Não há relatos ativos que coincidam com os identificadores deste cliente.",
    reasons: {
      suspected_fraud: "Possível fraude",
      payment_abuse: "Problema de pagamento ou chargeback",
      delivery_claim: "Reclamação de entrega inconsistente",
      identity_mismatch: "Dados ou identidade inconsistentes",
      abusive_behavior: "Comportamento abusivo",
      other: "Outro",
    },
  },
} as const;

const REASONS: CustomerRiskReason[] = [
  "suspected_fraud",
  "payment_abuse",
  "delivery_claim",
  "identity_mismatch",
  "abusive_behavior",
  "other",
];

function localeFor(language: string): LocaleKey {
  if (language.toLowerCase().startsWith("pt")) return "pt-BR";
  if (language.toLowerCase().startsWith("en")) return "en";
  return "es";
}

export default function CustomerRiskAlert({
  customerId,
  risk,
  storeId,
  canReport = false,
  compact = false,
  onChanged,
}: Props) {
  const { i18n } = useTranslation();
  const copy = COPY[localeFor(i18n.language)];
  const [current, setCurrent] = useState<CustomerRiskSummary | null>(risk ?? null);
  const [formOpen, setFormOpen] = useState(false);
  const [reason, setReason] = useState<CustomerRiskReason>(
    risk?.current_organization_report?.reason ?? "suspected_fraud",
  );
  const [notes, setNotes] = useState(risk?.current_organization_report?.notes ?? "");
  const [evidence, setEvidence] = useState(
    risk?.current_organization_report?.evidence_reference ?? "",
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setCurrent(risk ?? null);
  }, [customerId, risk]);

  const value = current ?? risk;
  const reasonLabels = useMemo(() => {
    if (!value?.reason_counts) return [];
    return REASONS
      .filter((item) => (value.reason_counts[item] ?? 0) > 0)
      .map((item) => copy.reasons[item]);
  }, [value, copy.reasons]);

  function publish(next: CustomerRiskSummary) {
    setCurrent(next);
    onChanged?.(next);
  }

  function openForm() {
    const mine = value?.current_organization_report;
    setReason(mine?.reason ?? "suspected_fraud");
    setNotes(mine?.notes ?? "");
    setEvidence(mine?.evidence_reference ?? "");
    setError("");
    setFormOpen(true);
  }

  async function submit() {
    setSaving(true);
    setError("");
    try {
      const next = await reportCustomerRisk(customerId, {
        reason,
        notes: notes.trim() || undefined,
        evidence_reference: evidence.trim() || undefined,
        store_id: storeId,
      });
      publish(next);
      setFormOpen(false);
    } catch {
      setError(copy.failed);
    } finally {
      setSaving(false);
    }
  }

  async function withdraw() {
    setSaving(true);
    setError("");
    try {
      publish(await dismissCustomerRiskReport(customerId));
      setFormOpen(false);
    } catch {
      setError(copy.withdrawFailed);
    } finally {
      setSaving(false);
    }
  }

  if (!value?.available) return null;

  if (compact) {
    if (!value.alert) return null;
    return (
      <span
        className={`customer-risk-chip severity-${value.severity}`}
        title={copy.notVerdict}
      >
        <ShieldAlert size={13} />
        {copy.caution} · {value.reporting_organizations}
      </span>
    );
  }

  const severityLabel = value.alert
    ? value.severity === "high"
      ? copy.high
      : value.severity === "elevated"
        ? copy.elevated
        : copy.notice
    : copy.noSignals;

  return (
    <>
      <section
        className={`customer-risk-alert ${value.alert ? `severity-${value.severity}` : "no-risk"}`}
      >
        <div className="customer-risk-alert-icon">
          {value.alert ? <ShieldAlert size={19} /> : <AlertTriangle size={18} />}
        </div>
        <div className="customer-risk-alert-copy">
          <strong>{severityLabel}</strong>
          {value.alert ? (
            <>
              <p>
                {value.reporting_organizations}{" "}
                {value.reporting_organizations === 1
                  ? copy.reportedByOne
                  : copy.reportedBy}.
              </p>
              {reasonLabels.length > 0 && (
                <div className="customer-risk-reasons">
                  {reasonLabels.map((label) => <span key={label}>{label}</span>)}
                </div>
              )}
              <small>{copy.notVerdict} {copy.private}</small>
            </>
          ) : (
            <p>{copy.noSignalsHelp}</p>
          )}
        </div>
        {canReport && (
          <div className="customer-risk-actions">
            <button type="button" onClick={openForm}>
              {value.reported_by_current_organization ? copy.update : copy.report}
            </button>
          </div>
        )}
      </section>

      {formOpen && (
        <div className="customer-risk-modal-backdrop" role="presentation">
          <div className="customer-risk-modal" role="dialog" aria-modal="true">
            <div className="customer-risk-modal-header">
              <div>
                <strong>{copy.formTitle}</strong>
                <p>{copy.formHelp}</p>
              </div>
              <button
                type="button"
                className="customer-risk-close"
                onClick={() => setFormOpen(false)}
                disabled={saving}
                aria-label={copy.cancel}
              >
                <X size={17} />
              </button>
            </div>

            <label>
              <span>{copy.reason}</span>
              <select
                value={reason}
                onChange={(event) => setReason(event.target.value as CustomerRiskReason)}
              >
                {REASONS.map((item) => (
                  <option key={item} value={item}>{copy.reasons[item]}</option>
                ))}
              </select>
            </label>

            <label>
              <span>{copy.notes}</span>
              <textarea
                value={notes}
                maxLength={2000}
                rows={4}
                onChange={(event) => setNotes(event.target.value)}
              />
            </label>

            <label>
              <span>{copy.evidence}</span>
              <input
                value={evidence}
                maxLength={1000}
                placeholder={copy.evidenceHint}
                onChange={(event) => setEvidence(event.target.value)}
              />
            </label>

            {error && <div className="customer-risk-error">{error}</div>}

            <div className="customer-risk-modal-footer">
              {value.reported_by_current_organization && (
                <button
                  type="button"
                  className="customer-risk-withdraw"
                  onClick={() => void withdraw()}
                  disabled={saving}
                >
                  {copy.withdraw}
                </button>
              )}
              <button
                type="button"
                className="customer-risk-cancel"
                onClick={() => setFormOpen(false)}
                disabled={saving}
              >
                {copy.cancel}
              </button>
              <button
                type="button"
                className="customer-risk-save"
                onClick={() => void submit()}
                disabled={saving}
              >
                {saving && <LoaderCircle className="spin" size={14} />}
                {saving ? copy.saving : copy.save}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
