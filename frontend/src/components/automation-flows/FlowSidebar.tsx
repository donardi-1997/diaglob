import {
  Clock,
  GitBranch,
  MessageSquare,
  Square,
  Trash2,
  Wrench,
  X,
  Zap,
} from "lucide-react";
import type {
  FlowNode,
  FlowNodeConfig,
  FlowToolName,
} from "./flowGraphUtils";
import {
  CONDITION_FIELDS,
  CONDITION_OPERATORS,
  TRIGGER_TYPES,
  humanizeNodeType,
} from "./flowGraphUtils";
import {
  FLOW_RUNTIME_VARIABLES,
  FLOW_TOOL_CATALOG,
  getFlowToolCatalogItem,
} from "./flowToolCatalog";

interface FlowSidebarProps {
  node: FlowNode | null;
  onUpdate: (
    nodeId: string,
    config: Partial<FlowNodeConfig>,
  ) => void;
  onDelete: (nodeId: string) => void;
  onClose: () => void;
  t: (key: string) => string;
  canWrite: boolean;
}

const TRIGGER_LABELS: Record<string, string> = {
  manual: "flowTriggerType_manual",
  customer_segment: "flowTriggerType_customer_segment",
  customer_created: "flowTriggerType_customer_created",
  order_created: "flowTriggerType_order_created",
  failed_order: "flowTriggerType_failed_order",
  post_sales_case_created: "flowTriggerType_post_sales_case_created",
  post_sales_case_updated: "flowTriggerType_post_sales_case_updated",
  post_sales_case_resolved: "flowTriggerType_post_sales_case_resolved",
  shipment_created: "flowTriggerType_shipment_created",
  shipment_in_transit: "flowTriggerType_shipment_in_transit",
  shipment_out_for_delivery: "flowTriggerType_shipment_out_for_delivery",
  shipment_delivered: "flowTriggerType_shipment_delivered",
  shipment_delayed: "flowTriggerType_shipment_delayed",
  shipment_failed: "flowTriggerType_shipment_failed",
  shipment_delivery_exception: "flowTriggerType_shipment_delivery_exception",
  shipment_returned: "flowTriggerType_shipment_returned",
};

const FIELD_LABELS: Record<string, string> = {
  "customer.segment": "flowField_customer_segment",
  "customer.health": "flowField_customer_health",
  "customer.priority": "flowField_customer_priority",
  "customer.needs_attention": "flowField_needs_attention",
  "customer.needs_followup": "flowField_needs_followup",
  "customer.order_count": "flowField_orders_count",
  "customer.country": "flowField_country_code",
  has_successful_order_since_flow_start:
    "flowField_successful_order_since_start",
};

const OPERATOR_LABELS: Record<string, string> = {
  equals: "flowOperator_equals",
  not_equals: "flowOperator_not_equals",
  greater_than: "flowOperator_gt",
  greater_or_equal: "flowOperator_gte",
  less_than: "flowOperator_lt",
  less_or_equal: "flowOperator_lte",
  in: "flowOperator_in",
  not_in: "flowOperator_not_in",
  is_true: "flowOperator_is_true",
  is_false: "flowOperator_is_false",
};

const NODE_ICONS: Record<string, typeof Zap> = {
  trigger: Zap,
  wait: Clock,
  message: MessageSquare,
  condition: GitBranch,
  tool: Wrench,
  end: Square,
};

const BOOLEAN_FIELDS = new Set([
  "customer.needs_attention",
  "customer.needs_followup",
  "has_successful_order_since_flow_start",
]);

const NUMERIC_FIELDS = new Set(["customer.order_count"]);

function updateToolArgument(
  node: FlowNode,
  key: string,
  value: unknown,
  onUpdate: FlowSidebarProps["onUpdate"],
) {
  onUpdate(node.id, {
    arguments: {
      ...(node.config.arguments || {}),
      [key]: value,
    },
  });
}

