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
import {
  addNodeToGraph,
  type FlowGraph,
  type FlowNode as FlowNodeData,
  type FlowNodeType,
} from "./flowGraphUtils";

interface FlowBuilderInnerProps {
  graph: FlowGraph;
  onGraphChange: (graph: FlowGraph) => void;
  selectedNodeId: string | null;
  onNodeSelect: (nodeId: string | null) => void;
  canWrite: boolean;
}

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

  const syncGraph = useCallback(
    (
      newNodes: FlowNodeData[],
      newEdges: FlowGraph["edges"],
    ) => {
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
      if (
        !canWrite
        || !connection.source
        || !connection.target
      ) {
        return;
      }

      const label =
        connection.sourceHandle === "true"
        || connection.sourceHandle === "false"
          ? connection.sourceHandle
          : undefined;

      const nextEdge = {
        source: connection.source,
        target: connection.target,
        sourceHandle: connection.sourceHandle || undefined,
        targetHandle: connection.targetHandle || undefined,
        label,
      };

      const withoutConflictingBranch =
        graphRef.current.edges.filter((edge) => {
          if (edge.source !== connection.source) return true;
          if (label) {
            return (edge.label || edge.sourceHandle) !== label;
          }
          return Boolean(edge.label || edge.sourceHandle);
        });

      syncGraph(
        graphRef.current.nodes,
        [...withoutConflictingBranch, nextEdge],
      );
    },
    [canWrite, syncGraph],
  );

  const addNode = useCallback(
    (
      type: FlowNodeType,
      position?: { x: number; y: number },
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
      );

      if (next === graphRef.current) return;

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
        onAdd={(type) => addNode(type)}
      />
      <div className="flow-canvas-workspace">
        <div className="flow-canvas-hint">
          <span>Canvas</span>
          <small>
            Conecta los nodos desde los puntos de entrada y salida.
          </small>
        </div>
        <FlowCanvas
          graph={graph}
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
