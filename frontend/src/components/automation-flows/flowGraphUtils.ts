export type FlowNodeType = "trigger" | "wait" | "message" | "condition" | "end";

export type TriggerType = "manual" | "customer_segment" | "customer_created" | "order_created" | "failed_order";

export type ConditionField = "customer_segment" | "customer_health" | "customer_priority" | "needs_attention" | "needs_followup" | "orders_count" | "country_code" | "successful_order_since_start";

export type ConditionOperator = "equals" | "not_equals" | "gt" | "gte" | "lt" | "lte" | "in" | "not_in" | "is_true" | "is_false";

export type MessageMode = "free_form" | "template" | "auto";

export type FlowNodeStatus = "pending" | "active" | "completed" | "failed" | "waiting" | "ambiguous";

export interface FlowNodeConfig {
  trigger_type?: TriggerType;
  trigger_config?: Record<string, unknown>;
  duration?: number;
  duration_unit?: "minutes" | "hours" | "days";
  condition_field?: ConditionField;
  condition_operator?: ConditionOperator;
  condition_value?: unknown;
  message_mode?: MessageMode;
  message_template?: string;
  template_variables?: Record<string, string>;
  whatsapp_template_id?: number;
  template_provider_name?: string;
  template_language?: string;
  label?: string;
}

export interface FlowNode {
  id: string;
  type: FlowNodeType;
  config: FlowNodeConfig;
  position: { x: number; y: number };
  label?: string;
  [key: string]: unknown;
}

export interface FlowEdge {
  source: string;
  target: string;
  sourceHandle?: string;
  targetHandle?: string;
  label?: string;
}

export interface FlowGraph {
  nodes: FlowNode[];
  edges: FlowEdge[];
}

const NODE_TYPES: FlowNodeType[] = ["trigger", "wait", "message", "condition", "end"];
const TRIGGER_TYPES: TriggerType[] = ["manual", "customer_segment", "customer_created", "order_created", "failed_order"];
const CONDITION_FIELDS: ConditionField[] = ["customer_segment", "customer_health", "customer_priority", "needs_attention", "needs_followup", "orders_count", "country_code", "successful_order_since_start"];
const CONDITION_OPERATORS: ConditionOperator[] = ["equals", "not_equals", "gt", "gte", "lt", "lte", "in", "not_in", "is_true", "is_false"];

export { NODE_TYPES, TRIGGER_TYPES, CONDITION_FIELDS, CONDITION_OPERATORS };

export function validateFlowGraph(graph: FlowGraph): string[] {
  const errors: string[] = [];
  if (!graph.nodes.length) {
    errors.push("flowValidationEmptyGraph");
    return errors;
  }
  const triggerNodes = graph.nodes.filter(n => n.type === "trigger");
  if (triggerNodes.length === 0) errors.push("flowValidationNoTrigger");
  if (triggerNodes.length > 1) errors.push("flowValidationMultipleTriggers");
  if (!graph.nodes.some(n => n.type === "end")) errors.push("flowValidationNoEnd");
  if (graph.nodes.length > 50) errors.push("flowValidationTooManyNodes");
  const messageNodes = graph.nodes.filter(n => n.type === "message");
  if (messageNodes.length > 10) errors.push("flowValidationTooManyMessages");
  const endNodes = graph.nodes.filter(n => n.type === "end");
  for (const endNode of endNodes) {
    const hasOutgoing = graph.edges.some(e => e.source === endNode.id);
    if (hasOutgoing) errors.push("flowValidationEndHasOutgoing");
  }
  for (const node of graph.nodes) {
    if (node.type === "trigger") {
      const hasIncoming = graph.edges.some(e => e.target === node.id);
      if (hasIncoming) errors.push("flowValidationTriggerHasIncoming");
    }
    if (node.type === "condition") {
      const outgoing = graph.edges.filter(e => e.source === node.id);
      const hasTrue = outgoing.some(e => e.sourceHandle === "true");
      const hasFalse = outgoing.some(e => e.sourceHandle === "false");
      if (!hasTrue || !hasFalse) errors.push("flowValidationConditionMissingBranch");
      if (outgoing.length > 2) errors.push("flowValidationConditionTooManyBranches");
    }
    if (node.type !== "condition" && node.type !== "end") {
      const outgoing = graph.edges.filter(e => e.source === node.id);
      if (outgoing.length > 1) errors.push("flowValidationNodeMultipleOutgoing");
    }
  }
  const nodeIds = new Set(graph.nodes.map(n => n.id));
  for (const edge of graph.edges) {
    if (!nodeIds.has(edge.source)) errors.push("flowValidationEdgeInvalidSource");
    if (!nodeIds.has(edge.target)) errors.push("flowValidationEdgeInvalidTarget");
    if (edge.source === edge.target) errors.push("flowValidationSelfEdge");
  }
  if (!hasCycle(graph)) errors.push("flowValidationCycle");
  return errors;
}

