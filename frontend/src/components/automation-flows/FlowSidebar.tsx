import {
  Clock,
  GitBranch,
  MessageSquare,
  Square,
  Trash2,
  X,
  Zap,
} from "lucide-react";
import type { FlowNode, FlowNodeConfig } from "./flowGraphUtils";
import {
  CONDITION_FIELDS,
  CONDITION_OPERATORS,
  TRIGGER_TYPES,
  humanizeNodeType,
} from "./flowGraphUtils";

interface FlowSidebarProps {
  node: FlowNode | null;
  onUpdate: (nodeId: string, config: Partial<FlowNodeConfig>) => void;
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
  end: Square,
};

const BOOLEAN_FIELDS = new Set([
  "customer.needs_attention",
  "customer.needs_followup",
  "has_successful_order_since_flow_start",
]);

const NUMERIC_FIELDS = new Set(["customer.order_count"]);

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

  return (
    <div
      className="flow-sidebar"
      style={{
        position: "fixed",
        top: 0,
        right: 0,
        height: "100vh",
        width: 380,
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
                      trigger_type: event.target.value as FlowNodeConfig["trigger_type"],
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
                        value: Math.max(1, Number(event.target.value) || 1),
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
                        unit: event.target.value as FlowNodeConfig["unit"],
                      })}
                    disabled={!canWrite}
                  >
                    <option value="minutes">{t("flowUnit_minutes")}</option>
                    <option value="hours">{t("flowUnit_hours")}</option>
                    <option value="days">{t("flowUnit_days")}</option>
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

                      const field = event.target.value as FlowNodeConfig["field"];
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
                        operator: event.target.value as FlowNodeConfig["operator"],
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
                      <option value="true">{t("flowOperator_is_true")}</option>
                      <option value="false">{t("flowOperator_is_false")}</option>
                    </select>
                  ) : NUMERIC_FIELDS.has(node.config.field || "") ? (
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
                        && onUpdate(node.id, { value: event.target.value })}
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
                        message_mode: event.target.value as FlowNodeConfig["message_mode"],
                      })}
                    disabled={!canWrite}
                  >
                    <option value="free_form">
                      {t("flowMessageMode_free_form")}
                    </option>
                    <option value="template">
                      {t("flowMessageMode_template")}
                    </option>
                    <option value="auto">{t("flowMessageMode_auto")}</option>
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

            {node.type === "end" && (
              <label>
                <span>{t("flowEndLabel")}</span>
                <input
                  type="text"
                  value={node.config.label || ""}
                  onChange={(event) =>
                    canWrite
                    && onUpdate(node.id, { label: event.target.value })}
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