export default function FlowSidebar({
  node,
  onUpdate,
  onDelete,
  onClose,
  t,
  canWrite,
}: FlowSidebarProps) {
  const isOpen = node !== null;
  const Icon = node ? NODE_ICONS[node.type] || Square : Square;
  const tool = node?.type === "tool"
    ? getFlowToolCatalogItem(node.config.tool_name)
    : undefined;

  return (
    <div
      className="flow-sidebar"
      style={{
        position: "fixed",
        top: 0,
        right: 0,
        height: "100vh",
        width: 400,
        background: "var(--bg)",
        borderLeft: "1px solid var(--border)",
        zIndex: 50,
        transition: "transform 200ms ease",
        transform: isOpen ? "translateX(0)" : "translateX(100%)",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        boxShadow: isOpen
          ? "-8px 0 30px rgba(0,0,0,0.15)"
          : "none",
      }}
    >
      {node && (
        <>
          <div className="flow-sidebar-header">
            <div>
              <Icon size={18} />
              <div>
                <span>Configuración</span>
                <h3>{humanizeNodeType(node.type, t)}</h3>
              </div>
            </div>
            <button
              className="icon-button"
              onClick={onClose}
              aria-label="Cerrar inspector"
            >
              <X size={16} />
            </button>
          </div>

          <div className="management-form flow-sidebar-form">
            {node.type === "trigger" && (
              <label>
                <span>{t("flowTriggerType")}</span>
                <select
                  value={node.config.trigger_type || "manual"}
                  onChange={(event) =>
                    canWrite
                    && onUpdate(node.id, {
                      trigger_type:
                        event.target.value as FlowNodeConfig["trigger_type"],
                    })}
                  disabled={!canWrite}
                >
                  {TRIGGER_TYPES.map((triggerType) => (
                    <option key={triggerType} value={triggerType}>
                      {t(TRIGGER_LABELS[triggerType] || triggerType)}
                    </option>
                  ))}
                </select>
              </label>
            )}

            {node.type === "wait" && (
              <>
                <label>
                  <span>{t("flowDuration")}</span>
                  <input
                    type="number"
                    min={1}
                    value={Number(node.config.value ?? 1)}
                    onChange={(event) =>
                      canWrite
                      && onUpdate(node.id, {
                        value:
                          Math.max(
                            1,
                            Number(event.target.value) || 1,
                          ),
                      })}
                    disabled={!canWrite}
                  />
                </label>
                <label>
                  <span>{t("flowDurationUnit")}</span>
                  <select
                    value={node.config.unit || "hours"}
                    onChange={(event) =>
                      canWrite
                      && onUpdate(node.id, {
                        unit:
                          event.target.value as FlowNodeConfig["unit"],
                      })}
                    disabled={!canWrite}
                  >
                    <option value="minutes">
                      {t("flowUnit_minutes")}
                    </option>
                    <option value="hours">
                      {t("flowUnit_hours")}
                    </option>
                    <option value="days">
                      {t("flowUnit_days")}
                    </option>
                  </select>
                </label>
              </>
            )}

            {node.type === "condition" && (
              <>
                <label>
                  <span>{t("flowConditionField")}</span>
                  <select
                    value={node.config.field || ""}
                    onChange={(event) => {
                      if (!canWrite) return;

                      const field =
                        event.target.value as FlowNodeConfig["field"];
                      const patch: Partial<FlowNodeConfig> = { field };

                      if (field && BOOLEAN_FIELDS.has(field)) {
                        patch.operator = "is_true";
                        patch.value = true;
                      } else if (field && NUMERIC_FIELDS.has(field)) {
                        patch.operator = "greater_than";
                        patch.value = 0;
                      } else {
                        patch.operator = "equals";
                        patch.value = "";
                      }

                      onUpdate(node.id, patch);
                    }}
                    disabled={!canWrite}
                  >
                    <option value="">{t("flowSelectField")}</option>
                    {CONDITION_FIELDS.map((field) => (
                      <option key={field} value={field}>
                        {t(FIELD_LABELS[field] || field)}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  <span>{t("flowConditionOperator")}</span>
                  <select
                    value={node.config.operator || "equals"}
                    onChange={(event) =>
                      canWrite
                      && onUpdate(node.id, {
                        operator:
                          event.target.value as FlowNodeConfig["operator"],
                      })}
                    disabled={!canWrite}
                  >
                    {CONDITION_OPERATORS.map((operator) => (
                      <option key={operator} value={operator}>
                        {t(OPERATOR_LABELS[operator] || operator)}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  <span>{t("flowConditionValue")}</span>
                  {BOOLEAN_FIELDS.has(node.config.field || "") ? (
                    <select
                      value={String(node.config.value ?? true)}
                      onChange={(event) =>
                        canWrite
                        && onUpdate(node.id, {
                          value: event.target.value === "true",
                          operator:
                            event.target.value === "true"
                              ? "is_true"
                              : "is_false",
                        })}
                      disabled={!canWrite}
                    >
                      <option value="true">
                        {t("flowOperator_is_true")}
                      </option>
                      <option value="false">
                        {t("flowOperator_is_false")}
                      </option>
                    </select>
                  ) : NUMERIC_FIELDS.has(
                    node.config.field || "",
                  ) ? (
                    <input
                      type="number"
                      value={Number(node.config.value ?? 0)}
                      onChange={(event) =>
                        canWrite
                        && onUpdate(node.id, {
                          value: Number(event.target.value),
                        })}
                      disabled={!canWrite}
                    />
                  ) : (
                    <input
                      type="text"
                      value={String(node.config.value ?? "")}
                      onChange={(event) =>
                        canWrite
                        && onUpdate(node.id, {
                          value: event.target.value,
                        })}
                      disabled={!canWrite}
                      placeholder={t("flowEnterValue")}
                    />
                  )}
                </label>
              </>
            )}

            {node.type === "message" && (
              <>
                <label>
                  <span>{t("flowMessageMode")}</span>
                  <select
                    value={node.config.message_mode || "auto"}
                    onChange={(event) =>
                      canWrite
                      && onUpdate(node.id, {
                        message_mode:
                          event.target.value as FlowNodeConfig["message_mode"],
                      })}
                    disabled={!canWrite}
                  >
                    <option value="free_form">
                      {t("flowMessageMode_free_form")}
                    </option>
                    <option value="template">
                      {t("flowMessageMode_template")}
                    </option>
                    <option value="auto">
                      {t("flowMessageMode_auto")}
                    </option>
                  </select>
                </label>

                <label>
                  <span>{t("flowMessageLabel")}</span>
                  <textarea
                    rows={5}
                    value={node.config.message_template || ""}
                    onChange={(event) =>
                      canWrite
                      && onUpdate(node.id, {
                        message_template: event.target.value,
                      })}
                    disabled={!canWrite}
                    placeholder={t("flowMessagePlaceholder")}
                  />
                </label>

                {node.config.message_mode === "template" && (
                  <small className="flow-field-hint">
                    {t("flowTemplateHint")}
                  </small>
                )}
              </>
            )}

            {node.type === "tool" && (
              <>
                <label>
                  <span>Herramienta</span>
                  <select
                    value={node.config.tool_name || "analytics.summary"}
                    onChange={(event) => {
                      if (!canWrite) return;
                      const next = getFlowToolCatalogItem(
                        event.target.value,
                      );
                      onUpdate(node.id, {
                        tool_name:
                          event.target.value as FlowToolName,
                        arguments: {
                          ...(next?.defaultArguments || {}),
                        },
                      });
                    }}
                    disabled={!canWrite}
                  >
                    {FLOW_TOOL_CATALOG.map((item) => (
                      <option key={item.name} value={item.name}>
                        {item.group} · {item.title}
                      </option>
                    ))}
                  </select>
                </label>

                {tool && (
                  <div className="flow-tool-description">
                    <strong>{tool.title}</strong>
                    <span>{tool.description}</span>
                  </div>
                )}

                {tool?.fields.map((field) => {
                  const current =
                    node.config.arguments?.[field.key];

                  if (field.type === "json") {
                    return (
                      <label key={field.key}>
                        <span>{field.label}</span>
                        <textarea
                          rows={5}
                          defaultValue={JSON.stringify(
                            current ?? [],
                            null,
                            2,
                          )}
                          placeholder={field.placeholder}
                          disabled={!canWrite}
                          onBlur={(event) => {
                            if (!canWrite) return;
                            try {
                              updateToolArgument(
                                node,
                                field.key,
                                JSON.parse(event.target.value),
                                onUpdate,
                              );
                              event.currentTarget
                                .classList.remove("invalid");
                            } catch {
                              event.currentTarget
                                .classList.add("invalid");
                            }
                          }}
                        />
                        <small className="flow-field-hint">
                          JSON válido. El cambio se aplica al salir
                          del campo.
                        </small>
                      </label>
                    );
                  }

                  return (
                    <label key={field.key}>
                      <span>{field.label}</span>
                      <input
                        type={
                          field.type === "number"
                            ? "number"
                            : "text"
                        }
                        min={field.min}
                        max={field.max}
                        value={
                          current == null
                            ? ""
                            : String(current)
                        }
                        placeholder={field.placeholder}
                        disabled={!canWrite}
                        onChange={(event) =>
                          canWrite
                          && updateToolArgument(
                            node,
                            field.key,
                            field.type === "number"
                              ? Number(event.target.value)
                              : event.target.value,
                            onUpdate,
                          )}
                      />
                    </label>
                  );
                })}

                <div className="flow-runtime-variables">
                  <span>Variables disponibles</span>
                  <div>
                    {FLOW_RUNTIME_VARIABLES.map((variable) => (
                      <code key={variable}>{variable}</code>
                    ))}
                  </div>
                </div>
              </>
            )}

            {node.type === "end" && (
              <label>
                <span>{t("flowEndLabel")}</span>
                <input
                  type="text"
                  value={node.config.label || ""}
                  onChange={(event) =>
                    canWrite
                    && onUpdate(node.id, {
                      label: event.target.value,
                    })}
                  disabled={!canWrite}
                  placeholder={t("flowEndPlaceholder")}
                />
              </label>
            )}
          </div>

          {node.type !== "trigger" && canWrite && (
            <div className="flow-sidebar-footer">
              <button
                className="secondary-button flow-delete-node"
                onClick={() => onDelete(node.id)}
              >
                <Trash2 size={14} />
                {t("flowDeleteNode")}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
