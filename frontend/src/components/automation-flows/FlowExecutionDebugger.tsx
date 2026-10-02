import { useMemo, useState } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
  type NodeTypes,
} from "@xyflow/react";
import {
  AlertTriangle,
  Clock3,
  RotateCcw,
  TerminalSquare,
} from "lucide-react";
import type {
  FlowNodeRunStats,
  NodeExecution,
} from "../../services/automationFlows";
import FlowNode from "./FlowNode";
import {
  deserializeFlowGraph,
  type FlowGraph,
  type FlowNode as FlowNodeData,
  type FlowNodeDebug,
} from "./flowGraphUtils";

interface Props {
  graph: Record<string, unknown> | FlowGraph;
  nodeStats?: Record<string, FlowNodeRunStats>;
  nodeExecutions?: NodeExecution[];
  currentNodeId?: string | null;
  recipientStatus?: string | null;
  canRetryFromNode?: boolean;
  retrying?: boolean;
  onRetryFromNode?: (nodeId: string) => void;
}

const nodeTypes: NodeTypes = {
  flowNode: FlowNode as any,
};

const TERMINAL_RECIPIENT_STATUSES = new Set([
  "completed",
  "failed",
  "ambiguous",
]);

function formatDuration(duration?: number | null) {
  if (duration == null) return "-";
  if (duration < 1000) return `${duration} ms`;
  if (duration < 60_000) {
    return `${(duration / 1000).toFixed(1)} s`;
  }
  return `${(duration / 60_000).toFixed(1)} min`;
}

function executionDebug(
  node: FlowNodeData,
  latest: NodeExecution | undefined,
  executions: NodeExecution[],
  currentNodeId?: string | null,
  recipientStatus?: string | null,
): FlowNodeDebug {
  if (latest) {
    let status = latest.status as FlowNodeDebug["status"];
    if (status === "sending" || status === "processing") {
      status = "running";
    }
    if (status === "retry_wait") status = "waiting";

    return {
      status,
      duration_ms: latest.duration_ms,
      executions: executions.length,
      error: latest.error_message,
    };
  }

  if (
    node.id === currentNodeId
    && recipientStatus
    && !TERMINAL_RECIPIENT_STATUSES.has(recipientStatus)
  ) {
    return {
      status:
        recipientStatus === "waiting"
          ? "waiting"
          : "running",
      executions: 0,
    };
  }

  if (
    node.type === "trigger"
    && (
      executions.length > 0
      || Boolean(currentNodeId)
      || TERMINAL_RECIPIENT_STATUSES.has(
        recipientStatus || "",
      )
    )
  ) {
    return {
      status: "completed",
      executions: 1,
      label: "Disparado",
    };
  }

  if (
    node.type === "end"
    && node.id === currentNodeId
    && recipientStatus === "completed"
  ) {
    return {
      status: "completed",
      executions: 1,
    };
  }

  return { status: "pending", executions: 0 };
}

function runDebug(
  node: FlowNodeData,
  stats?: FlowNodeRunStats,
): FlowNodeDebug {
  if (!stats || stats.executions === 0) {
    if (node.type === "trigger") {
      return {
        status: "completed",
        executions: 1,
        label: "Disparado",
      };
    }
    return { status: "pending", executions: 0 };
  }

  const counts = stats.status_counts || {};
  let status: FlowNodeDebug["status"] = "completed";

  if ((counts.failed || 0) > 0) status = "failed";
  else if ((counts.ambiguous || 0) > 0) status = "ambiguous";
  else if (
    (counts.sending || 0) > 0
    || (counts.processing || 0) > 0
  ) {
    status = "running";
  } else if ((counts.retry_wait || 0) > 0) status = "waiting";
  else if (
    (counts.skipped || 0) > 0
    && (counts.completed || 0) === 0
  ) {
    status = "skipped";
  }

  return {
    status,
    duration_ms: stats.avg_duration_ms,
    executions: stats.executions,
    error: stats.last_error,
  };
}

