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
