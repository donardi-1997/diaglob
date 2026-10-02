import { useCallback, useMemo } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
  type NodeTypes,
  type OnEdgesChange,
  type OnNodesChange,
} from "@xyflow/react";
import type {
  FlowEdge,
  FlowGraph,
  FlowNode as FlowNodeData,
  FlowNodeConfig,
  FlowNodeType,
} from "./flowGraphUtils";

interface FlowCanvasProps {
  graph: FlowGraph;
  onNodesChange: OnNodesChange;
  onEdgesChange: OnEdgesChange;
  onConnect: (connection: Connection) => void;
  onNodeClick: (nodeId: string) => void;
  onDropNode: (
    type: FlowNodeType,
    position: { x: number; y: number },
    config?: Partial<FlowNodeConfig>,
  ) => void;
  selectedNodeId: string | null;
  nodeTypes: NodeTypes;
}

function toReactFlowNodes(nodes: FlowNodeData[]): Node[] {
  return nodes.map((node) => ({
    id: node.id,
    type: "flowNode",
    position: {
      x: node.position.x,
      y: node.position.y,
    },
    data: node,
    selected: false,
  }));
}

function toReactFlowEdges(edges: FlowEdge[]): Edge[] {
  return edges.map((edge, index) => ({
    id: `edge-${index}-${edge.source}-${edge.target}-${edge.sourceHandle || "default"}`,
    source: edge.source,
    target: edge.target,
    sourceHandle: edge.sourceHandle || null,
    targetHandle: edge.targetHandle || null,
    label: edge.label || undefined,
    type: "smoothstep",
    animated: false,
    style: {
      stroke: "var(--text-muted)",
      strokeWidth: 1.5,
    },
  }));
}

export default function FlowCanvas({
  graph,
  onNodesChange,
  onEdgesChange,
  onConnect,
  onNodeClick,
  onDropNode,
  selectedNodeId,
  nodeTypes,
}: FlowCanvasProps) {
  const { screenToFlowPosition } = useReactFlow();

  const nodes = useMemo(() => {
    const reactFlowNodes = toReactFlowNodes(graph.nodes);
    if (!selectedNodeId) return reactFlowNodes;

    return reactFlowNodes.map((node) => ({
      ...node,
      selected: node.id === selectedNodeId,
    }));
  }, [graph.nodes, selectedNodeId]);

  const edges = useMemo(
    () => toReactFlowEdges(graph.edges),
    [graph.edges],
  );

  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      onNodeClick(node.id);
    },
    [onNodeClick],
  );

  const handleDragOver = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
    },
    [],
  );

  const handleDrop = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      const raw = event.dataTransfer.getData(
        "application/diaglob-flow-node",
      );
      if (!raw) return;

      let descriptor: {
        type: FlowNodeType;
        config?: Partial<FlowNodeConfig>;
      };
      try {
        descriptor = JSON.parse(raw) as {
          type: FlowNodeType;
          config?: Partial<FlowNodeConfig>;
        };
      } catch {
        descriptor = { type: raw as FlowNodeType };
      }

      if (!descriptor.type) return;

      onDropNode(
        descriptor.type,
        screenToFlowPosition({
          x: event.clientX,
          y: event.clientY,
        }),
        descriptor.config,
      );
    },
    [onDropNode, screenToFlowPosition],
  );

  return (
    <div
      className="flow-canvas-container"
      onDragOver={handleDragOver}
      onDrop={handleDrop}
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
          style: {
            stroke: "var(--text-muted)",
            strokeWidth: 1.5,
          },
        }}
      >
        <Background
          color="var(--text-muted)"
          gap={20}
          size={1}
        />
        <Controls />
        <MiniMap
          nodeColor={(node: Node) => {
            const data = node.data as unknown as FlowNodeData;
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
        />
      </ReactFlow>
    </div>
  );
}
