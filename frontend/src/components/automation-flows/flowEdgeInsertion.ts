import {
  addNodeToGraph,
  type FlowGraph,
  type FlowNodeType,
} from "./flowGraphUtils";

export type SequentialNodeType = Extract<FlowNodeType, "wait" | "message" | "tool">;

export interface InsertedNodeResult {
  graph: FlowGraph;
  insertedNodeId: string | null;
}

/** Split only the chosen edge and retain its conditional/call branch metadata. */
export function insertNodeOnEdge(
  graph: FlowGraph,
  edgeIndex: number,
  type: SequentialNodeType,
): InsertedNodeResult {
  const edge = graph.edges[edgeIndex];
  const source = graph.nodes.find((node) => node.id === edge?.source);
  const target = graph.nodes.find((node) => node.id === edge?.target);

  if (!edge || !source || !target
    || !["wait", "message", "tool"].includes(type)) {
    return { graph, insertedNodeId: null };
  }

  const position = {
    x: Math.round((source.position.x + target.position.x) / 2),
    y: Math.round((source.position.y + target.position.y) / 2),
  };
  const withNode = addNodeToGraph(graph, type, position);
  const inserted = withNode.nodes[withNode.nodes.length - 1];
  if (inserted === graph.nodes[graph.nodes.length - 1]) {
    return { graph, insertedNodeId: null };
  }

  return {
    graph: {
      ...withNode,
      edges: [
        ...graph.edges.slice(0, edgeIndex),
        { ...edge, target: inserted.id, targetHandle: undefined },
        { source: inserted.id, target: edge.target },
        ...graph.edges.slice(edgeIndex + 1),
      ],
    },
    insertedNodeId: inserted.id,
  };
}
