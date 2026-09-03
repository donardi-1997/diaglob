import React, { useCallback } from "react";
import { useTranslation } from "react-i18next";
import {
  ReactFlowProvider,
  useNodesState,
  useEdgesState,
  addEdge,
  type Connection,
  type NodeTypes,
} from "@xyflow/react";
import FlowCanvas from "./FlowCanvas";
import FlowNode from "./FlowNode";
import {
  type FlowGraph,
  type FlowNode as FlowNodeData,
} from "./flowGraphUtils";

interface FlowBuilderInnerProps {
  graph: FlowGraph;
  onGraphChange: (graph: FlowGraph) => void;
  selectedNodeId: string | null;
  onNodeSelect: (nodeId: string | null) => void;
}

function FlowBuilderInner({ graph, onGraphChange, selectedNodeId, onNodeSelect }: FlowBuilderInnerProps) {
  const { t } = useTranslation();
  const nodeTypes: NodeTypes = { flowNode: FlowNode as any };

  const [, , onNodesChange] = useNodesState(
    graph.nodes.map((n) => ({
      id: n.id,
      type: "flowNode",
      position: { x: n.position.x, y: n.position.y },
      data: n,
      selected: n.id === selectedNodeId,
    }))
  );

  const [, setEdges, onEdgesChange] = useEdgesState(
    graph.edges.map((e, i) => ({
      id: `edge-${i}-${e.source}-${e.target}-${e.sourceHandle || "default"}`,
      source: e.source,
      target: e.target,
      sourceHandle: e.sourceHandle || null,
      targetHandle: e.targetHandle || null,
      label: e.label || undefined,
      type: "smoothstep",
      style: { stroke: "var(--text-muted)", strokeWidth: 1.5 },
    }))
  );

  const graphRef = React.useRef(graph);
  graphRef.current = graph;

  const syncGraph = useCallback(
    (newNodes: FlowNodeData[], newEdges: { source: string; target: string; sourceHandle?: string; targetHandle?: string; label?: string }[]) => {
      onGraphChange({
        nodes: newNodes,
        edges: newEdges.map((e) => ({
          source: e.source,
          target: e.target,
          sourceHandle: e.sourceHandle || undefined,
          targetHandle: e.targetHandle || undefined,
          label: e.label || undefined,
        })),
      });
    },
    [onGraphChange]
  );

  const handleNodesChange: typeof onNodesChange = useCallback(
    (changes) => {
      onNodesChange(changes);
      const positionChanges = changes.filter((c: any) => c.type === "position" && c.position);
      if (positionChanges.length > 0) {
        const updated = graphRef.current.nodes.map((n) => {
          const change = positionChanges.find((c: any) => c.id === n.id) as any;
          if (change?.position) {
            return { ...n, position: { x: change.position.x, y: change.position.y } };
          }
          return n;
        });
        syncGraph(updated, graphRef.current.edges);
      }
      const removeChanges = changes.filter((c: any) => c.type === "remove");
      if (removeChanges.length > 0) {
        const ids = new Set(removeChanges.map((c: any) => c.id));
        syncGraph(
          graphRef.current.nodes.filter((n) => !ids.has(n.id)),
          graphRef.current.edges.filter((e) => !ids.has(e.source) && !ids.has(e.target))
        );
      }
    },
    [onNodesChange, syncGraph]
  );

  const handleEdgesChange: typeof onEdgesChange = useCallback(
    (changes) => {
      onEdgesChange(changes);
      const removeChanges = changes.filter((c: any) => c.type === "remove");
      if (removeChanges.length > 0) {
        const edgeIds = removeChanges.map((c: any) => c.id);
        const updatedEdges = graphRef.current.edges.filter((e, i) => {
          const edgeId = `edge-${i}-${e.source}-${e.target}-${e.sourceHandle || "default"}`;
          return !edgeIds.includes(edgeId);
        });
        syncGraph(graphRef.current.nodes, updatedEdges);
      }
    },
    [onEdgesChange, syncGraph]
  );

  const handleConnect = useCallback(
    (connection: Connection) => {
      setEdges((eds) => addEdge({ ...connection, type: "smoothstep", style: { stroke: "var(--text-muted)", strokeWidth: 1.5 } }, eds));
      if (connection.source && connection.target) {
        syncGraph(graphRef.current.nodes, [
          ...graphRef.current.edges,
          {
            source: connection.source,
            target: connection.target,
            sourceHandle: connection.sourceHandle || undefined,
            targetHandle: connection.targetHandle || undefined,
          },
        ]);
      }
    },
    [setEdges, syncGraph]
  );

  return (
    <FlowCanvas
      graph={{ nodes: graph.nodes, edges: graph.edges }}
      onNodesChange={handleNodesChange as any}
      onEdgesChange={handleEdgesChange as any}
      onConnect={handleConnect}
      onNodeClick={onNodeSelect}
      selectedNodeId={selectedNodeId}
      nodeTypes={nodeTypes}
      t={t}
    />
  );
}

export interface FlowBuilderProps {
  graph: FlowGraph;
  onGraphChange: (graph: FlowGraph) => void;
}

export default function FlowBuilder({ graph, onGraphChange }: FlowBuilderProps) {
  const [selectedNodeId, setSelectedNodeId] = React.useState<string | null>(null);

  return (
    <ReactFlowProvider>
      <FlowBuilderInner
        graph={graph}
        onGraphChange={onGraphChange}
        selectedNodeId={selectedNodeId}
        onNodeSelect={setSelectedNodeId}
      />
    </ReactFlowProvider>
  );
}

export { FlowBuilderInner };
