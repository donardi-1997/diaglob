export type FlowNodeType = "trigger" | "wait" | "message" | "condition" | "tool" | "end";

export type FlowToolName =
  | "orders.list"
  | "orders.get"
  | "products.list"
  | "customers.search"
  | "tracking.get"
  | "suppliers.cj.search"
  | "suppliers.cj.quote"
  | "analytics.summary";

export type TriggerType =
  | "manual"
  | "customer_segment"
  | "customer_created"
  | "order_created"
  | "failed_order";

export type ConditionField =
  | "customer.segment"
  | "customer.health"
  | "customer.priority"
  | "customer.needs_attention"
  | "customer.needs_followup"
  | "customer.order_count"
  | "customer.country"
  | "has_successful_order_since_flow_start";

export type ConditionOperator =
  | "equals"
  | "not_equals"
  | "greater_than"
  | "greater_or_equal"
  | "less_than"
  | "less_or_equal"
  | "in"
  | "not_in"
  | "is_true"
  | "is_false";

export type MessageMode = "free_form" | "template" | "auto";

export type FlowNodeStatus =
  | "pending"
  | "active"
  | "completed"
  | "failed"
  | "waiting"
  | "ambiguous";

export interface FlowNodeConfig {
  trigger_type?: TriggerType;
  trigger_config?: Record<string, unknown>;

  value?: unknown;
  unit?: "minutes" | "hours" | "days";

  field?: ConditionField;
  operator?: ConditionOperator;

  message_mode?: MessageMode;
  message_template?: string;
  template_variables?: Record<string, string>;
  whatsapp_template_id?: number;
  template_provider_name?: string;
  template_language?: string;

  tool_name?: FlowToolName;
  arguments?: Record<string, unknown>;

  label?: string;
}

export interface FlowNodeDebug {
  status:
    | "pending"
    | "running"
    | "completed"
    | "failed"
    | "skipped"
    | "ambiguous"
    | "waiting";
  label?: string;
  duration_ms?: number | null;
  executions?: number;
  error?: string | null;
}

