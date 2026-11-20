/** Pure helpers for the "use model" setup wizard (no React, unit-tested). */

export interface SuggestedMetaTemplate {
  name: string;
  category: "UTILITY" | "MARKETING" | string;
  language: string;
  body: string;
  variables: string[];
}

export interface ModelWhatsAppSetup {
  node_id: string;
  suggested_template: SuggestedMetaTemplate;
}

export interface ModelSetupState {
  name: string;
  whatsappTemplateId: number | null;
  mapping: string[];
  messageMode: "auto" | "template";
  activate: boolean;
}

export interface ModelSetupPayload {
  name?: string;
  whatsapp_template_id?: number;
  template_variables?: { body: string[] };
  message_mode?: "auto" | "template";
  activate: boolean;
}

/**
 * Parameters for a chosen Meta template: keep the model's suggestion for each
 * position and fall back to the customer name for extra parameters.
 */
export function suggestedMapping(suggested: string[] | undefined, count: number): string[] {
  const base = Array.isArray(suggested) ? suggested : [];
  return Array.from({ length: Math.max(0, count) }, (_, index) => base[index] || "customer.name");
}

/** Request body for POST /automation-flow-templates/{id}. */
export function buildModelSetupPayload(state: ModelSetupState, modelName: string): ModelSetupPayload {
  const payload: ModelSetupPayload = { activate: state.activate };
  const name = state.name.trim();
  if (name && name !== modelName) payload.name = name;
  if (state.whatsappTemplateId) {
    payload.whatsapp_template_id = state.whatsappTemplateId;
    payload.template_variables = { body: [...state.mapping] };
    payload.message_mode = state.messageMode;
  }
  return payload;
}

/** Text to paste in Meta's template editor, plus what each {{n}} means. */
export function suggestedTemplateClipboard(template: SuggestedMetaTemplate): string {
  const legend = template.variables
    .map((variable, index) => `{{${index + 1}}} = ${variable}`)
    .join("\n");
  return [
    `Nombre: ${template.name}`,
    `Categoría: ${template.category}`,
    `Idioma: ${template.language}`,
    "",
    template.body,
    "",
    "Ejemplos de parámetros:",
    legend,
  ].join("\n");
}

const KNOWN_SETUP_ERRORS = new Set([
  "FLOW_TEMPLATE_NOT_FOUND",
  "FLOW_TEMPLATE_INTEGRATION_REQUIRED",
  "WHATSAPP_NOT_CONNECTED",
  "WHATSAPP_TEMPLATE_NOT_FOUND",
  "WHATSAPP_TEMPLATE_NOT_APPROVED",
  "WHATSAPP_TEMPLATE_REQUIRED",
  "TEMPLATE_PARAMETER_COUNT_MISMATCH",
  "TEMPLATE_VARIABLES_INVALID",
  "TEMPLATE_VARIABLES_UNSUPPORTED",
  "TEMPLATE_HAS_NO_WHATSAPP_MESSAGE",
  "TEMPLATE_MESSAGE_NODE_MISSING",
  "MESSAGE_MODE_INVALID",
]);

/** i18n key for an API error; never surfaces raw HTTP/provider text. */
export function modelSetupErrorKey(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  const code = detail && typeof detail === "object" ? (detail as { code?: unknown }).code : undefined;
  if (typeof code === "string" && KNOWN_SETUP_ERRORS.has(code)) return `autoModelError_${code}`;
  const status = (error as { response?: { status?: number } })?.response?.status;
  if (status === 403) return "autoModelError_FORBIDDEN";
  if (status === 409 || status === 422) return "autoModelError_INVALID_FLOW";
  return "autoModelError_GENERIC";
}
