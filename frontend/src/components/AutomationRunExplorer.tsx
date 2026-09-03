import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, RefreshCw, RotateCcw } from "lucide-react";
import {
  listAutomationCampaigns,
  listCampaignRuns,
  getCampaignRunDetail,
  listRunRecipients,
  getRunRecipientDetail,
  retryRunRecipient,
  type AutomationCampaign,
  type AutomationRun,
  type AutomationRecipientRow,
  type AutomationRecipientDetail,
} from "../services/automations";

interface Props {
  storeId: number;
  canWrite: boolean;
}

const TERMINAL_RUN = new Set(["completed", "partial", "failed", "simulated"]);
const RETRYABLE = new Set(["failed", "skipped"]);
const NON_RETRYABLE_SKIP = new Set(["outside_service_window", "cooldown", "no_phone", "invalid_template_data", "send_window", "rate_limited"]);

export default function AutomationRunExplorer({ storeId, canWrite }: Props) {
  const { t } = useTranslation();
  const [campaigns, setCampaigns] = useState<AutomationCampaign[]>([]);
  const [selectedCampaignId, setSelectedCampaignId] = useState<number | null>(null);
  const [runs, setRuns] = useState<AutomationRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<AutomationRun | null>(null);
  const [recipients, setRecipients] = useState<AutomationRecipientRow[]>([]);
  const [recipientPage, setRecipientPage] = useState({ page: 1, total: 1, pageSize: 25 });
  const [recipientFilters, setRecipientFilters] = useState({ status: "", reason: "", search: "" });
  const [selectedRecipient, setSelectedRecipient] = useState<AutomationRecipientDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const pollRef = useRef<number | undefined>(undefined);

  const loadCampaigns = useCallback(async () => {
    try { setCampaigns((await listAutomationCampaigns(storeId)).items); } catch { setError(t("autoCampaignLoadError")); }
  }, [storeId, t]);

  useEffect(() => { void loadCampaigns(); }, [loadCampaigns]);

  const loadRuns = useCallback(async (campaignId: number) => {
    setLoading(true); setError("");
    try { setRuns((await listCampaignRuns(storeId, campaignId)).items); } catch { setError(t("autoRunLoadError")); } finally { setLoading(false); }
  }, [storeId, t]);

  useEffect(() => { if (selectedCampaignId) void loadRuns(selectedCampaignId); }, [selectedCampaignId, loadRuns]);

  const loadRunDetail = useCallback(async (campaignId: number, runId: number) => {
    setLoading(true); setError("");
    try {
      const detail = await getCampaignRunDetail(storeId, campaignId, runId);
      setSelectedRun(detail);
      setRecipientFilters({ status: "", reason: "", search: "" });
      setRecipientPage((prev) => ({ ...prev, page: 1 }));
    } catch { setError(t("autoRunLoadError")); } finally { setLoading(false); }
  }, [storeId, t]);

  const loadRecipients = useCallback(async (campaignId: number, runId: number, page: number, filters: { status: string; reason: string; search: string }, pageSize: number) => {
    setLoading(true); setError("");
    try {
      const result = await listRunRecipients(storeId, campaignId, runId, { status: filters.status || undefined, reason: filters.reason || undefined, search: filters.search || undefined, page, page_size: pageSize });
      setRecipients(result.items);
      setRecipientPage({ page: result.page, total: result.total_pages, pageSize });
    } catch { setError(t("autoRecipientLoadError")); } finally { setLoading(false); }
  }, [storeId, t]);

  useEffect(() => {
    if (selectedRun && selectedCampaignId) void loadRecipients(selectedCampaignId, selectedRun.id, recipientPage.page, recipientFilters, recipientPage.pageSize);
  }, [selectedRun?.id, recipientPage.page, recipientFilters.status, recipientFilters.reason, recipientFilters.search]);

  useEffect(() => {
    if (selectedRun && !TERMINAL_RUN.has(selectedRun.status)) {
      pollRef.current = window.setInterval(() => { if (selectedCampaignId && selectedRun) void loadRunDetail(selectedCampaignId, selectedRun.id); }, 7000);
    }
    return () => { if (pollRef.current) window.clearInterval(pollRef.current); };
  }, [selectedRun?.status, selectedCampaignId]);

  const openRecipient = async (campaignId: number, runId: number, recipientId: number) => {
    setLoading(true); setError("");
    try { setSelectedRecipient(await getRunRecipientDetail(storeId, campaignId, runId, recipientId)); } catch { setError(t("autoRecipientLoadError")); } finally { setLoading(false); }
  };

  const handleRetry = async (campaignId: number, runId: number, recipientId: number) => {
    if (!window.confirm(t("autoRetryConfirm"))) return;
    setLoading(true); setError("");
    try { await retryRunRecipient(storeId, campaignId, runId, recipientId); setSelectedRecipient(null); void loadRecipients(campaignId, runId, recipientPage.page, recipientFilters, recipientPage.pageSize); void loadRunDetail(campaignId, runId); } catch (err: any) { setError(err?.response?.data?.detail || t("autoRetryFailed")); } finally { setLoading(false); }
  };

  const formatDate = (iso: string | null) => iso ? new Date(iso).toLocaleString() : "-";

  const maskPhone = (phone: string | null) => {
    if (!phone) return "-";
    if (phone.length <= 4) return phone;
    return phone.slice(0, 3) + "*".repeat(Math.max(0, phone.length - 5)) + phone.slice(-2);
  };

  if (!selectedCampaignId) {
    return <div className="automation-run-explorer">
      <h3>{t("autoRunExplorer")}</h3>
      <p>{t("autoSelectCampaign")}</p>
      <div className="automation-run-campaign-grid">
        {campaigns.filter((c) => c.status !== "draft").map((campaign) => <button key={campaign.id} className="automation-run-campaign-card" onClick={() => setSelectedCampaignId(campaign.id)}><strong>{campaign.name}</strong><span>{t(`autoStatus_${campaign.status}`)} · {campaign.schedule_type}</span></button>)}
        {!campaigns.filter((c) => c.status !== "draft").length && <p>{t("autoNoActiveCampaigns")}</p>}
      </div>
    </div>;
  }

  if (selectedRun) {
    const total = selectedRun.total_recipients ?? (selectedRun.sent_count + selectedRun.failed_count + selectedRun.excluded_count + (selectedRun.pending_count ?? 0));
    const processed = total - (selectedRun.pending_count ?? 0);
    const pct = total > 0 ? Math.round((processed / total) * 100) : 0;
    const campaign = campaigns.find((c) => c.id === selectedCampaignId);
    return <div className="automation-run-explorer">
      <button className="icon-button" onClick={() => { setSelectedRun(null); setRecipients([]); setSelectedRecipient(null); }}><ArrowLeft size={16} /> {t("autoBackToRuns")}</button>
      <div className="automation-run-detail-header">
        <div><h3>{campaign?.name || t("autoRunLabel")}</h3><span className={`automation-run-status-badge ${selectedRun.status}`}>{t(`autoRunStatus_${selectedRun.status}`)}</span></div>
        <div className="automation-run-detail-meta"><span>{t("autoRunScheduled")}: {formatDate(selectedRun.scheduled_for)}</span><span>{t("autoRunStarted")}: {formatDate(selectedRun.started_at)}</span><span>{t("autoRunFinished")}: {formatDate(selectedRun.completed_at)}</span><span>{t("autoRunTotal")}: {total}</span></div>
      </div>
      <div className="automation-run-counter-grid">
        <div className="automation-run-counter success"><span className="automation-run-counter-value">{selectedRun.sent_count}</span><span className="automation-run-counter-label">{t("autoRunSent")}</span></div>
        <div className="automation-run-counter danger"><span className="automation-run-counter-value">{selectedRun.failed_count}</span><span className="automation-run-counter-label">{t("autoRunFailed")}</span></div>
        <div className="automation-run-counter muted"><span className="automation-run-counter-value">{selectedRun.excluded_count}</span><span className="automation-run-counter-label">{t("autoRunSkipped")}</span></div>
        <div className="automation-run-counter warning"><span className="automation-run-counter-value">{selectedRun.pending_count ?? 0}</span><span className="automation-run-counter-label">{t("autoRunPending")}</span></div>
        <div className="automation-run-counter"><span className="automation-run-counter-value">{pct}%</span><span className="automation-run-counter-label">{t("autoRunProgress")}</span></div>
      </div>
      {!TERMINAL_RUN.has(selectedRun.status) && <p className="automation-run-live-notice">{t("autoRunLive")}</p>}
      {selectedRecipient && <div className="modal-backdrop" onClick={() => setSelectedRecipient(null)}><div className="modal automation-recipient-detail-modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <h2>{t("autoRecipientDetail")}</h2>
        <div className="automation-recipient-detail-grid">
          <div><strong>{t("autoRecipientCustomer")}</strong><p>{selectedRecipient.customer_name} ({maskPhone(selectedRecipient.customer_phone)})</p></div>
          <div><strong>{t("autoRecipientStatus")}</strong><span className={`automation-recipient-status-badge ${selectedRecipient.status}`}>{t(`autoRecipientStatus_${selectedRecipient.status}`)}</span></div>
          <div><strong>{t("autoRecipientAttempts")}</strong><p>{selectedRecipient.attempt_count}</p></div>
          <div><strong>{t("autoRecipientSentAt")}</strong><p>{formatDate(selectedRecipient.sent_at)}</p></div>
          {selectedRecipient.provider_message_id && <div><strong>{t("autoRecipientProviderId")}</strong><p className="automation-mono-text">{selectedRecipient.provider_message_id}</p></div>}
          {selectedRecipient.error_code && <div><strong>{t("autoRecipientError")}</strong><p>{t(`autoReason_${selectedRecipient.error_code}`)}</p></div>}
          {selectedRecipient.exclusion_reason && <div><strong>{t("autoRecipientReason")}</strong><p>{t(`autoReason_${selectedRecipient.exclusion_reason}`)}</p></div>}
          {selectedRecipient.rendered_message && <div className="automation-recipient-message-preview"><strong>{t("autoRecipientMessage")}</strong><p>{selectedRecipient.rendered_message}</p></div>}
        </div>
        <div className="automation-attempt-timeline">
          <h4>{t("autoAttemptTimeline")}</h4>
          {!selectedRecipient.attempts.length && <p>{t("autoNoAttempts")}</p>}
          {selectedRecipient.attempts.map((a) => <div key={a.id} className={`automation-attempt-entry ${a.status}`}>
            <div className="automation-attempt-header"><span className="automation-attempt-number">{t("autoAttemptNumber", { n: a.attempt_number })}</span><span className={`automation-recipient-status-badge ${a.status}`}>{t(`autoRecipientStatus_${a.status}`)}</span></div>
            <div className="automation-attempt-meta"><span>{t("autoAttemptStarted")}: {formatDate(a.started_at)}</span><span>{t("autoAttemptFinished")}: {formatDate(a.finished_at)}</span></div>
            {a.error_code && <p className="automation-attempt-error">{t(`autoReason_${a.error_code}`)}</p>}
            {a.provider_message_id && <p className="automation-mono-text">{a.provider_message_id}</p>}
          </div>)}
        </div>
        {canWrite && RETRYABLE.has(selectedRecipient.status) && !(selectedRecipient.status === "skipped" && NON_RETRYABLE_SKIP.has(selectedRecipient.exclusion_reason || "")) && <button className="primary-button" disabled={loading} onClick={() => void handleRetry(selectedCampaignId, selectedRun.id, selectedRecipient.id)}><RotateCcw size={14} /> {t("autoRetryRecipient")}</button>}
        {selectedRecipient.status === "ambiguous" && <p className="automation-ambiguous-notice">{t("autoAmbiguousNoRetry")}</p>}
        <button className="secondary-button" onClick={() => setSelectedRecipient(null)}>{t("autoClose")}</button>
      </div></div>}
      <div className="automation-recipient-filters">
        <input placeholder={t("autoSearchCustomers")} value={recipientFilters.search} onChange={(e) => { setRecipientFilters({ ...recipientFilters, search: e.target.value }); setRecipientPage((p) => ({ ...p, page: 1 })); }} />
        <select value={recipientFilters.status} onChange={(e) => { setRecipientFilters({ ...recipientFilters, status: e.target.value }); setRecipientPage((p) => ({ ...p, page: 1 })); }}><option value="">{t("autoAllStatuses")}</option>{["queued", "processing", "sending", "retry_wait", "sent", "failed", "skipped", "ambiguous"].map((s) => <option key={s} value={s}>{t(`autoRecipientStatus_${s}`)}</option>)}</select>
        <select value={recipientFilters.reason} onChange={(e) => { setRecipientFilters({ ...recipientFilters, reason: e.target.value }); setRecipientPage((p) => ({ ...p, page: 1 })); }}><option value="">{t("autoAllReasons")}</option>{["outside_service_window", "template_required", "template_not_approved", "invalid_template_data", "connection_inactive", "cooldown", "no_phone", "rate_limited"].map((r) => <option key={r} value={r}>{t(`autoReason_${r}`)}</option>)}</select>
      </div>
      {loading && !selectedRecipient && <p>{t("autoLoading")}</p>}
      {error && <p className="automation-error-text">{error}</p>}
      <div className="automation-recipient-table-wrap">
        <table className="automation-recipient-table">
          <thead><tr><th>{t("autoRecipientCustomer")}</th><th>{t("autoRecipientStatus")}</th><th>{t("autoRecipientAttempts")}</th><th>{t("autoRecipientSentAt")}</th><th>{t("autoRecipientReason")}</th><th>{t("autoRecipientProviderId")}</th></tr></thead>
          <tbody>{recipients.map((r) => <tr key={r.id} className="automation-recipient-row" onClick={() => void openRecipient(selectedCampaignId, selectedRun.id, r.id)}>
            <td><strong>{r.customer_name}</strong><small>{maskPhone(r.customer_phone)}</small></td>
            <td><span className={`automation-recipient-status-badge ${r.status}`}>{t(`autoRecipientStatus_${r.status}`)}</span></td>
            <td>{r.attempt_count}</td>
            <td>{formatDate(r.sent_at)}</td>
            <td>{r.exclusion_reason ? t(`autoReason_${r.exclusion_reason}`) : "-"}</td>
            <td className="automation-mono-text">{r.provider_message_id || "-"}</td>
          </tr>)}</tbody>
        </table>
      </div>
      {!recipients.length && !loading && <p>{t("autoNoRecipients")}</p>}
      <div className="automation-recipient-pagination">
        <button className="secondary-button" disabled={recipientPage.page <= 1} onClick={() => setRecipientPage((p) => ({ ...p, page: p.page - 1 }))}>{t("autoPrevious")}</button>
        <span>{recipientPage.page} / {recipientPage.total}</span>
        <select value={recipientPage.pageSize} onChange={(e) => { const size = Number(e.target.value); setRecipientPage((p) => ({ ...p, pageSize: size, page: 1 })); }}>{[25, 50, 100].map((s) => <option key={s} value={s}>{s}</option>)}</select>
        <button className="secondary-button" disabled={recipientPage.page >= recipientPage.total} onClick={() => setRecipientPage((p) => ({ ...p, page: p.page + 1 }))}>{t("autoNext")}</button>
        <button className="secondary-button" onClick={() => { void loadRunDetail(selectedCampaignId, selectedRun.id); void loadRecipients(selectedCampaignId, selectedRun.id, recipientPage.page, recipientFilters, recipientPage.pageSize); }}><RefreshCw size={14} /></button>
      </div>
    </div>;
  }

  return <div className="automation-run-explorer">
    <button className="icon-button" onClick={() => setSelectedCampaignId(null)}><ArrowLeft size={16} /> {t("autoBackToCampaigns")}</button>
    <h3>{campaigns.find((c) => c.id === selectedCampaignId)?.name} — {t("autoRuns")}</h3>
    {loading && <p>{t("autoLoading")}</p>}
    {error && <p className="automation-error-text">{error}</p>}
    {!runs.length && !loading && <p>{t("autoNoRuns")}</p>}
    <div className="automation-runs-table-wrap">
      <table className="automation-runs-table">
        <thead><tr><th>{t("autoRunLabel")}</th><th>{t("autoRunStatus")}</th><th>{t("autoRunScheduled")}</th><th>{t("autoRunStarted")}</th><th>{t("autoRunFinished")}</th><th>{t("autoRunMatched")}</th><th>{t("autoRunSent")}</th><th>{t("autoRunFailed")}</th><th>{t("autoRunSkipped")}</th></tr></thead>
        <tbody>{runs.map((run) => <tr key={run.id} className="automation-run-row" onClick={() => void loadRunDetail(selectedCampaignId, run.id)}>
          <td>#{run.id}</td>
          <td><span className={`automation-run-status-badge ${run.status}`}>{t(`autoRunStatus_${run.status}`)}</span></td>
          <td>{formatDate(run.scheduled_for)}</td>
          <td>{formatDate(run.started_at)}</td>
          <td>{formatDate(run.completed_at)}</td>
          <td>{run.matched_count}</td>
          <td>{run.sent_count}</td>
          <td>{run.failed_count}</td>
          <td>{run.excluded_count}</td>
        </tr>)}</tbody>
      </table>
    </div>
  </div>;
}