function edgeStyle(
  edge: FlowGraph["edges"][number],
  nodeMap: Map<string, FlowNodeData>,
  latestByNode: Map<string, NodeExecution>,
) {
  const source = nodeMap.get(edge.source);
  const target = nodeMap.get(edge.target);
  const sourceDebug = source?.debug;
  const targetDebug = target?.debug;
  const sourceExecution = latestByNode.get(edge.source);

  const branch = edge.label || edge.sourceHandle;
  if (
    branch
    && sourceExecution?.outcome
    && sourceExecution.outcome !== branch
  ) {
    return {
      stroke: "var(--border)",
      strokeWidth: 1,
      opacity: 0.28,
    };
  }

  if (
    sourceDebug?.status === "failed"
    || sourceDebug?.status === "ambiguous"
  ) {
    return {
      stroke: "#ef4444",
      strokeWidth: 2.2,
      opacity: 1,
    };
  }

  if (
    targetDebug?.status === "completed"
    || targetDebug?.status === "skipped"
    || targetDebug?.status === "failed"
    || targetDebug?.status === "ambiguous"
  ) {
    return {
      stroke:
        targetDebug.status === "failed"
        || targetDebug.status === "ambiguous"
          ? "#ef4444"
          : "#22c55e",
      strokeWidth: 2.2,
      opacity: 0.95,
    };
  }

  if (
    sourceDebug?.status === "running"
    || sourceDebug?.status === "waiting"
  ) {
    return {
      stroke: "#3b82f6",
      strokeWidth: 2,
      opacity: 0.9,
    };
  }

  return {
    stroke: "var(--text-muted)",
    strokeWidth: 1.2,
    opacity: 0.45,
  };
}

