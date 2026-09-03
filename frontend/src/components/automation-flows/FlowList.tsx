import { useEffect, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Plus, ArrowLeft, Play, Pause, Archive, Eye, Edit3 } from "lucide-react";
import {
  listFlows,
  getFlow,
  createFlow,
  archiveFlow,
  activateFlow,
  deactivateFlow,
  type AutomationFlow,
} from "../../services/automationFlows";
import {
  type FlowGraph,
  createDefaultGraph,
  deserializeFlowGraph,
  serializeFlowGraph,
} from "./flowGraphUtils";
import FlowBuilder from "./FlowBuilder";
import FlowRuns from "./FlowRuns";
import FlowSidebar from "./FlowSidebar";
import FlowSimulation from "./FlowSimulation";
import type { FlowNodeConfig } from "./flowGraphUtils";

interface Props {
  canWrite: boolean;
  storeId: number;
}

type View = "list" | "builder" | "runs";

const STATUS_STYLES: Record<string, { bg: string; color: string }> = {
  draft: { bg: "rgba(255,255,255,0.06)", color: "var(--text-muted)" },
  active: { bg: "rgba(34,197,94,0.12)", color: "var(--green)" },
  paused: { bg: "rgba(230,168,23,0.12)", color: "#e6a817" },
  archived: { bg: "rgba(255,255,255,0.04)", color: "var(--text-muted)" },
};