export interface FlowNode {
  id: string;
  type: FlowNodeType;
  config: FlowNodeConfig;
  position: { x: number; y: number };
  label?: string;
  debug?: FlowNodeDebug;
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

const NODE_TYPES: FlowNodeType[] = [
  "trigger",
  "wait",
  "message",
  "condition",
  "tool",
  "end",
];

const TRIGGER_TYPES: TriggerType[] = [
  "manual",
  "customer_segment",
  "customer_created",
  "order_created",
  "failed_order",
];

const CONDITION_FIELDS: ConditionField[] = [
  "customer.segment",
  "customer.health",
  "customer.priority",
  "customer.needs_attention",
  "customer.needs_followup",
  "customer.order_count",
  "customer.country",
  "has_successful_order_since_flow_start",
];

const CONDITION_OPERATORS: ConditionOperator[] = [
  "equals",
  "not_equals",
  "greater_than",
  "greater_or_equal",
  "less_than",
  "less_or_equal",
  "in",
  "not_in",
  "is_true",
  "is_false",
];

export {
  NODE_TYPES,
  TRIGGER_TYPES,
  CONDITION_FIELDS,
  CONDITION_OPERATORS,
};

const LEGACY_FIELD_MAP: Record<string, ConditionField> = {
  customer_segment: "customer.segment",
  customer_health: "customer.health",
  customer_priority: "customer.priority",
  needs_attention: "customer.needs_attention",
  needs_followup: "customer.needs_followup",
  orders_count: "customer.order_count",
  country_code: "customer.country",
  successful_order_since_start: "has_successful_order_since_flow_start",
};

const LEGACY_OPERATOR_MAP: Record<string, ConditionOperator> = {
  gt: "greater_than",
  gte: "greater_or_equal",
  lt: "less_than",
  lte: "less_or_equal",
};

export function defaultConfigForNode(type: FlowNodeType): FlowNodeConfig {
  switch (type) {
    case "trigger":
      return { trigger_type: "manual" };
    case "wait":
      return { value: 1, unit: "hours" };
    case "condition":
      return {
        field: "customer.order_count",
        operator: "greater_than",
        value: 0,
      };
    case "message":
      return {
        message_mode: "auto",
        message_template: "Hola {{customer.name}}",
      };
    case "tool":
      return {
        tool_name: "analytics.summary",
        arguments: {},
      };
    case "end":
      return {};
  }
}

function edgeBranch(edge: FlowEdge): string | undefined {
  return edge.label || edge.sourceHandle;
}

export function validateFlowGraph(graph: FlowGraph): string[] {
  const errors: string[] = [];

  if (!graph.nodes.length) {
    errors.push("flowValidationEmptyGraph");
    return errors;
  }

  const triggerNodes = graph.nodes.filter((node) => node.type === "trigger");
  if (triggerNodes.length === 0) errors.push("flowValidationNoTrigger");
  if (triggerNodes.length > 1) errors.push("flowValidationMultipleTriggers");
  if (!graph.nodes.some((node) => node.type === "end")) {
    errors.push("flowValidationNoEnd");
  }
  if (graph.nodes.length > 50) errors.push("flowValidationTooManyNodes");

  const messageNodes = graph.nodes.filter((node) => node.type === "message");
  if (messageNodes.length > 10) {
    errors.push("flowValidationTooManyMessages");
  }

  const nodeIds = new Set(graph.nodes.map((node) => node.id));
  if (nodeIds.size !== graph.nodes.length) {
    errors.push("flowValidationDuplicateNodeIds");
  }

  for (const node of graph.nodes) {
    const incoming = graph.edges.filter((edge) => edge.target === node.id);
    const outgoing = graph.edges.filter((edge) => edge.source === node.id);

    if (node.type === "trigger" && incoming.length > 0) {
      errors.push("flowValidationTriggerHasIncoming");
    }

    if (node.type === "end" && outgoing.length > 0) {
      errors.push("flowValidationEndHasOutgoing");
    }

    if (node.type === "condition") {
      const branches = outgoing.map(edgeBranch);
      if (!branches.includes("true") || !branches.includes("false")) {
        errors.push("flowValidationConditionMissingBranch");
      }
      if (outgoing.length > 2) {
        errors.push("flowValidationConditionTooManyBranches");
      }
    }

    if (node.type === "tool") {
      if (!node.config.tool_name) {
        errors.push("flowValidationToolMissingName");
      }
      if (
        node.config.arguments != null
        && (
          typeof node.config.arguments !== "object"
          || Array.isArray(node.config.arguments)
        )
      ) {
        errors.push("flowValidationToolInvalidArguments");
      }
    }

    if (node.type !== "condition" && node.type !== "end") {
      if (outgoing.length === 0) {
        errors.push("flowValidationMissingOutgoing");
      }
      if (outgoing.length > 1) {
        errors.push("flowValidationNodeMultipleOutgoing");
      }
    }
  }

  for (const edge of graph.edges) {
    if (!nodeIds.has(edge.source)) {
      errors.push("flowValidationEdgeInvalidSource");
    }
    if (!nodeIds.has(edge.target)) {
      errors.push("flowValidationEdgeInvalidTarget");
    }
    if (edge.source === edge.target) {
      errors.push("flowValidationSelfEdge");
    }
  }

  if (hasCycle(graph)) {
    errors.push("flowValidationCycle");
  }

  const reachable = reachableFromTrigger(graph);
  if (reachable.size && reachable.size !== graph.nodes.length) {
    errors.push("flowValidationOrphanNodes");
  }

  return [...new Set(errors)];
}

function hasCycle(graph: FlowGraph): boolean {
  const adjacency = new Map<string, string[]>();
  for (const node of graph.nodes) adjacency.set(node.id, []);
  for (const edge of graph.edges) {
    const list = adjacency.get(edge.source);
    if (list) list.push(edge.target);
  }

  const visited = new Set<string>();
  const inStack = new Set<string>();

  function dfs(id: string): boolean {
    if (inStack.has(id)) return true;
    if (visited.has(id)) return false;

    visited.add(id);
    inStack.add(id);

    for (const next of adjacency.get(id) || []) {
      if (dfs(next)) return true;
    }

    inStack.delete(id);
    return false;
  }

  return graph.nodes.some((node) => dfs(node.id));
}

function reachableFromTrigger(graph: FlowGraph): Set<string> {
  const trigger = graph.nodes.find((node) => node.type === "trigger");
  if (!trigger) return new Set();

  const adjacency = new Map<string, string[]>();
  for (const edge of graph.edges) {
    const list = adjacency.get(edge.source) || [];
    list.push(edge.target);
    adjacency.set(edge.source, list);
  }

  const visited = new Set<string>();
  const queue = [trigger.id];

  while (queue.length) {
    const id = queue.shift();
    if (!id || visited.has(id)) continue;
    visited.add(id);
    queue.push(...(adjacency.get(id) || []));
  }

  return visited;
}

export function createDefaultGraph(): FlowGraph {
  return {
    nodes: [
      {
        id: "trigger-1",
        type: "trigger",
        config: defaultConfigForNode("trigger"),
        position: { x: 260, y: 60 },
      },
      {
        id: "end-1",
        type: "end",
        config: defaultConfigForNode("end"),
        position: { x: 260, y: 430 },
      },
    ],
    edges: [{ source: "trigger-1", target: "end-1" }],
  };
}

export function addNodeToGraph(
  graph: FlowGraph,
  type: FlowNodeType,
  position: { x: number; y: number },
  config?: Partial<FlowNodeConfig>,
): FlowGraph {
  if (type === "trigger" && graph.nodes.some((node) => node.type === "trigger")) {
    return graph;
  }

  const base = `${type}-${Date.now().toString(36)}`;
  let id = base;
  let suffix = 1;
  const existing = new Set(graph.nodes.map((node) => node.id));
  while (existing.has(id)) {
    id = `${base}-${suffix++}`;
  }

  return {
    ...graph,
    nodes: [
      ...graph.nodes,
      {
        id,
        type,
        config: {
          ...defaultConfigForNode(type),
          ...(config || {}),
        },
        position,
      },
    ],
  };
}

export function updateNodeConfig(
  graph: FlowGraph,
  nodeId: string,
  config: Partial<FlowNodeConfig>,
): FlowGraph {
  return {
    ...graph,
    nodes: graph.nodes.map((node) =>
      node.id === nodeId
        ? { ...node, config: { ...node.config, ...config } }
        : node,
    ),
  };
}

export function removeNode(graph: FlowGraph, nodeId: string): FlowGraph {
  const node = graph.nodes.find((candidate) => candidate.id === nodeId);
  if (!node || node.type === "trigger") return graph;

  return {
    nodes: graph.nodes.filter((candidate) => candidate.id !== nodeId),
    edges: graph.edges.filter(
      (edge) => edge.source !== nodeId && edge.target !== nodeId,
    ),
  };
}

export function humanizeNodeType(
  type: FlowNodeType,
  t: (key: string) => string,
): string {
  const map: Record<FlowNodeType, string> = {
    trigger: t("flowNodeTypeTrigger"),
    wait: t("flowNodeTypeWait"),
    message: t("flowNodeTypeMessage"),
    condition: t("flowNodeTypeCondition"),
    tool: t("flowNodeTypeTool"),
    end: t("flowNodeTypeEnd"),
  };
  return map[type] || type;
}

export function humanizeNodeSummary(
  node: FlowNode,
  t: (key: string) => string,
): string {
  switch (node.type) {
    case "trigger":
      return t(`flowTriggerType_${node.config.trigger_type || "manual"}`);
    case "wait": {
      const value = Number(node.config.value ?? 1);
      const unit = node.config.unit || "hours";
      return `${value} ${t(`flowUnit_${unit}`)}`;
    }
    case "condition":
      return `${node.config.field || ""} ${node.config.operator || ""} ${String(node.config.value ?? "")}`.trim();
    case "message":
      return (
        node.config.message_template
        || `${t(`flowMessageMode_${node.config.message_mode || "auto"}`)} · WhatsApp`
      );
    case "tool":
      return node.config.tool_name || t("flowNodeTypeTool");
    case "end":
      return node.config.label || t("flowNodeTypeEnd");
  }
}

function normalizeLegacyConfig(
  type: FlowNodeType,
  input: Record<string, unknown>,
): FlowNodeConfig {
  const config: Record<string, unknown> = { ...input };

  if (type === "wait") {
    if (config.value == null && config.duration != null) {
      config.value = config.duration;
    }
    if (!config.unit && config.duration_unit) {
      config.unit = config.duration_unit;
    }
    delete config.duration;
    delete config.duration_unit;
  }

  if (type === "condition") {
    const legacyField = String(config.condition_field || "");
    if (!config.field && legacyField) {
      config.field = LEGACY_FIELD_MAP[legacyField] || legacyField;
    }

    const legacyOperator = String(config.condition_operator || "");
    if (!config.operator && legacyOperator) {
      config.operator = LEGACY_OPERATOR_MAP[legacyOperator] || legacyOperator;
    }

    if (config.value == null && config.condition_value !== undefined) {
      config.value = config.condition_value;
    }

    delete config.condition_field;
    delete config.condition_operator;
    delete config.condition_value;
  }

  if (type === "message") {
    if (!config.message_template && config.label) {
      config.message_template = config.label;
    }
  }

  return config as FlowNodeConfig;
}

export function serializeFlowGraph(
  graph: FlowGraph,
): Record<string, unknown> {
  return {
    nodes: graph.nodes.map((node) => ({
      id: node.id,
      type: node.type,
      config: normalizeLegacyConfig(
        node.type,
        node.config as Record<string, unknown>,
      ),
      position: node.position,
    })),
    edges: graph.edges.map((edge) => ({
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle,
      targetHandle: edge.targetHandle,
      label: edge.label || edge.sourceHandle,
    })),
  };
}

export function deserializeFlowGraph(
  data: Record<string, unknown>,
): FlowGraph {
  const nodes = (data.nodes as Record<string, unknown>[]) || [];
  const edges = (data.edges as Record<string, unknown>[]) || [];

  return {
    nodes: nodes.map((node) => {
      const type = node.type as FlowNodeType;
      return {
        id: node.id as string,
        type,
        config: normalizeLegacyConfig(
          type,
          (node.config as Record<string, unknown>) || {},
        ),
        position:
          (node.position as { x: number; y: number })
          || { x: 0, y: 0 },
      };
    }),
    edges: edges.map((edge) => ({
      source: edge.source as string,
      target: edge.target as string,
      sourceHandle: edge.sourceHandle as string | undefined,
      targetHandle: edge.targetHandle as string | undefined,
      label:
        (edge.label as string | undefined)
        || (edge.sourceHandle as string | undefined),
    })),
  };
}
