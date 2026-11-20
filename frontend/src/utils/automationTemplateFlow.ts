/** Read the authoritative flow ID returned by POST /automation-flow-templates/{id}. */
export function createdTemplateFlowId(response: unknown): number {
  if (typeof response !== "object" || response === null || !("flow" in response)) {
    throw new Error("Template creation did not return a flow");
  }
  const flow = response.flow;
  if (typeof flow !== "object" || flow === null || !("id" in flow)) {
    throw new Error("Template creation did not return a flow ID");
  }
  const id = flow.id;
  if (typeof id !== "number" || !Number.isSafeInteger(id) || id <= 0) {
    throw new Error("Template creation returned an invalid flow ID");
  }
  return id;
}

export type TemplateStepType = "trigger" | "wait" | "condition" | "message" | "call" | "tool" | "end";

const KNOWN_STEPS: ReadonlySet<string> = new Set([
  "trigger", "wait", "condition", "message", "call", "tool", "end",
]);

/** Preserve the visible order from the template without exposing config/PII. */
export function templateGraphSteps(graph: Record<string, unknown>): TemplateStepType[] {
  const nodes = graph.nodes;
  if (!Array.isArray(nodes)) return [];
  const steps: TemplateStepType[] = [];
  for (const node of nodes) {
    if (typeof node !== "object" || node === null || !("type" in node)) continue;
    const type = node.type;
    if (typeof type === "string" && KNOWN_STEPS.has(type)) {
      steps.push(type as TemplateStepType);
    }
  }
  return steps;
}
