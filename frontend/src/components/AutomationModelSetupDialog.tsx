import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Check, Copy, ExternalLink, Loader2, RefreshCw, X, Zap } from "lucide-react";

import { api } from "../services/api";
import { listWhatsAppTemplates, type WhatsAppMessageTemplate } from "../services/automations";
import {
  FLOW_TEMPLATE_VARIABLES,
  previewTemplateBody,
  templateBodyText,
  templateParameterCount,
} from "./automation-flows/flowWhatsAppTemplates";
import { createdTemplateFlowId, templateGraphSteps } from "../utils/automationTemplateFlow";
import {
  buildModelSetupPayload,
  modelSetupErrorKey,
  suggestedMapping,
  suggestedTemplateClipboard,
  type ModelWhatsAppSetup,
} from "../utils/automationModelSetup";

export interface SetupModel {
  id: string;
  name: string;
  description: string;
  graph: Record<string, unknown>;
  trigger_type?: string | null;
  trigger_mode?: "automatic" | "manual";
  whatsapp_setup?: ModelWhatsAppSetup;
}

interface Props {
  storeId: number;
  model: SetupModel;
  onClose: () => void;
  onCreated: (flowId: number, activated: boolean) => void;
}

const META_TEMPLATES_URL = "https://business.facebook.com/wa/manage/message-templates/";

