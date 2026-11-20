/**
 * Approved WhatsApp (Meta) templates inside flow message nodes.
 *
 * Mirrors backend `whatsapp_compliance.FLOW_TEMPLATE_VARIABLES`: event-driven
 * flows can fill template parameters with order/shipment data. Contact
 * details and street addresses are intentionally not offered.
 */
export const FLOW_TEMPLATE_VARIABLES = [
  "customer.name",
  "customer.segment",
  "customer.health",
  "store.name",
  "order.number",
  "order.total",
  "order.total_display",
  "order.currency",
  "order.items_summary",
  "order.payment_method",
  "order.payment_status",
  "order.fulfillment_status",
  "order.shipping.city",
  "shipment.carrier",
  "shipment.tracking_number",
  "shipment.last_mile_tracking_number",
  "shipment.status",
  "shipment.delivery_days",
  "shipment.tracking_url",
] as const;

export type FlowTemplateVariable = (typeof FLOW_TEMPLATE_VARIABLES)[number];

export interface TemplateLike {
  components?: Record<string, unknown> | null;
}

/** BODY text of a synced Meta template, e.g. "Hola {{1}}, tu pedido {{2}}…". */
export function templateBodyText(template: TemplateLike | null | undefined): string {
  const items = template?.components?.items;
  if (!Array.isArray(items)) return "";
  for (const component of items) {
    if (
      component
      && typeof component === "object"
      && String((component as { type?: unknown }).type ?? "").toUpperCase() === "BODY"
    ) {
      return String((component as { text?: unknown }).text ?? "");
    }
  }
  return "";
}

/** Number of distinct {{n}} parameters Meta expects in the BODY. */
export function templateParameterCount(template: TemplateLike | null | undefined): number {
  const matches = templateBodyText(template).match(/\{\{\s*(\d+)\s*\}\}/g) ?? [];
  return new Set(matches.map((item) => item.replace(/[{}\s]/g, ""))).size;
}

/**
 * Resize a body-variable mapping to the template's parameter count, keeping
 * the existing choices and defaulting new slots to the customer name.
 */
export function resizeTemplateMapping(
  current: string[] | undefined,
  count: number,
): string[] {
  const base = Array.isArray(current) ? current : [];
  return Array.from({ length: count }, (_, index) => base[index] || "customer.name");
}

/** Preview the BODY with each {{n}} replaced by its mapped variable name. */
export function previewTemplateBody(body: string, mapping: string[]): string {
  return body.replace(/\{\{\s*(\d+)\s*\}\}/g, (match, raw: string) => {
    const variable = mapping[Number(raw) - 1];
    return variable ? `[${variable}]` : match;
  });
}

/** Client-side mirror of the backend message-node checks, for inline hints. */
export function templateConfigIssue(config: {
  message_mode?: string;
  message_template?: string;
  whatsapp_template_id?: number;
  template_variables?: { body?: string[] };
}, template: TemplateLike & { status?: string } | null | undefined): string | null {
  const mode = config.message_mode || "auto";
  if (mode === "template" && !config.whatsapp_template_id) return "template_required";
  if (mode !== "template" && !(config.message_template || "").trim()) return "text_required";
  if (!config.whatsapp_template_id) return null;
  if (template && template.status !== "approved") return "template_not_approved";
  const mapping = config.template_variables?.body ?? [];
  if (template && templateParameterCount(template) !== mapping.length) return "parameter_mismatch";
  const allowed = new Set<string>(FLOW_TEMPLATE_VARIABLES);
  if (mapping.some((item) => !allowed.has(item))) return "unsupported_variable";
  return null;
}
