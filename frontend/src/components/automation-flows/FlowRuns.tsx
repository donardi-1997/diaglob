import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, RotateCcw } from "lucide-react";
import {
  listFlowRuns,
  getFlowRun,
  listFlowRunRecipients,
  getFlowRecipientDetail,
  retryFlowRecipient,
  type AutomationFlowRun,
  type AutomationFlowRecipient,
  type AutomationFlowRecipientDetail,
} from "../../services/automationFlows";

interface Props {
  storeId: number;
  flowId: number;
  onBack: () => void;
  t: (key: string) => string;
}

const STATUS_STYLES: Record<string, string> = {
  pending: "rgba(255,255,255,0.06)",
  running: "rgba(74,158,255,0.12)",
  completed: "rgba(34,197,94,0.12)",
  partial: "rgba(230,168,23,0.12)",
  failed: "rgba(239,68,68,0.12)",
  sent: "rgba(34,197,94,0.12)",
  queued: "rgba(255,255,255,0.06)",
  processing: "rgba(74,158,255,0.12)",
  retry_wait: "rgba(230,168,23,0.12)",
  skipped: "rgba(255,255,255,0.04)",
  ambiguous: "rgba(230,168,23,0.12)",
};

type SubView = "runs" | "recipients" | "detail";

export default function FlowRuns({ storeId, flowId, onBack, t }: Props) {
  const [subView, setSubView] = useState<SubView>("runs");
  const [runs, setRuns] = useState<AutomationFlowRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<AutomationFlowRun | null>(null);
  const [recipients, setRecipients] = useState<AutomationFlowRecipient[]>([]);
  const [selectedRecipient, setSelectedRecipient] = useState<AutomationFlowRecipientDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const loadRuns = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setRuns(await listFlowRuns(storeId, flowId));
    } catch {
      setError(t("flowRunsLoadError"));
    } finally {
      setLoading(false);
    }
  }, [storeId, flowId, t]);

  useEffect(() => {
    if (subView === "runs") void loadRuns();
  }, [subView, loadRuns]);

  const loadRunDetail = useCallback(
    async (run: AutomationFlowRun) => {
      setLoading(true);
      setError("");
      try {
        const detail = await getFlowRun(storeId, flowId, run.id);
        setSelectedRun(detail);
        setSubView("recipients");
      } catch {
        setError(t("flowRunsLoadError"));
      } finally {
        setLoading(false);
      }
    },
    [storeId, flowId, t]
  );

  const loadRecipients = useCallback(
    async (runId: number) => {
      setLoading(true);
      setError("");
      try {
        const result = await listFlowRunRecipients(storeId, flowId, runId);
        setRecipients(result.items);
      } catch {
        setError(t("flowRunsLoadError"));
      } finally {
        setLoading(false);
      }
    },
    [storeId, flowId, t]
  );

  useEffect(() => {
    if (subView === "recipients" && selectedRun) void loadRecipients(selectedRun.id);
  }, [subView, selectedRun?.id, loadRecipients]);

  const loadRecipientDetail = useCallback(
    async (runId: number, recipientId: number) => {
      setLoading(true);
      setError("");
      try {
        setSelectedRecipient(await getFlowRecipientDetail(storeId, flowId, runId, recipientId));
        setSubView("detail");
      } catch {
        setError(t("flowRunsLoadError"));
      } finally {
        setLoading(false);
      }
    },
    [storeId, flowId, t]
  );

  const handleRetry = useCallback(
    async (runId: number, recipientId: number) => {
      setLoading(true);
      setError("");
      try {
        await retryFlowRecipient(storeId, flowId, runId, recipientId);
        setSelectedRecipient(null);
        setSubView("recipients");
        void loadRecipients(runId);
      } catch {
        setError(t("flowRetryError"));
      } finally {
        setLoading(false);
      }
    },
    [storeId, flowId, loadRecipients, t]
  );

  const formatDate = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : "-");

  const breadcrumb = (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
      <button
        className="icon-button"
        onClick={() => {
          if (subView === "detail") {
            setSelectedRecipient(null);
            setSubView("recipients");
          } else if (subView === "recipients") {
            setSelectedRun(null);
            setSubView("runs");
          } else {
            onBack();
          }
        }}
        style={{
          width: 34,
          height: 34,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          border: "1px solid var(--border)",
          borderRadius: 8,
          background: "transparent",
          color: "var(--text-muted)",
          cursor: "pointer",
        }}
      >
        <ArrowLeft size={14} />
      </button>
      <span style={{ fontSize: 13, color: "var(--text-muted)" }}>
        {subView === "runs" && t("flowRunsBreadcrumbRuns")}
        {subView === "recipients" && (
          <>
            {t("flowRunsBreadcrumbRuns")} / {t("flowRunsBreadcrumbRecipients")}
          </>
        )}
        {subView === "detail" && (
          <>
            {t("flowRunsBreadcrumbRuns")} / {t("flowRunsBreadcrumbRecipients")} / {t("flowRunsBreadcrumbDetail")}
          </>
        )}
      </span>
    </div>
  );

  if (loading && !runs.length && subView === "runs") {
    return (
      <section className="flow-runs-section">
        {breadcrumb}
        <p>{t("flowLoading")}</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="flow-runs-section">
        {breadcrumb}
        <p style={{ color: "#ef4444" }}>{error}</p>
      </section>
    );
  }

  if (subView === "detail" && selectedRecipient) {
    return (
      <section className="flow-runs-section">
        {breadcrumb}
        <div className="flow-recipient-detail" style={{ padding: "0 0 20px" }}>
          <h3 style={{ margin: "0 0 16px" }}>{t("flowRecipientDetail")}</h3>
          <div className="flow-recipient-meta" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{t("flowRecipientCustomer")}</span>
              <p style={{ margin: "2px 0 0" }}>#{selectedRecipient.customer_id}</p>
            </div>
            <div>
              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{t("flowRecipientStatus")}</span>
              <p style={{ margin: "2px 0 0" }}>
                <span
                  style={{
                    display: "inline-block",
                    padding: "2px 8px",
                    borderRadius: 6,
                    fontSize: 11,
                    fontWeight: 600,
                    background: STATUS_STYLES[selectedRecipient.status] || "rgba(255,255,255,0.06)",
                    color: "var(--text)",
                  }}
                >
                  {t(`flowRecipientStatus_${selectedRecipient.status}`)}
                </span>
              </p>
            </div>
            <div>
              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{t("flowRecipientAttempts")}</span>
              <p style={{ margin: "2px 0 0" }}>{selectedRecipient.attempt_count}</p>
            </div>
            {selectedRecipient.error_message && (
              <div>
                <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{t("flowRecipientError")}</span>
                <p style={{ margin: "2px 0 0", color: "#ef4444" }}>{selectedRecipient.error_message}</p>
              </div>
            )}
          </div>

          {selectedRecipient.node_executions.length > 0 && (
            <>
              <h4 style={{ margin: "20px 0 12px", fontSize: 14 }}>{t("flowNodeExecutions")}</h4>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {selectedRecipient.node_executions.map((ne) => (
                  <div
                    key={ne.id}
                    style={{
                      padding: "12px 16px",
                      border: "1px solid var(--border)",
                      borderRadius: 10,
                      background: "var(--panel)",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <div>
                        <span style={{ fontSize: 12, fontWeight: 600 }}>{ne.node_id}</span>
                        <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: 8 }}>{ne.node_type}</span>
                      </div>
                      <span
                        style={{
                          fontSize: 11,
                          fontWeight: 600,
                          padding: "2px 8px",
                          borderRadius: 6,
                          background: ne.status === "completed" ? "rgba(34,197,94,0.12)" : ne.status === "failed" ? "rgba(239,68,68,0.12)" : "rgba(255,255,255,0.06)",
                          color: "var(--text)",
                        }}
                      >
                        {t(`flowExecStatus_${ne.status}`)}
                      </span>
                    </div>
                    {ne.error_message && (
                      <p style={{ margin: "6px 0 0", fontSize: 12, color: "#ef4444" }}>{ne.error_message}</p>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}

          {["failed", "skipped"].includes(selectedRecipient.status) && (
            <button
              className="primary-button"
              style={{ marginTop: 16 }}
              disabled={loading}
              onClick={() => void handleRetry(selectedRecipient.flow_run_id, selectedRecipient.id)}
            >
              <RotateCcw size={14} />
              {t("flowRetry")}
            </button>
          )}
        </div>
      </section>
    );
  }

  if (subView === "recipients") {
    return (
      <section className="flow-runs-section">
        {breadcrumb}
        <h3 style={{ margin: "0 0 16px" }}>{t("flowRecipients")}</h3>
        {loading && <p>{t("flowLoading")}</p>}
        {!loading && recipients.length === 0 && <p style={{ color: "var(--text-muted)" }}>{t("flowNoRecipients")}</p>}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {recipients.map((r) => (
            <div
              key={r.id}
              className="flow-recipient-row"
              onClick={() => void loadRecipientDetail(selectedRun!.id, r.id)}
              style={{
                padding: "12px 16px",
                border: "1px solid var(--border)",
                borderRadius: 10,
                background: "var(--panel)",
                cursor: "pointer",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                transition: "border-color 150ms ease",
              }}
            >
              <div>
                <span style={{ fontSize: 13, fontWeight: 600 }}>#{r.customer_id}</span>
                <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: 8 }}>
                  {t("flowAttemptCount")}: {r.attempt_count}
                </span>
              </div>
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  padding: "2px 8px",
                  borderRadius: 6,
                  background: STATUS_STYLES[r.status] || "rgba(255,255,255,0.06)",
                  color: "var(--text)",
                }}
              >
                {t(`flowRecipientStatus_${r.status}`)}
              </span>
            </div>
          ))}
        </div>
      </section>
    );
  }

  return (
    <section className="flow-runs-section">
      {breadcrumb}
      <h3 style={{ margin: "0 0 16px" }}>{t("flowRuns")}</h3>
      {!runs.length && !loading && <p style={{ color: "var(--text-muted)" }}>{t("flowNoRuns")}</p>}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {runs.map((run) => (
          <div
            key={run.id}
            className="flow-run-row"
            onClick={() => void loadRunDetail(run)}
            style={{
              padding: "14px 18px",
              border: "1px solid var(--border)",
              borderRadius: 10,
              background: "var(--panel)",
              cursor: "pointer",
              transition: "border-color 150ms ease",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <span style={{ fontSize: 13, fontWeight: 600 }}>#{run.id}</span>
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 600,
                    padding: "2px 8px",
                    borderRadius: 6,
                    background: STATUS_STYLES[run.status] || "rgba(255,255,255,0.06)",
                    color: "var(--text)",
                  }}
                >
                  {t(`flowRunStatus_${run.status}`)}
                </span>
              </div>
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{formatDate(run.created_at)}</span>
            </div>
            <div style={{ marginTop: 8, display: "flex", gap: 16, fontSize: 12, color: "var(--text-secondary)" }}>
              <span>{t("flowRunTotal")}: {run.total_recipients}</span>
              <span>{t("flowRunCompleted")}: {run.completed_recipients}</span>
              <span>{t("flowRunFailed")}: {run.failed_recipients}</span>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