export default function AutomationModelSetupDialog({ storeId, model, onClose, onCreated }: Props) {
  const { t } = useTranslation();
  const suggested = model.whatsapp_setup?.suggested_template;

  const [templates, setTemplates] = useState<WhatsAppMessageTemplate[]>([]);
  const [loadingTemplates, setLoadingTemplates] = useState(Boolean(suggested));
  const [syncing, setSyncing] = useState(false);
  const [templateId, setTemplateId] = useState<number | null>(null);
  const [mapping, setMapping] = useState<string[]>([]);
  const [messageMode, setMessageMode] = useState<"auto" | "template">("auto");
  const [name, setName] = useState(model.name);
  const [activate, setActivate] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  const approved = useMemo(() => templates.filter((item) => item.status === "approved"), [templates]);
  const selected = approved.find((item) => item.id === templateId) ?? null;
  const steps = templateGraphSteps(model.graph);

  function applyTemplates(items: WhatsAppMessageTemplate[]) {
    setTemplates(items);
    // Preselect a synced template that already matches the suggested name.
    const match = items.find(
      (item) => item.status === "approved" && item.provider_template_name === suggested?.name,
    );
    if (match && templateId === null) selectTemplate(match.id, items);
  }

  useEffect(() => {
    if (!suggested) return;
    let active = true;
    listWhatsAppTemplates(storeId)
      .then((data) => { if (active) applyTemplates(data.items); })
      .catch(() => { if (active) setError(t("flowWaTemplateLoadError")); })
      .finally(() => { if (active) setLoadingTemplates(false); });
    return () => { active = false; };
    // Load once per model/store; applyTemplates reads the latest selection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storeId, model.id]);

  async function syncTemplates() {
    setError("");
    setSyncing(true);
    try {
      await api.post(`/api/stores/${storeId}/whatsapp/templates/sync`);
      applyTemplates((await listWhatsAppTemplates(storeId)).items);
    } catch {
      setError(t("autoModelSyncError"));
    } finally {
      setSyncing(false);
    }
  }

  function selectTemplate(id: number | null, source = templates) {
    setTemplateId(id);
    const template = source.find((item) => item.id === id);
    setMapping(template ? suggestedMapping(suggested?.variables, templateParameterCount(template)) : []);
  }

  async function copySuggestion() {
    if (!suggested) return;
    try {
      await navigator.clipboard.writeText(suggestedTemplateClipboard(suggested));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  async function submit() {
    // Same explicit gate as the editor: a live flow messages real customers.
    if (activate && !window.confirm(t("flowEditorConfirmActivate"))) return;
    setSubmitting(true);
    setError("");
    try {
      const payload = buildModelSetupPayload(
        { name, whatsappTemplateId: templateId, mapping, messageMode, activate },
        model.name,
      );
      const response = await api.post<unknown>(
        `/api/stores/${storeId}/automation-flow-templates/${encodeURIComponent(model.id)}`,
        payload,
      );
      const activated = Boolean((response.data as { activated?: boolean })?.activated);
      onCreated(createdTemplateFlowId(response.data), activated);
    } catch (cause) {
      setError(t(modelSetupErrorKey(cause)));
    } finally {
      setSubmitting(false);
    }
  }

  const triggerLabel = model.trigger_type ? t(`flowTriggerType_${model.trigger_type}`) : "";

  return (
    <div className="management-modal-backdrop" onMouseDown={() => !submitting && onClose()}>
      <div
        className="management-modal automation-model-setup"
        role="dialog"
        aria-modal="true"
        aria-labelledby="automation-model-setup-title"
        onMouseDown={(event) => event.stopPropagation()}
        style={{ maxWidth: 640, width: "100%", maxHeight: "90vh", overflowY: "auto" }}
      >
        <header className="management-modal-header">
          <div>
            <span className="eyebrow">{t("autoModelEyebrow")}</span>
            <h2 id="automation-model-setup-title">{model.name}</h2>
            <p style={{ margin: "4px 0 0" }}>{model.description}</p>
          </div>
          <button className="icon-button" onClick={onClose} disabled={submitting} aria-label={t("autoModelClose")}>
            <X size={18} />
          </button>
        </header>

        <div className="management-form">
          <section className="management-form-section">
            <strong>1. {t("autoModelWhenTitle")}</strong>
            <p style={{ margin: "6px 0" }}>
              <Zap size={14} style={{ verticalAlign: "-2px", marginRight: 6 }} />
              {model.trigger_mode === "automatic"
                ? `${t("autoModelAutomatic")}: ${triggerLabel}`
                : t("autoModelManual")}
            </p>
            {steps.length > 0 && (
              <ol style={{ margin: "4px 0 0", paddingLeft: 20 }}>
                {steps.map((step, index) => <li key={`${step}-${index}`}>{t(`autoTemplateStep_${step}`)}</li>)}
              </ol>
            )}
          </section>

          {suggested && (
            <section className="management-form-section">
              <strong>2. {t("autoModelWhatsAppTitle")}</strong>
              <p style={{ margin: "6px 0" }}>{t("autoModelWhatsAppHelp")}</p>

              <label>
                <span>{t("flowWaTemplate")}</span>
                <select
                  value={templateId ?? ""}
                  onChange={(event) => selectTemplate(event.target.value ? Number(event.target.value) : null)}
                  disabled={loadingTemplates || submitting}
                >
                  <option value="">
                    {loadingTemplates ? t("flowWaTemplateLoading") : t("autoModelNoTemplateYet")}
                  </option>
                  {approved.map((template) => (
                    <option key={template.id} value={template.id}>
                      {template.provider_template_name} · {template.language_code}
                    </option>
                  ))}
                </select>
              </label>

              {selected && (
                <>
                  {mapping.map((variable, index) => (
                    <label key={`param-${index}`}>
                      <span>{`${t("flowWaTemplateParam")} {{${index + 1}}}`}</span>
                      <select
                        value={variable}
                        onChange={(event) => setMapping((current) => current.map((item, i) => (
                          i === index ? event.target.value : item
                        )))}
                        disabled={submitting}
                      >
                        {FLOW_TEMPLATE_VARIABLES.map((item) => <option key={item} value={item}>{`{{${item}}}`}</option>)}
                      </select>
                    </label>
                  ))}
                  {templateBodyText(selected) && (
                    <p className="flow-field-hint" style={{ whiteSpace: "pre-wrap" }}>
                      <strong>{t("flowWaTemplatePreview")}: </strong>
                      {previewTemplateBody(templateBodyText(selected), mapping)}
                    </p>
                  )}
                  <label>
                    <span>{t("autoModelSendMode")}</span>
                    <select
                      value={messageMode}
                      onChange={(event) => setMessageMode(event.target.value as "auto" | "template")}
                      disabled={submitting}
                    >
                      <option value="auto">{t("autoModelModeAuto")}</option>
                      <option value="template">{t("autoModelModeTemplate")}</option>
                    </select>
                  </label>
                </>
              )}

              {!selected && !loadingTemplates && (
                <div className="flow-field-hint" style={{ border: "1px dashed var(--border-color, #cbd5e1)", borderRadius: 10, padding: 12 }}>
                  <p style={{ margin: 0 }}>
                    <AlertTriangle size={14} style={{ verticalAlign: "-2px", marginRight: 6 }} />
                    {t("autoModelWithoutTemplateWarning")}
                  </p>
                  <p style={{ margin: "10px 0 4px" }}><strong>{t("autoModelSuggestedTitle")}</strong></p>
                  <p style={{ margin: 0 }}>
                    <code>{suggested.name}</code> · {suggested.category} · {suggested.language}
                  </p>
                  <p style={{ margin: "6px 0", whiteSpace: "pre-wrap" }}>{suggested.body}</p>
                  <ul style={{ margin: "0 0 8px", paddingLeft: 18 }}>
                    {suggested.variables.map((variable, index) => (
                      <li key={variable + index}><code>{`{{${index + 1}}}`}</code> = <code>{variable}</code></li>
                    ))}
                  </ul>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <button type="button" className="secondary-button" onClick={() => void copySuggestion()}>
                      {copied ? <Check size={14} /> : <Copy size={14} />} {copied ? t("autoModelCopied") : t("autoModelCopy")}
                    </button>
                    <a className="secondary-button" href={META_TEMPLATES_URL} target="_blank" rel="noopener noreferrer">
                      <ExternalLink size={14} /> {t("autoModelOpenMeta")}
                    </a>
                    <button type="button" className="secondary-button" onClick={() => void syncTemplates()} disabled={syncing}>
                      {syncing ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />} {t("autoModelSync")}
                    </button>
                  </div>
                </div>
              )}
            </section>
          )}

          <section className="management-form-section">
            <strong>{suggested ? "3" : "2"}. {t("autoModelFinishTitle")}</strong>
            <label>
              <span>{t("autoModelFlowName")}</span>
              <input value={name} maxLength={255} onChange={(event) => setName(event.target.value)} disabled={submitting} />
            </label>
            <label className="toggle-row">
              <input type="checkbox" checked={activate} onChange={(event) => setActivate(event.target.checked)} disabled={submitting} />
              <span>{t("autoModelActivateNow")}</span>
            </label>
            <small className="flow-field-hint">
              {activate ? t("autoModelActivateHelp") : t("autoModelDraftHelp")}
            </small>
          </section>

          {error && (
            <div className="stores-alert error" role="alert">
              <AlertTriangle size={15} /> {error}
            </div>
          )}
        </div>

        <footer className="management-modal-actions">
          <button className="secondary-button" onClick={onClose} disabled={submitting}>{t("autoModelCancel")}</button>
          <button className="primary-button" onClick={() => void submit()} disabled={submitting || !name.trim()}>
            {submitting && <Loader2 className="spin" size={16} />}
            {activate ? t("autoModelCreateAndActivate") : t("autoModelCreateDraft")}
          </button>
        </footer>
      </div>
    </div>
  );
}
