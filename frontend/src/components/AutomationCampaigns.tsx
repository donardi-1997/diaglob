import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy, Plus, Send } from "lucide-react";
import {
  createAutomationCampaign,
  duplicateAutomationCampaign,
  listAutomationCampaigns,
  previewAutomationAudience,
  simulateAutomationCampaign,
  listWhatsAppTemplates,
  type AutomationCampaign,
  type AutomationCampaignPayload,
  type AudiencePreview,
  type CampaignSimulation,
  type WhatsAppMessageTemplate,
} from "../services/automations";
import AutomationAudienceSelector from "./AutomationAudienceSelector";

interface Props { canWrite: boolean; storeId: number; }

const initial = (): AutomationCampaignPayload => ({
  name: "", automation_type: "custom", status: "draft", audience_type: "dynamic",
  audience_filters: {}, member_ids: [], schedule_type: "once",
  schedule_config: { starts_at: new Date().toISOString() }, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  cooldown_days: 7, channel: "whatsapp", message_template: "Hola {{customer.name}},", message_mode: "auto", template_variables: { body: ["customer.name", "store.name"] },
});

export default function AutomationCampaigns({ canWrite, storeId }: Props) {
  const { t } = useTranslation();
  const [items, setItems] = useState<AutomationCampaign[]>([]);
  const [form, setForm] = useState(initial);
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(1);
  const [preview, setPreview] = useState<AudiencePreview | null>(null);
  const [simulation, setSimulation] = useState<CampaignSimulation | null>(null);
  const [error, setError] = useState("");
  const [templates, setTemplates] = useState<WhatsAppMessageTemplate[]>([]);

  const load = async () => { try { setItems((await listAutomationCampaigns(storeId)).items); } catch { setError(t("autoCampaignLoadError")); } };
  useEffect(() => { void load(); }, [storeId]);
  useEffect(() => { void listWhatsAppTemplates(storeId).then((data) => setTemplates(data.items)).catch(() => setTemplates([])); }, [storeId]);
  const updateFilters = (key: string, value: unknown) => setForm({ ...form, audience_filters: { ...form.audience_filters, [key]: value } });
  const previewAudience = async () => { try { setPreview(await previewAutomationAudience(storeId, form)); } catch { setError(t("autoPreviewError")); } };
  const save = async (status: "draft" | "active") => { try { const created = await createAutomationCampaign(storeId, { ...form, status }); setOpen(false); setSimulation(await simulateAutomationCampaign(storeId, created.id)); await load(); } catch { setError(t("autoCampaignSaveError")); } };

  return <section className="automation-campaigns">
    <div className="automations-toolbar"><div><h2>{t("autoCampaigns")}</h2><p>{t("autoCampaignsDescription")}</p></div>{canWrite && <button className="primary-button" onClick={() => { setForm(initial()); setStep(1); setPreview(null); setOpen(true); }}><Plus size={16} />{t("autoNewCampaign")}</button>}</div>
    {error && <p className="automation-error-text">{error}</p>}
    <div className="automation-campaign-stats"><span>{t("autoActive")}: {items.filter((item) => item.status === "active").length}</span><span>{t("autoDraft")}: {items.filter((item) => item.status === "draft").length}</span></div>
    {!items.length ? <div className="empty-state"><p>{t("autoNoCampaigns")}</p></div> : <div className="automations-grid">{items.map((item) => <article className="automation-card" key={item.id}><div className="automation-card-header"><div className="automation-card-info"><h3>{item.name}</h3><p>{item.audience_type === "fixed" ? t("autoFixedAudience") : t("autoDynamicAudience")} · {item.channel}</p></div><span className="automation-trigger-badge">{t(`autoStatus_${item.status}`)}</span></div><div className="automation-card-meta"><span>{t(`autoSchedule_${item.schedule_type}`)}</span><span>{t("autoCooldown")}: {item.cooldown_days}d</span></div>{canWrite && <div className="automation-card-actions"><button className="icon-button" title={t("autoDuplicate")} onClick={async () => { await duplicateAutomationCampaign(storeId, item.id); await load(); }}><Copy size={16} /></button><button className="icon-button" title={t("autoSimulate")} onClick={async () => setSimulation(await simulateAutomationCampaign(storeId, item.id))}><Send size={16} /></button></div>}</article>)}</div>}
    {open && <div className="modal-backdrop"><div className="modal automation-wizard" role="dialog" aria-modal="true"><h2>{t("autoNewCampaign")}</h2><div className="wizard-steps">{[1, 2, 3, 4].map((number) => <button key={number} className={step === number ? "active" : ""} onClick={() => setStep(number)}>{number}. {t(`autoWizard${number}`)}</button>)}</div>
      {step === 1 && <div className="automation-wizard-body"><label>{t("autoFormName")}<input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label><label>{t("autoAudienceType")}<select value={form.audience_type} onChange={(event) => setForm({ ...form, audience_type: event.target.value as "dynamic" | "fixed", member_ids: [], selected_customer_ids: [], excluded_customer_ids: [], selection_mode: "explicit" })}><option value="dynamic">{t("autoDynamicAudience")}</option><option value="fixed">{t("autoFixedAudience")}</option></select></label>{form.audience_type === "dynamic" ? <><label>{t("autoSegment")}<select onChange={(event) => updateFilters("segment", event.target.value ? [event.target.value] : [])}><option value="">-</option>{["new", "interested", "high_intent", "buyer", "repeat_buyer", "vip", "inactive"].map((value) => <option key={value} value={value}>{value}</option>)}</select></label><label>{t("autoHealth")}<select onChange={(event) => updateFilters("health", event.target.value ? [event.target.value] : [])}><option value="">-</option><option value="active">active</option><option value="at_risk">at_risk</option><option value="inactive">inactive</option></select></label></> : <AutomationAudienceSelector storeId={storeId} value={form} onChange={(selection) => setForm({ ...form, ...selection })} />}<button className="secondary-button" onClick={() => void previewAudience()}>{t("autoPreview")}</button>{preview && <p>{t("autoEligible")}: {preview.eligible_count}</p>}</div>}
      {step === 2 && <div className="automation-wizard-body"><label>{t("autoSchedule")}<select value={form.schedule_type} onChange={(event) => setForm({ ...form, schedule_type: event.target.value, schedule_config: event.target.value === "once" ? { starts_at: new Date().toISOString() } : {} })}>{["once", "daily", "weekly", "every_n_days"].map((value) => <option key={value} value={value}>{t(`autoSchedule_${value}`)}</option>)}</select></label><label>{t("autoTimezone")}<input value={form.timezone} onChange={(event) => setForm({ ...form, timezone: event.target.value })} /></label><label>{t("autoCooldown")}<input type="number" min="0" value={form.cooldown_days} onChange={(event) => setForm({ ...form, cooldown_days: Number(event.target.value) })} /></label></div>}
      {step === 3 && <div className="automation-wizard-body"><label>{t("autoMessageMode")}<select value={form.message_mode} onChange={(event) => setForm({ ...form, message_mode: event.target.value as "auto" | "free_form" | "template" })}><option value="auto">{t("autoModeAuto")}</option><option value="free_form">{t("autoModeFreeForm")}</option><option value="template">{t("autoModeTemplate")}</option></select></label>{form.message_mode !== "free_form" && <label>{t("autoApprovedTemplate")}<select value={form.whatsapp_template_id ?? ""} onChange={(event) => setForm({ ...form, whatsapp_template_id: event.target.value ? Number(event.target.value) : undefined })}><option value="">{t("autoSelectTemplate")}</option>{templates.map((template) => <option disabled={template.status !== "approved"} key={template.id} value={template.id}>{template.provider_template_name} · {template.language_code} · {template.status}</option>)}</select></label>}<label>{t("autoMessage")}<textarea value={form.message_template} onChange={(event) => setForm({ ...form, message_template: event.target.value })} /></label><p>{form.message_mode === "auto" ? t("autoAutoModeHelp") : form.message_mode === "free_form" ? t("autoFreeFormWarning") : t("autoTemplateModeHelp")}</p><p>{t("autoVariables")}: {"{{customer.name}}, {{store.name}}, {{customer.segment}}, {{customer.health}}"}</p></div>}
      {step === 4 && <div className="automation-wizard-body"><p>{t("autoReviewCampaign", { audience: preview?.eligible_count ?? 0, schedule: form.schedule_type })}</p><p className="automation-message-preview">{form.message_template}</p><button className="secondary-button" onClick={() => void save("draft")}>{t("autoSaveDraft")}</button><button className="primary-button" onClick={() => void save("active")}>{t("autoActivate")}</button></div>}
      <button className="secondary-button" onClick={() => setOpen(false)}>{t("autoCancel")}</button></div></div>}
    {simulation && <div className="modal-backdrop"><div className="modal" role="dialog" aria-modal="true"><h2>{t("autoSimulation")}</h2><p>{t("autoMatched")}: {simulation.matched}</p><p>{t("autoWouldSend")}: {simulation.would_send}</p><p>{t("autoExcluded")}: {simulation.excluded}</p><button className="secondary-button" onClick={() => setSimulation(null)}>{t("autoClose")}</button></div></div>}
  </section>;
}
