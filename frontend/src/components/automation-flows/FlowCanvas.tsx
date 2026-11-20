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
  canWrite: boolean;
  onNodesChange: OnNodesChange;
  onEdgesChange: OnEdgesChange;
  onConnect: (connection: Connection) => void;
  onNodeClick: (nodeId: string) => void;
  onEdgeSelect: (edgeIndex: number) => void;
  onNodeDragStart: () => void;
  onNodeDragStop: () => void;
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
      stroke: "var(--flow-connector)",
      strokeWidth: 1.5,
    },
  }));
}

export default function FlowCanvas({
  graph,
  canWrite,
  onNodesChange,
  onEdgesChange,
  onConnect,
  onNodeClick,
  onEdgeSelect,
  onNodeDragStart,
  onNodeDragStop,
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
        onEdgeClick={(_event, edge) => onEdgeSelect(edges.findIndex((candidate) => candidate.id === edge.id))}
        onNodeDragStart={onNodeDragStart}
        onNodeDragStop={onNodeDragStop}
        nodeTypes={nodeTypes}
        nodesDraggable={canWrite}
        nodesConnectable={canWrite}
        deleteKeyCode={canWrite ? ["Backspace", "Delete"] : null}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{
          type: "smoothstep",
          style: {
            stroke: "var(--flow-connector)",
            strokeWidth: 1.5,
          },
        }}
      >
        <Background
          color="var(--flow-grid)"
          gap={20}
          size={1}
        />
        <Controls />
        <MiniMap
          nodeColor={(node: Node) => {
            const data = node.data as unknown as FlowNodeData;
            const colors: Record<string, string> = {
              trigger: "var(--flow-trigger)",
              wait: "var(--flow-wait)",
              condition: "var(--flow-condition)",
              message: "var(--flow-action)",
              call: "var(--flow-human)",
              tool: "var(--flow-ai)",
              end: "var(--flow-neutral)",
            };
            return colors[data?.type] || "var(--flow-neutral)";
          }}
          maskColor="rgba(0,0,0,0.35)"
        />
      </ReactFlow>
    </div>
  );
}
