import React, { useCallback } from "react";
import {
  ReactFlowProvider,
  type Connection,
  type NodeTypes,
  type OnEdgesChange,
  type OnNodesChange,
} from "@xyflow/react";
import FlowCanvas from "./FlowCanvas";
import FlowNode from "./FlowNode";
import FlowNodePalette from "./FlowNodePalette";
import { connectFlowNodes, type FlowConnectionError } from "./flowConnectionRules";
import {
  addNodeToGraph,
  type FlowGraph,
  type FlowNode as FlowNodeData,
  type FlowNodeConfig,
  type FlowNodeType,
} from "./flowGraphUtils";

interface FlowBuilderInnerProps {
  graph: FlowGraph;
  onGraphChange: (graph: FlowGraph) => void;
  selectedNodeId: string | null;
  onNodeSelect: (nodeId: string | null) => void;
  canWrite: boolean;
}

const CONNECTION_MESSAGES: Record<FlowConnectionError, string> = {
  "missing-node": "Selecciona dos nodos existentes para conectarlos.",
  "self-loop": "No puedes conectar un nodo consigo mismo.",
  "trigger-target": "Un nodo de inicio no puede recibir conexiones.",
  "end-source": "Un nodo de fin no puede tener salidas.",
  "invalid-handle": "Utiliza una salida válida para este tipo de nodo.",
  "cycle": "Esa conexión crearía un ciclo. Los flujos deben avanzar sin bucles.",
};

const nodeTypes: NodeTypes = {
  flowNode: FlowNode as any,
};

function FlowBuilderInner({
  graph,
  onGraphChange,
  selectedNodeId,
  onNodeSelect,
  canWrite,
}: FlowBuilderInnerProps) {
  const graphRef = React.useRef(graph);
  graphRef.current = graph;
  const [connectionError, setConnectionError] = React.useState<FlowConnectionError | null>(null);

  const syncGraph = useCallback(
    (
      newNodes: FlowNodeData[],
      newEdges: FlowGraph["edges"],
    ) => {
      setConnectionError(null);
      onGraphChange({
        nodes: newNodes,
        edges: newEdges,
      });
    },
    [onGraphChange],
  );

  const handleNodesChange: OnNodesChange = useCallback(
    (changes) => {
      if (!canWrite) return;

      let nextNodes = graphRef.current.nodes;
      let nextEdges = graphRef.current.edges;
      let changed = false;

      for (const change of changes) {
        if (change.type === "position" && change.position) {
          nextNodes = nextNodes.map((node) =>
            node.id === change.id
              ? {
                  ...node,
                  position: {
                    x: change.position!.x,
                    y: change.position!.y,
                  },
                }
              : node,
          );
          changed = true;
        }

        if (change.type === "remove") {
          nextNodes = nextNodes.filter(
            (node) => node.id !== change.id,
          );
          nextEdges = nextEdges.filter(
            (edge) =>
              edge.source !== change.id
              && edge.target !== change.id,
          );
          if (selectedNodeId === change.id) {
            onNodeSelect(null);
          }
          changed = true;
        }
      }

      if (changed) {
        syncGraph(nextNodes, nextEdges);
      }
    },
    [
      canWrite,
      onNodeSelect,
      selectedNodeId,
      syncGraph,
    ],
  );

  const handleEdgesChange: OnEdgesChange = useCallback(
    (changes) => {
      if (!canWrite) return;

      const removed = new Set(
        changes
          .filter((change) => change.type === "remove")
          .map((change) => change.id),
      );

      if (!removed.size) return;

      const nextEdges = graphRef.current.edges.filter(
        (edge, index) => {
          const edgeId =
            `edge-${index}-${edge.source}-${edge.target}-${edge.sourceHandle || "default"}`;
          return !removed.has(edgeId);
        },
      );

      syncGraph(graphRef.current.nodes, nextEdges);
    },
    [canWrite, syncGraph],
  );

  const handleConnect = useCallback(
    (connection: Connection) => {
      if (!canWrite) return;

      const result = connectFlowNodes(graphRef.current, connection);
      setConnectionError(result.error);
      if (!result.error && result.graph !== graphRef.current) {
        onGraphChange(result.graph);
      }
    },
    [canWrite, onGraphChange],
  );

  const addNode = useCallback(
    (
      type: FlowNodeType,
      position?: { x: number; y: number },
      config?: Partial<FlowNodeConfig>,
    ) => {
      if (!canWrite) return;

      const fallbackPosition = {
        x: 260 + ((graphRef.current.nodes.length % 3) * 220),
        y: 150 + (graphRef.current.nodes.length * 80),
      };

      const next = addNodeToGraph(
        graphRef.current,
        type,
        position || fallbackPosition,
        config,
      );

      if (next === graphRef.current) return;

      setConnectionError(null);
      onGraphChange(next);
      const created = next.nodes[next.nodes.length - 1];
      if (created) onNodeSelect(created.id);
    },
    [canWrite, onGraphChange, onNodeSelect],
  );

  return (
    <div className="flow-builder-v2">
      <FlowNodePalette
        canWrite={canWrite}
        onAdd={(type, config) =>
          addNode(type, undefined, config)}
      />
      <div className="flow-canvas-workspace">
        <div className="flow-canvas-hint">
          <span>Canvas</span>
          <small>
            Arrastra o toca una herramienta para agregarla; conecta sus salidas con otros nodos.
          </small>
        </div>
        {connectionError && (
          <p className="flow-connection-error" role="status" aria-live="polite">
            {CONNECTION_MESSAGES[connectionError]}
          </p>
        )}
        <FlowCanvas
          graph={graph}
          canWrite={canWrite}
          onNodesChange={handleNodesChange}
          onEdgesChange={handleEdgesChange}
          onConnect={handleConnect}
          onNodeClick={onNodeSelect}
          onDropNode={addNode}
          selectedNodeId={selectedNodeId}
          nodeTypes={nodeTypes}
        />
      </div>
    </div>
  );
}

export interface FlowBuilderProps {
  graph: FlowGraph;
  onGraphChange: (graph: FlowGraph) => void;
  selectedNodeId: string | null;
  onNodeSelect: (nodeId: string | null) => void;
  canWrite: boolean;
}

export default function FlowBuilder(props: FlowBuilderProps) {
  return (
    <ReactFlowProvider>
      <FlowBuilderInner {...props} />
    </ReactFlowProvider>
  );
}

export { FlowBuilderInner };