export default function FlowList({ canWrite, storeId }: Props) {
  const { t } = useTranslation();
  const [view, setView] = useState<View>("list");
  const [flows, setFlows] = useState<AutomationFlow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [selectedFlow, setSelectedFlow] = useState<AutomationFlow | null>(null);
  const [graph, setGraph] = useState<FlowGraph>(createDefaultGraph());
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [showSimulation, setShowSimulation] = useState(false);

  const loadFlows = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setFlows(await listFlows(storeId));
    } catch {
      setError(t("flowListLoadError"));
    } finally {
      setLoading(false);
    }
  }, [storeId, t]);

  useEffect(() => {
    if (view === "list") void loadFlows();
  }, [view, loadFlows]);

  const handleCreate = async () => {
    if (!canWrite) return;
    setSaving(true);
    setError("");
    try {
      const flow = await createFlow(storeId, {
        name: t("flowNewName"),
        graph: serializeFlowGraph(createDefaultGraph()),
      });
      setSelectedFlow(flow);
      setGraph(flow.current_version ? deserializeFlowGraph(flow.current_version.graph) : createDefaultGraph());
      setView("builder");
    } catch {
      setError(t("flowCreateError"));
    } finally {
      setSaving(false);
    }
  };

  const handleEditFlow = async (flow: AutomationFlow) => {
    setLoading(true);
    setError("");
    try {
      const full = await getFlow(storeId, flow.id);
      setSelectedFlow(full);
      setGraph(full.current_version ? deserializeFlowGraph(full.current_version.graph) : createDefaultGraph());
      setView("builder");
    } catch {
      setError(t("flowLoadError"));
    } finally {
      setLoading(false);
    }
  };

  const handleViewRuns = (flow: AutomationFlow) => {
    setSelectedFlow(flow);
    setView("runs");
  };

  const handleSaveGraph = async () => {
    if (!selectedFlow || !canWrite) return;
    setSaving(true);
    setError("");
    try {
      const { listFlowVersions, createFlowVersion } = await import("../../services/automationFlows");
      const versions = await listFlowVersions(storeId, selectedFlow.id);
      const draftVersion = versions.find((v) => !v.published_at);
      if (draftVersion) {
        await createFlowVersion(storeId, selectedFlow.id, serializeFlowGraph(graph));
      } else {
        await createFlowVersion(storeId, selectedFlow.id, serializeFlowGraph(graph));
      }
      const updated = await getFlow(storeId, selectedFlow.id);
      setSelectedFlow(updated);
    } catch {
      setError(t("flowSaveError"));
    } finally {
      setSaving(false);
    }
  };

  const handleActivate = async (flow: AutomationFlow) => {
    if (!canWrite) return;
    try {
      await activateFlow(storeId, flow.id);
      await loadFlows();
    } catch {
      setError(t("flowActivateError"));
    }
  };

  const handleDeactivate = async (flow: AutomationFlow) => {
    if (!canWrite) return;
    try {
      await deactivateFlow(storeId, flow.id);
      await loadFlows();
    } catch {
      setError(t("flowDeactivateError"));
    }
  };

  const handleArchive = async (flow: AutomationFlow) => {
    if (!canWrite) return;
    try {
      await archiveFlow(storeId, flow.id);
      await loadFlows();
    } catch {
      setError(t("flowArchiveError"));
    }
  };

  const handleNodeUpdate = (nodeId: string, config: Partial<FlowNodeConfig>) => {
    const updated = {
      ...graph,
      nodes: graph.nodes.map((n) => (n.id === nodeId ? { ...n, config: { ...n.config, ...config } } : n)),
    };
    setGraph(updated);
  };

  const handleNodeDelete = (nodeId: string) => {
    const updated = {
      nodes: graph.nodes.filter((n) => n.id !== nodeId),
      edges: graph.edges.filter((e) => e.source !== nodeId && e.target !== nodeId),
    };
    setGraph(updated);
    setSelectedNodeId(null);
  };

  const selectedNode = selectedNodeId ? graph.nodes.find((n) => n.id === selectedNodeId) || null : null;

  const getNodeCount = (flow: AutomationFlow) => {
    if (!flow.current_version) return 0;
    const g = flow.current_version.graph as { nodes?: unknown[] };
    return g?.nodes?.length ?? 0;
  };

  const formatDate = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString() : "-");

  if (view === "runs" && selectedFlow) {
    return (
      <FlowRuns
        storeId={storeId}
        flowId={selectedFlow.id}
        onBack={() => {
          setView("list");
          setSelectedFlow(null);
        }}
        t={t}
      />
    );
  }

  if (view === "builder" && selectedFlow) {
    return (
      <section className="flow-builder-section">
        <div className="flow-builder-toolbar">
          <button
            className="secondary-button"
            onClick={() => {
              setView("list");
              setSelectedFlow(null);
              setSelectedNodeId(null);
            }}
          >
            <ArrowLeft size={14} />
            {t("flowBackToList")}
          </button>
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <h3 style={{ margin: 0 }}>{selectedFlow.name}</h3>
            {canWrite && (
              <>
                <button className="secondary-button" onClick={() => setShowSimulation(true)} disabled={saving}>
                  <Play size={14} />
                  {t("flowSimulate")}
                </button>
                <button className="primary-button" onClick={() => void handleSaveGraph()} disabled={saving}>
                  {saving ? t("flowSaving") : t("flowSave")}
                </button>
              </>
            )}
          </div>
        </div>
        {error && <p style={{ color: "#ef4444", margin: "8px 0" }}>{error}</p>}
        <FlowBuilder graph={graph} onGraphChange={setGraph} />
        <FlowSidebar
          node={selectedNode}
          graph={graph}
          onUpdate={handleNodeUpdate}
          onDelete={handleNodeDelete}
          onClose={() => setSelectedNodeId(null)}
          t={t}
          canWrite={canWrite}
        />
        {showSimulation && (
          <FlowSimulation
            storeId={storeId}
            graph={graph}
            flowName={selectedFlow.name}
            onClose={() => setShowSimulation(false)}
            t={t}
          />
        )}
      </section>
    );
  }

  return (
    <section className="flow-list-section">
      <div className="flow-list-header">
        <div>
          <h2>{t("flowListTitle")}</h2>
          <p style={{ color: "var(--text-secondary)", margin: "4px 0 0", fontSize: 13 }}>
            {t("flowListSubtitle")}
          </p>
        </div>
        {canWrite && (
          <button className="primary-button" onClick={() => void handleCreate()} disabled={saving}>
            <Plus size={16} />
            {t("flowCreate")}
          </button>
        )}
      </div>

      {loading && <p>{t("flowLoading")}</p>}
      {error && <p style={{ color: "#ef4444" }}>{error}</p>}

      {!loading && flows.length === 0 && (
        <div className="empty-state" style={{ padding: "60px 20px", textAlign: "center" }}>
          <p style={{ color: "var(--text-muted)" }}>{t("flowNoFlows")}</p>
          {canWrite && (
            <button className="primary-button" onClick={() => void handleCreate()} style={{ marginTop: 12 }}>
              <Plus size={16} />
              {t("flowCreateFirst")}
            </button>
          )}
        </div>
      )}

      <div className="flow-list-grid">
        {flows.map((flow) => {
          const st = STATUS_STYLES[flow.status] || STATUS_STYLES.draft;
          return (
            <article className="flow-card" key={flow.id}>
              <div className="flow-card-header">
                <div className="flow-card-info">
                  <h3>{flow.name}</h3>
                  {flow.description && (
                    <p style={{ color: "var(--text-secondary)", margin: "2px 0 0", fontSize: 12 }}>
                      {flow.description}
                    </p>
                  )}
                </div>
                <span
                  className="flow-status-badge"
                  style={{ background: st.bg, color: st.color }}
                >
                  {t(`flowStatus_${flow.status}`)}
                </span>
              </div>
              <div className="flow-card-meta">
                <span>{t("flowNodeCount")}: {getNodeCount(flow)}</span>
                <span>{t("flowCreated")}: {formatDate(flow.created_at)}</span>
              </div>
              <div className="flow-card-actions">
                {canWrite && flow.status !== "archived" && (
                  <button className="icon-button" title={t("flowEdit")} onClick={() => void handleEditFlow(flow)}>
                    <Edit3 size={15} />
                  </button>
                )}
                <button className="icon-button" title={t("flowViewRuns")} onClick={() => handleViewRuns(flow)}>
                  <Eye size={15} />
                </button>
                {canWrite && flow.status === "draft" && flow.current_version?.published_at && (
                  <button className="icon-button" title={t("flowActivate")} onClick={() => void handleActivate(flow)}>
                    <Play size={15} />
                  </button>
                )}
                {canWrite && flow.status === "active" && (
                  <button className="icon-button" title={t("flowPause")} onClick={() => void handleDeactivate(flow)}>
                    <Pause size={15} />
                  </button>
                )}
                {canWrite && flow.status !== "archived" && (
                  <button className="icon-button" title={t("flowArchive")} onClick={() => void handleArchive(flow)}>
                    <Archive size={15} />
                  </button>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