export default function FlowExecutionDebugger({
  graph,
  nodeStats,
  nodeExecutions,
  currentNodeId,
  recipientStatus,
  canRetryFromNode = false,
  retrying = false,
  onRetryFromNode,
}: Props) {
  const [selectedNodeId, setSelectedNodeId] =
    useState<string | null>(null);

  const baseGraph = useMemo(
    () =>
      "nodes" in graph
        ? deserializeFlowGraph(
            graph as Record<string, unknown>,
          )
        : graph,
    [graph],
  );

  const executionGroups = useMemo(() => {
    const map = new Map<string, NodeExecution[]>();
    for (const execution of nodeExecutions || []) {
      const items = map.get(execution.node_id) || [];
      items.push(execution);
      map.set(execution.node_id, items);
    }
    return map;
  }, [nodeExecutions]);

  const latestByNode = useMemo(() => {
    const map = new Map<string, NodeExecution>();
    for (const [nodeId, items] of executionGroups) {
      if (items.length) {
        map.set(nodeId, items[items.length - 1]);
      }
    }
    return map;
  }, [executionGroups]);

  const decoratedGraph = useMemo<FlowGraph>(() => {
    return {
      nodes: baseGraph.nodes.map((node) => ({
        ...node,
        debug: nodeExecutions
          ? executionDebug(
              node,
              latestByNode.get(node.id),
              executionGroups.get(node.id) || [],
              currentNodeId,
              recipientStatus,
            )
          : runDebug(node, nodeStats?.[node.id]),
      })),
      edges: baseGraph.edges,
    };
  }, [
    baseGraph,
    currentNodeId,
    executionGroups,
    latestByNode,
    nodeExecutions,
    nodeStats,
    recipientStatus,
  ]);

  const nodeMap = useMemo(
    () =>
      new Map(
        decoratedGraph.nodes.map((node) => [node.id, node]),
      ),
    [decoratedGraph.nodes],
  );

  const nodes = useMemo<Node[]>(
    () =>
      decoratedGraph.nodes.map((node) => ({
        id: node.id,
        type: "flowNode",
        position: node.position,
        data: node,
        selected: node.id === selectedNodeId,
        draggable: false,
        connectable: false,
      })),
    [decoratedGraph.nodes, selectedNodeId],
  );

  const edges = useMemo<Edge[]>(
    () =>
      decoratedGraph.edges.map((edge, index) => ({
        id:
          `debug-edge-${index}-${edge.source}-${edge.target}-${edge.sourceHandle || "default"}`,
        source: edge.source,
        target: edge.target,
        sourceHandle: edge.sourceHandle || null,
        targetHandle: edge.targetHandle || null,
        label: edge.label,
        type: "smoothstep",
        animated:
          nodeMap.get(edge.source)?.debug?.status ===
          "running",
        style: edgeStyle(edge, nodeMap, latestByNode),
      })),
    [decoratedGraph.edges, latestByNode, nodeMap],
  );

  const selectedNode = selectedNodeId
    ? nodeMap.get(selectedNodeId)
    : undefined;
  const selectedExecutions = selectedNodeId
    ? executionGroups.get(selectedNodeId) || []
    : [];
  const selectedLatest = selectedExecutions.length
    ? selectedExecutions[selectedExecutions.length - 1]
    : undefined;
  const selectedStats = selectedNodeId
    ? nodeStats?.[selectedNodeId]
    : undefined;

  const canRetry =
    Boolean(onRetryFromNode)
    && canRetryFromNode
    && selectedNode
    && selectedNode.type !== "trigger";

  return (
    <div className="flow-debugger">
      <div className="flow-debugger-canvas">
        <div className="flow-debugger-legend">
          <span className="ok">Completado</span>
          <span className="run">Ejecutando</span>
          <span className="wait">Esperando</span>
          <span className="fail">Falló</span>
          <span className="pending">Pendiente</span>
        </div>

        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          nodesDraggable={false}
          nodesConnectable={false}
          edgesReconnectable={false}
          onNodeClick={(_event, node) =>
            setSelectedNodeId(node.id)}
          proOptions={{ hideAttribution: true }}
        >
          <Background
            color="var(--text-muted)"
            gap={20}
            size={1}
          />
          <Controls showInteractive={false} />
          <MiniMap
            pannable
            zoomable
            nodeColor={(node) => {
              const data =
                node.data as unknown as FlowNodeData;
              const status = data.debug?.status;
              if (status === "completed") return "#22c55e";
              if (
                status === "failed"
                || status === "ambiguous"
              ) {
                return "#ef4444";
              }
              if (status === "running") return "#3b82f6";
              if (status === "waiting") return "#e6a817";
              return "#64748b";
            }}
            maskColor="rgba(0,0,0,0.35)"
          />
        </ReactFlow>
      </div>

      <aside className="flow-debugger-inspector">
        {!selectedNode ? (
          <div className="flow-debugger-empty">
            <TerminalSquare size={24} />
            <strong>Inspecciona un nodo</strong>
            <span>
              Selecciona un nodo para ver tiempos, output,
              errores y reejecutarlo cuando aplique.
            </span>
          </div>
        ) : (
          <>
            <div className="flow-debugger-inspector-head">
              <div>
                <span>{selectedNode.type}</span>
                <strong>{selectedNode.id}</strong>
              </div>
              <span
                className={
                  `flow-debug-status is-${selectedNode.debug?.status || "pending"}`
                }
              >
                {selectedNode.debug?.status || "pending"}
              </span>
            </div>

            <div className="flow-debugger-kpis">
              <div>
                <Clock3 size={14} />
                <span>Duración</span>
                <strong>
                  {formatDuration(
                    selectedLatest?.duration_ms
                    ?? selectedStats?.avg_duration_ms,
                  )}
                </strong>
              </div>
              <div>
                <TerminalSquare size={14} />
                <span>Ejecuciones</span>
                <strong>
                  {selectedExecutions.length
                    || selectedStats?.executions
                    || 0}
                </strong>
              </div>
            </div>

            {selectedLatest?.outcome && (
              <div className="flow-debugger-field">
                <span>Outcome</span>
                <code>{selectedLatest.outcome}</code>
              </div>
            )}

            {selectedLatest?.provider_message_id && (
              <div className="flow-debugger-field">
                <span>Provider message ID</span>
                <code>
                  {selectedLatest.provider_message_id}
                </code>
              </div>
            )}

            {(selectedLatest?.error_message
              || selectedStats?.last_error) && (
              <div className="flow-debugger-error">
                <AlertTriangle size={15} />
                <div>
                  <strong>
                    {selectedLatest?.error_code || "Error"}
                  </strong>
                  <span>
                    {selectedLatest?.error_message
                    || selectedStats?.last_error}
                  </span>
                </div>
              </div>
            )}

            {selectedLatest?.metadata && (
              <div className="flow-debugger-field">
                <span>Input / output</span>
                <pre>
                  {JSON.stringify(
                    selectedLatest.metadata,
                    null,
                    2,
                  )}
                </pre>
              </div>
            )}

            {selectedExecutions.length > 1 && (
              <div className="flow-debugger-history">
                <span>Historial del nodo</span>
                {selectedExecutions.map((execution) => (
                  <div key={execution.id}>
                    <strong>#{execution.id}</strong>
                    <span>{execution.status}</span>
                    <small>
                      {formatDuration(execution.duration_ms)}
                    </small>
                  </div>
                ))}
              </div>
            )}

            {canRetry && (
              <button
                className="primary-button flow-debugger-retry"
                disabled={retrying}
                onClick={() =>
                  onRetryFromNode?.(selectedNode.id)}
              >
                <RotateCcw size={14} />
                Reejecutar desde este nodo
              </button>
            )}
          </>
        )}
      </aside>
    </div>
  );
}