function hasCycle(graph: FlowGraph): boolean {
  const adj = new Map<string, string[]>();
  for (const node of graph.nodes) adj.set(node.id, []);
  for (const edge of graph.edges) {
    const list = adj.get(edge.source);
    if (list) list.push(edge.target);
  }
  const visited = new Set<string>();
  const inStack = new Set<string>();
  function dfs(id: string): boolean {
    if (inStack.has(id)) return true;
    if (visited.has(id)) return false;
    visited.add(id);
    inStack.add(id);
    for (const next of (adj.get(id) || [])) {
      if (dfs(next)) return true;
    }
    inStack.delete(id);
    return false;
  }
  for (const node of graph.nodes) {
    if (dfs(node.id)) return true;
  }
  return false;
}

export function createDefaultGraph(): FlowGraph {
  return {
    nodes: [
      { id: "trigger-1", type: "trigger", config: { trigger_type: "manual" }, position: { x: 250, y: 50 } },
      { id: "end-1", type: "end", config: {}, position: { x: 250, y: 450 } },
    ],
    edges: [
      { source: "trigger-1", target: "end-1" },
    ],
  };
}

export function addNodeToGraph(graph: FlowGraph, type: FlowNodeType, position: { x: number; y: number }): FlowGraph {
  const id = `${type}-${Date.now()}`;
  const newNode: FlowNode = { id, type, config: {}, position };
  const newEdges: FlowEdge[] = [];
  const trigger = graph.nodes.find(n => n.type === "trigger");
  if (trigger && type !== "trigger") {
    const triggerEdge = graph.edges.find(e => e.source === trigger.id && e.target === "end-1");
    if (triggerEdge) {
      newEdges.push({ source: trigger.id, target: id });
      newEdges.push({ source: id, target: "end-1" });
    }
    return { nodes: [...graph.nodes, newNode], edges: [...graph.edges.filter(e => !(e.source === trigger.id && e.target === "end-1")), ...newEdges] };
  }
  return { nodes: [...graph.nodes, newNode], edges: [...graph.edges, ...newEdges] };
}

export function updateNodeConfig(graph: FlowGraph, nodeId: string, config: Partial<FlowNodeConfig>): FlowGraph {
  return {
    ...graph,
    nodes: graph.nodes.map(n => n.id === nodeId ? { ...n, config: { ...n.config, ...config } } : n),
  };
}

export function removeNode(graph: FlowGraph, nodeId: string): FlowGraph {
  const node = graph.nodes.find(n => n.id === nodeId);
  if (!node || node.type === "trigger") return graph;
  return {
    nodes: graph.nodes.filter(n => n.id !== nodeId),
    edges: graph.edges.filter(e => e.source !== nodeId && e.target !== nodeId),
  };
}

export function humanizeNodeType(type: FlowNodeType, t: (key: string) => string): string {
  const map: Record<FlowNodeType, string> = {
    trigger: t("flowNodeTypeTrigger"),
    wait: t("flowNodeTypeWait"),
    message: t("flowNodeTypeMessage"),
    condition: t("flowNodeTypeCondition"),
    end: t("flowNodeTypeEnd"),
  };
  return map[type] || type;
}

export function humanizeNodeSummary(node: FlowNode, t: (key: string) => string): string {
  switch (node.type) {
    case "trigger":
      return t(`flowTriggerType_${node.config.trigger_type || "manual"}`);
    case "wait": {
      const d = node.config.duration || 0;
      const u = node.config.duration_unit || "hours";
      return `${t("flowWaitUntil")} ${d} ${t(`flowUnit_${u}`)}`;
    }
    case "condition": {
      const field = node.config.condition_field || "";
      const op = node.config.condition_operator || "";
      const val = node.config.condition_value;
      return `${field} ${op} ${val ?? ""}`.trim();
    }
    case "message": {
      const mode = node.config.message_mode || "auto";
      return `${t(`flowMessageMode_${mode}`)} · WhatsApp`;
    }
    case "end":
      return t("flowNodeTypeEnd");
    default:
      return "";
  }
}

export function serializeFlowGraph(graph: FlowGraph): Record<string, unknown> {
  return {
    nodes: graph.nodes.map(n => ({ id: n.id, type: n.type, config: n.config, position: n.position })),
    edges: graph.edges.map(e => ({ source: e.source, target: e.target, sourceHandle: e.sourceHandle, targetHandle: e.targetHandle, label: e.label })),
  };
}

export function deserializeFlowGraph(data: Record<string, unknown>): FlowGraph {
  const nodes = (data.nodes as Record<string, unknown>[]) || [];
  const edges = (data.edges as Record<string, unknown>[]) || [];
  return {
    nodes: nodes.map((n: Record<string, unknown>) => ({
      id: n.id as string,
      type: n.type as FlowNodeType,
      config: (n.config as FlowNodeConfig) || {},
      position: (n.position as { x: number; y: number }) || { x: 0, y: 0 },
    })),
    edges: edges.map((e: Record<string, unknown>) => ({
      source: e.source as string,
      target: e.target as string,
      sourceHandle: e.sourceHandle as string | undefined,
      targetHandle: e.targetHandle as string | undefined,
      label: e.label as string | undefined,
    })),
  };
}
