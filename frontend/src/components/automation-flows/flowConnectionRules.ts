import type { FlowEdge, FlowGraph } from "./flowGraphUtils";

export interface FlowConnectionInput {
  source: string | null;
  target: string | null;
  sourceHandle?: string | null;
  targetHandle?: string | null;
}

export type FlowConnectionError =
  | "missing-node"
  | "self-loop"
  | "trigger-target"
  | "end-source"
  | "invalid-handle"
  | "cycle";

export interface FlowConnectionResult {
  graph: FlowGraph;
  error: FlowConnectionError | null;
}

const CALL_BRANCHES = new Set([
  "confirmed",
  "rejected",
  "no_answer",
  "failed",
]);

const CONDITION_BRANCHES = new Set(["true", "false"]);

function pathExists(edges: FlowEdge[], start: string, destination: string): boolean {
  const visited = new Set<string>();
  const pending = [start];

  while (pending.length) {
    const id = pending.pop()!;
    if (id === destination) return true;
    if (visited.has(id)) continue;
    visited.add(id);
    for (const edge of edges) {
      if (edge.source === id && !visited.has(edge.target)) {
        pending.push(edge.target);
      }
    }
  }
  return false;
}

/**
 * Validate one editor interaction without requiring the entire draft to be
 * publishable. Invalid replacements must preserve the existing branch.
 */
export function connectFlowNodes(
  graph: FlowGraph,
  connection: FlowConnectionInput,
): FlowConnectionResult {
  const reject = (error: FlowConnectionError): FlowConnectionResult => ({
    graph,
    error,
  });

  const source = graph.nodes.find((node) => node.id === connection.source);
  const target = graph.nodes.find((node) => node.id === connection.target);
  if (!source || !target) return reject("missing-node");
  if (source.id === target.id) return reject("self-loop");
  if (target.type === "trigger") return reject("trigger-target");
  if (source.type === "end") return reject("end-source");
  if (connection.targetHandle) return reject("invalid-handle");

  const handle = connection.sourceHandle || undefined;
  const branches = source.type === "condition"
    ? CONDITION_BRANCHES
    : source.type === "call"
      ? CALL_BRANCHES
      : null;

  if (branches ? !handle || !branches.has(handle) : Boolean(handle)) {
    return reject("invalid-handle");
  }

  // A regular node has one output. A condition/call has one output per branch.
  // Keep all other outgoing branches intact when replacing an existing edge.
  const remaining = graph.edges.filter((edge) => {
    if (edge.source !== source.id) return true;
    return branches
      ? (edge.sourceHandle || edge.label) !== handle
      : false;
  });
  const nextEdge: FlowEdge = {
    source: source.id,
    target: target.id,
    ...(handle ? { sourceHandle: handle, label: handle } : {}),
  };

  const existingBranch = graph.edges.filter((edge) =>
    edge.source === source.id
    && (!branches || (edge.sourceHandle || edge.label) === handle)
  );
  if (existingBranch.length === 1
    && existingBranch[0].target === target.id
    && (existingBranch[0].sourceHandle || existingBranch[0].label || undefined) === handle) {
    return { graph, error: null };
  }

  // Check the final edge set after replacement, not the old graph, so
  // reconnecting a branch does not give a false-positive cycle error.
  if (pathExists(remaining, target.id, source.id)) {
    return reject("cycle");
  }

  return {
    graph: { ...graph, edges: [...remaining, nextEdge] },
    error: null,
  };
}
