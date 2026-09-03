import { useEffect, useState } from "react";
import { X, AlertTriangle, CheckCircle } from "lucide-react";
import { simulateFlow, type FlowSimulationResult } from "../../services/automationFlows";
import { serializeFlowGraph, type FlowGraph } from "./flowGraphUtils";

interface Props {
  storeId: number;
  graph: FlowGraph;
  flowName: string;
  onClose: () => void;
  t: (key: string) => string;
}

export default function FlowSimulation({ storeId, graph, flowName, onClose, t }: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [result, setResult] = useState<FlowSimulationResult | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    simulateFlow(storeId, { name: flowName, graph: serializeFlowGraph(graph) })
      .then((res) => {
        if (!cancelled) setResult(res);
      })
      .catch(() => {
        if (!cancelled) setError(t("flowSimulationError"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [storeId, graph, flowName, t]);

  return (
    <div
      className="management-modal-backdrop"
      onClick={onClose}
    >
      <div
        className="management-modal"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: 520 }}
      >
        <div className="management-modal-header">
          <div>
            <h2 style={{ margin: 0 }}>{t("flowSimulationTitle")}</h2>
            <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--text-secondary)" }}>
              {flowName}
            </p>
          </div>
          <button
            className="icon-button"
            onClick={onClose}
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
            <X size={16} />
          </button>
        </div>

        <div style={{ padding: "16px 24px" }}>
          <div
            className="flow-simulation-banner"
            style={{
              padding: "10px 14px",
              borderRadius: 8,
              background: "rgba(230,168,23,0.12)",
              border: "1px solid rgba(230,168,23,0.25)",
              marginBottom: 16,
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            <AlertTriangle size={16} style={{ color: "#e6a817", flexShrink: 0 }} />
            <span style={{ fontSize: 12, fontWeight: 700, color: "#e6a817", textTransform: "uppercase", letterSpacing: "0.05em" }}>
              {t("flowSimulationBanner")}
            </span>
          </div>

          {loading && (
            <div style={{ textAlign: "center", padding: "32px 0" }}>
              <p>{t("flowSimulationLoading")}</p>
            </div>
          )}

          {error && (
            <p style={{ color: "#ef4444", textAlign: "center", padding: "24px 0" }}>{error}</p>
          )}

          {result && !loading && (
            <>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "12px 14px",
                  borderRadius: 8,
                  background: result.valid ? "rgba(34,197,94,0.1)" : "rgba(239,68,68,0.1)",
                  border: result.valid ? "1px solid rgba(34,197,94,0.25)" : "1px solid rgba(239,68,68,0.25)",
                  marginBottom: 16,
                }}
              >
                {result.valid ? (
                  <CheckCircle size={18} style={{ color: "var(--green)" }} />
                ) : (
                  <AlertTriangle size={18} style={{ color: "#ef4444" }} />
                )}
                <span style={{ fontSize: 14, fontWeight: 600 }}>
                  {result.valid ? t("flowSimulationValid") : t("flowSimulationInvalid")}
                </span>
              </div>

              {result.errors.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <h4 style={{ margin: "0 0 8px", fontSize: 13, color: "#ef4444" }}>{t("flowSimulationErrors")}</h4>
                  <ul style={{ margin: 0, paddingLeft: 18 }}>
                    {result.errors.map((err, i) => (
                      <li key={i} style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 4 }}>
                        {t(err)}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {result.warnings.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <h4 style={{ margin: "0 0 8px", fontSize: 13, color: "#e6a817" }}>{t("flowSimulationWarnings")}</h4>
                  <ul style={{ margin: 0, paddingLeft: 18 }}>
                    {result.warnings.map((warn, i) => (
                      <li key={i} style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 4 }}>
                        {t(warn)}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {result.summary && (
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(2, 1fr)",
                    gap: 10,
                    marginTop: 16,
                  }}
                >
                  <div className="flow-sim-stat" style={{ padding: "10px 14px", border: "1px solid var(--border)", borderRadius: 8, background: "var(--panel)" }}>
                    <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{t("flowSimTotalNodes")}</span>
                    <p style={{ margin: "2px 0 0", fontSize: 16, fontWeight: 700 }}>{result.summary.total_nodes}</p>
                  </div>
                  <div className="flow-sim-stat" style={{ padding: "10px 14px", border: "1px solid var(--border)", borderRadius: 8, background: "var(--panel)" }}>
                    <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{t("flowSimMessageNodes")}</span>
                    <p style={{ margin: "2px 0 0", fontSize: 16, fontWeight: 700 }}>{result.summary.message_nodes}</p>
                  </div>
                  <div className="flow-sim-stat" style={{ padding: "10px 14px", border: "1px solid var(--border)", borderRadius: 8, background: "var(--panel)" }}>
                    <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{t("flowSimWaitNodes")}</span>
                    <p style={{ margin: "2px 0 0", fontSize: 16, fontWeight: 700 }}>{result.summary.wait_nodes}</p>
                  </div>
                  <div className="flow-sim-stat" style={{ padding: "10px 14px", border: "1px solid var(--border)", borderRadius: 8, background: "var(--panel)" }}>
                    <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{t("flowSimConditionNodes")}</span>
                    <p style={{ margin: "2px 0 0", fontSize: 16, fontWeight: 700 }}>{result.summary.condition_nodes}</p>
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        <div className="management-modal-actions">
          <button className="secondary-button" onClick={onClose}>
            {t("flowClose")}
          </button>
        </div>
      </div>
    </div>
  );
}
