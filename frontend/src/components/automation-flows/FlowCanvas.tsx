import { useCallback, useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  type OnNodesChange,
  type OnEdgesChange,
  type Connection,
  type NodeTypes,
} from "@xyflow/react";
import type { FlowGraph, FlowNode as FlowNodeData, FlowEdge } from "./flowGraphUtils";

interface FlowCanvasProps {
  graph: FlowGraph;
  onNodesChange: OnNodesChange;
  onEdgesChange: OnEdgesChange;
  onConnect: (conn: Connection) => void;
  onNodeClick: (nodeId: string) => void;
  selectedNodeId: string | null;
  nodeTypes: NodeTypes;
  t: (key: string) => string;
}

function toReactFlowNodes(nodes: FlowNodeData[]): Node[] {
  return nodes.map((n) => ({
    id: n.id,
    type: "flowNode",
    position: { x: n.position.x, y: n.position.y },
    data: n,
    selected: false,
  }));
}

function toReactFlowEdges(edges: FlowEdge[]): Edge[] {
  return edges.map((e, i) => ({
    id: `edge-${i}-${e.source}-${e.target}-${e.sourceHandle || "default"}`,
    source: e.source,
    target: e.target,
    sourceHandle: e.sourceHandle || null,
    targetHandle: e.targetHandle || null,
    label: e.label || undefined,
    type: "smoothstep",
    animated: false,
    style: { stroke: "var(--text-muted)", strokeWidth: 1.5 },
  }));
}

export default function FlowCanvas({
  graph,
  onNodesChange,
  onEdgesChange,
  onConnect,
  onNodeClick,
  selectedNodeId,
  nodeTypes,
}: FlowCanvasProps) {
  const nodes = useMemo(() => {
    const rfNodes = toReactFlowNodes(graph.nodes);
    if (selectedNodeId) {
      return rfNodes.map((n) => ({ ...n, selected: n.id === selectedNodeId }));
    }
    return rfNodes;
  }, [graph.nodes, selectedNodeId]);

  const edges = useMemo(() => toReactFlowEdges(graph.edges), [graph.edges]);

  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      onNodeClick(node.id);
    },
    [onNodeClick]
  );

  return (
    <div
      className="flow-canvas-container"
      style={{
        height: 500,
        border: "1px solid var(--border)",
        borderRadius: 14,
        background: "var(--panel)",
        overflow: "hidden",
      }}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={handleNodeClick}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{
          type: "smoothstep",
          style: { stroke: "var(--text-muted)", strokeWidth: 1.5 },
        }}
      >
        <Background color="var(--text-muted)" gap={20} size={1} />
        <Controls
          style={{
            background: "var(--panel)",
            border: "1px solid var(--border)",
            borderRadius: 10,
          }}
        />
        <MiniMap
          nodeColor={(node: Node) => {
            const data = node.data as FlowNodeData;
            const colors: Record<string, string> = {
              trigger: "#7c5cff",
              wait: "#e6a817",
              condition: "#4a9eff",
              message: "#22c55e",
              end: "#6b7280",
            };
            return colors[data?.type] || "#6b7280";
          }}
          maskColor="rgba(0,0,0,0.35)"
          style={{
            background: "var(--bg)",
            border: "1px solid var(--border)",
            borderRadius: 8,
          }}
        />
      </ReactFlow>
    </div>
  );
}
