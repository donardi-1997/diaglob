import {
  useCallback,
  useEffect,
  useState,
} from "react";
import {
  ArrowLeft,
  Network,
  RotateCcw,
  Users,
} from "lucide-react";
import {
  getFlowRecipientDetail,
  getFlowRun,
  listFlowRunRecipients,
  listFlowRuns,
  retryFlowRecipient,
  retryFlowRecipientFromNode,
  type AutomationFlowRecipient,
  type AutomationFlowRecipientDetail,
  type AutomationFlowRun,
} from "../../services/automationFlows";
import FlowExecutionDebugger from "./FlowExecutionDebugger";

interface Props {
  storeId: number;
  flowId: number;
  canWrite: boolean;
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
  active: "rgba(74,158,255,0.12)",
  waiting: "rgba(230,168,23,0.12)",
};

const TERMINAL_RECIPIENT_STATUSES = new Set([
  "failed",
  "ambiguous",
  "completed",
]);

type SubView =
  | "runs"
  | "run-map"
  | "recipients"
  | "detail";

export default function FlowRuns({
  storeId,
  flowId,
  canWrite,
  onBack,
  t,
}: Props) {
  const [subView, setSubView] = useState<SubView>("runs");
  const [runs, setRuns] = useState<AutomationFlowRun[]>([]);
  const [selectedRun, setSelectedRun] =
    useState<AutomationFlowRun | null>(null);
  const [recipients, setRecipients] = useState<
    AutomationFlowRecipient[]
  >([]);
  const [selectedRecipient, setSelectedRecipient] =
    useState<AutomationFlowRecipientDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [retryingNodeId, setRetryingNodeId] =
    useState<string | null>(null);
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
        const detail = await getFlowRun(
          storeId,
          flowId,
          run.id,
        );
        setSelectedRun(detail);
        setSubView("run-map");
      } catch {
        setError(t("flowRunsLoadError"));
      } finally {
        setLoading(false);
      }
    },
    [storeId, flowId, t],
  );

  const refreshSelectedRun = useCallback(
    async (runId: number) => {
      const detail = await getFlowRun(
        storeId,
        flowId,
        runId,
      );
      setSelectedRun(detail);
      return detail;
    },
    [storeId, flowId],
  );

  const loadRecipients = useCallback(
    async (runId: number) => {
      setLoading(true);
      setError("");
      try {
        const result = await listFlowRunRecipients(
          storeId,
          flowId,
          runId,
        );
        setRecipients(result.items);
      } catch {
        setError(t("flowRunsLoadError"));
      } finally {
        setLoading(false);
      }
    },
    [storeId, flowId, t],
  );

  useEffect(() => {
    if (subView === "recipients" && selectedRun) {
      void loadRecipients(selectedRun.id);
    }
  }, [subView, selectedRun?.id, loadRecipients]);

  const loadRecipientDetail = useCallback(
    async (runId: number, recipientId: number) => {
      setLoading(true);
      setError("");
      try {
        setSelectedRecipient(
          await getFlowRecipientDetail(
            storeId,
            flowId,
            runId,
            recipientId,
          ),
        );
        setSubView("detail");
      } catch {
        setError(t("flowRunsLoadError"));
      } finally {
        setLoading(false);
      }
    },
    [storeId, flowId, t],
  );

  const handleRetry = useCallback(
    async (runId: number, recipientId: number) => {
      setLoading(true);
      setError("");
      try {
        await retryFlowRecipient(
          storeId,
          flowId,
          runId,
          recipientId,
        );
        await refreshSelectedRun(runId);
        setSelectedRecipient(
          await getFlowRecipientDetail(
            storeId,
            flowId,
            runId,
            recipientId,
          ),
        );
      } catch {
        setError(t("flowRetryError"));
      } finally {
        setLoading(false);
      }
    },
    [storeId, flowId, refreshSelectedRun, t],
  );

  const handleRetryFromNode = useCallback(
    async (nodeId: string) => {
      if (!selectedRun || !selectedRecipient || !canWrite) {
        return;
      }
      setRetryingNodeId(nodeId);
      setError("");
      try {
        await retryFlowRecipientFromNode(
          storeId,
          flowId,
          selectedRun.id,
          selectedRecipient.id,
          nodeId,
        );
        await refreshSelectedRun(selectedRun.id);
        setSelectedRecipient(
          await getFlowRecipientDetail(
            storeId,
            flowId,
            selectedRun.id,
            selectedRecipient.id,
          ),
        );
      } catch {
        setError(t("flowRetryError"));
      } finally {
        setRetryingNodeId(null);
      }
    },
    [
      canWrite,
      flowId,
      refreshSelectedRun,
      selectedRecipient,
      selectedRun,
      storeId,
      t,
    ],
  );

  const formatDate = (iso: string | null) =>
    iso ? new Date(iso).toLocaleString() : "-";

  const goBack = () => {
    if (subView === "detail") {
      setSelectedRecipient(null);
      setSubView("recipients");
      return;
    }
    if (subView === "recipients") {
      setRecipients([]);
      setSubView("run-map");
      return;
    }
    if (subView === "run-map") {
      setSelectedRun(null);
      setSubView("runs");
      return;
    }
    onBack();
  };

  const breadcrumb = (
    <div className="flow-runs-breadcrumb">
      <button
        className="icon-button"
        onClick={goBack}
        aria-label="Volver"
      >
        <ArrowLeft size={14} />
      </button>
      <span>
        {t("flowRunsBreadcrumbRuns")}
        {subView === "run-map" && " / Debug"}
        {subView === "recipients"
          && ` / ${t("flowRunsBreadcrumbRecipients")}`}
        {subView === "detail"
          && ` / ${t("flowRunsBreadcrumbRecipients")} / ${t("flowRunsBreadcrumbDetail")}`}
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

  if (subView === "detail" && selectedRecipient) {
    const canRetry = canWrite
      && TERMINAL_RECIPIENT_STATUSES.has(
        selectedRecipient.status,
      );

    return (
      <section className="flow-runs-section">
        {breadcrumb}

        {error && (
          <p className="flow-runs-error">{error}</p>
        )}

        <div className="flow-recipient-debug-header">
          <div>
            <span>Destinatario</span>
            <strong>
              Cliente #{selectedRecipient.customer_id}
            </strong>
          </div>
          <span
            className="flow-recipient-status"
            style={{
              background:
                STATUS_STYLES[selectedRecipient.status]
                || STATUS_STYLES.pending,
            }}
          >
            {t(
              `flowRecipientStatus_${selectedRecipient.status}`,
            )}
          </span>
          <div className="flow-recipient-debug-meta">
            <span>
              Intentos: {selectedRecipient.attempt_count}
            </span>
            <span>
              Nodo actual: {
                selectedRecipient.current_node_id || "-"
              }
            </span>
            <span>
              Inicio: {
                formatDate(selectedRecipient.started_at)
              }
            </span>
          </div>
        </div>

        {selectedRecipient.error_message && (
          <div className="flow-run-error-banner">
            <strong>
              {selectedRecipient.error_code || "Error"}
            </strong>
            <span>{selectedRecipient.error_message}</span>
          </div>
        )}

        {selectedRun?.graph ? (
          <FlowExecutionDebugger
            graph={selectedRun.graph}
            nodeExecutions={
              selectedRecipient.node_executions
            }
            currentNodeId={
              selectedRecipient.current_node_id
            }
            recipientStatus={selectedRecipient.status}
            canRetryFromNode={canRetry}
            retrying={Boolean(retryingNodeId)}
            onRetryFromNode={(nodeId) =>
              void handleRetryFromNode(nodeId)}
          />
        ) : (
          <p className="flow-runs-empty">
            No se encontró el grafo histórico de esta ejecución.
          </p>
        )}

        {canRetry && (
          <button
            className="secondary-button flow-retry-recipient"
            disabled={loading || Boolean(retryingNodeId)}
            onClick={() =>
              void handleRetry(
                selectedRecipient.flow_run_id,
                selectedRecipient.id,
              )}
          >
            <RotateCcw size={14} />
            Reintentar desde el nodo actual
          </button>
        )}
      </section>
    );
  }

  if (subView === "recipients" && selectedRun) {
    return (
      <section className="flow-runs-section">
        {breadcrumb}

        <div className="flow-runs-view-header">
          <div>
            <span>Run #{selectedRun.id}</span>
            <h3>{t("flowRecipients")}</h3>
          </div>
          <button
            className="secondary-button"
            onClick={() => setSubView("run-map")}
          >
            <Network size={14} />
            Mapa de ejecución
          </button>
        </div>

        {error && (
          <p className="flow-runs-error">{error}</p>
        )}
        {loading && <p>{t("flowLoading")}</p>}
        {!loading && recipients.length === 0 && (
          <p className="flow-runs-empty">
            {t("flowNoRecipients")}
          </p>
        )}

        <div className="flow-recipient-list">
          {recipients.map((recipient) => (
            <button
              key={recipient.id}
              type="button"
              className="flow-recipient-row"
              onClick={() =>
                void loadRecipientDetail(
                  selectedRun.id,
                  recipient.id,
                )}
            >
              <div>
                <strong>
                  Cliente #{recipient.customer_id}
                </strong>
                <span>
                  {t("flowAttemptCount")}: {
                    recipient.attempt_count
                  }
                </span>
                {recipient.current_node_id && (
                  <small>
                    {recipient.current_node_id}
                  </small>
                )}
              </div>
              <span
                className="flow-recipient-status"
                style={{
                  background:
                    STATUS_STYLES[recipient.status]
                    || STATUS_STYLES.pending,
                }}
              >
                {t(
                  `flowRecipientStatus_${recipient.status}`,
                )}
              </span>
            </button>
          ))}
        </div>
      </section>
    );
  }

  if (subView === "run-map" && selectedRun) {
    return (
      <section className="flow-runs-section">
        {breadcrumb}

        <div className="flow-runs-view-header">
          <div>
            <span>Diagnóstico</span>
            <h3>Run #{selectedRun.id}</h3>
          </div>
          <button
            className="secondary-button"
            onClick={() => setSubView("recipients")}
          >
            <Users size={14} />
            Ver destinatarios
          </button>
        </div>

        {error && (
          <p className="flow-runs-error">{error}</p>
        )}

        <div className="flow-run-summary-strip">
          <div>
            <span>Estado</span>
            <strong>{selectedRun.status}</strong>
          </div>
          <div>
            <span>Total</span>
            <strong>
              {selectedRun.total_recipients}
            </strong>
          </div>
          <div>
            <span>Completados</span>
            <strong>
              {selectedRun.completed_recipients}
            </strong>
          </div>
          <div>
            <span>Fallidos</span>
            <strong>
              {selectedRun.failed_recipients}
            </strong>
          </div>
          <div>
            <span>Inicio</span>
            <strong>
              {formatDate(selectedRun.started_at)}
            </strong>
          </div>
        </div>

        {selectedRun.graph ? (
          <FlowExecutionDebugger
            graph={selectedRun.graph}
            nodeStats={selectedRun.node_stats}
          />
        ) : (
          <p className="flow-runs-empty">
            Esta ejecución no tiene un grafo histórico disponible.
          </p>
        )}
      </section>
    );
  }

  return (
    <section className="flow-runs-section">
      {breadcrumb}

      <div className="flow-runs-view-header">
        <div>
          <span>Observabilidad</span>
          <h3>{t("flowRuns")}</h3>
        </div>
      </div>

      {error && (
        <p className="flow-runs-error">{error}</p>
      )}

      {!runs.length && !loading && (
        <p className="flow-runs-empty">
          {t("flowNoRuns")}
        </p>
      )}

      <div className="flow-run-list">
        {runs.map((run) => (
          <button
            key={run.id}
            type="button"
            className="flow-run-row"
            onClick={() => void loadRunDetail(run)}
          >
            <div className="flow-run-row-main">
              <div>
                <Network size={15} />
                <strong>Run #{run.id}</strong>
                <span
                  className="flow-run-status"
                  style={{
                    background:
                      STATUS_STYLES[run.status]
                      || STATUS_STYLES.pending,
                  }}
                >
                  {t(`flowRunStatus_${run.status}`)}
                </span>
              </div>
              <span>{formatDate(run.created_at)}</span>
            </div>
            <div className="flow-run-row-stats">
              <span>
                Total <strong>{run.total_recipients}</strong>
              </span>
              <span>
                Completados{" "}
                <strong>{run.completed_recipients}</strong>
              </span>
              <span>
                Fallidos{" "}
                <strong>{run.failed_recipients}</strong>
              </span>
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}
