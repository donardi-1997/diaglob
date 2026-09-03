import { X, Zap, Clock, MessageSquare, GitBranch, Square, Trash2 } from "lucide-react";
import type { FlowGraph, FlowNode, FlowNodeConfig } from "./flowGraphUtils";
import { TRIGGER_TYPES, CONDITION_FIELDS, CONDITION_OPERATORS, humanizeNodeType } from "./flowGraphUtils";

interface FlowSidebarProps {
  node: FlowNode | null;
  graph: FlowGraph;
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
  customer_segment: "flowField_customer_segment",
  customer_health: "flowField_customer_health",
  customer_priority: "flowField_customer_priority",
  needs_attention: "flowField_needs_attention",
  needs_followup: "flowField_needs_followup",
  orders_count: "flowField_orders_count",
  country_code: "flowField_country_code",
  successful_order_since_start: "flowField_successful_order_since_start",
};

const OPERATOR_LABELS: Record<string, string> = {
  equals: "flowOperator_equals",
  not_equals: "flowOperator_not_equals",
  gt: "flowOperator_gt",
  gte: "flowOperator_gte",
  lt: "flowOperator_lt",
  lte: "flowOperator_lte",
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

const BOOLEAN_FIELDS = new Set(["needs_attention", "needs_followup"]);
const NUMERIC_FIELDS = new Set(["orders_count"]);

export default function FlowSidebar({ node, onUpdate, onDelete, onClose, t, canWrite }: FlowSidebarProps) {
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
        boxShadow: isOpen ? "-8px 0 30px rgba(0,0,0,0.15)" : "none",
      }}
    >
      {node && (
        <>
          <div
            className="flow-sidebar-header"
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "18px 20px",
              borderBottom: "1px solid var(--border)",
              flexShrink: 0,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <Icon size={18} style={{ color: "var(--accent)" }} />
              <h3 style={{ margin: 0, fontSize: 15 }}>
                {humanizeNodeType(node.type, t)}
              </h3>
            </div>
            <button
              className="icon-button"
              onClick={onClose}
              style={{
                width: 34,
                height: 34,
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                border: "1px solid var(--border)",
                borderRadius: 8,
                background: "transparent",
                color: "var(--text-muted)",
                cursor: "pointer",
              }}
            >
              <X size={16} />
            </button>
          </div>

          <div
            className="management-form"
            style={{ flex: 1, overflowY: "auto", padding: 20, display: "flex", flexDirection: "column", gap: 20 }}
          >
            {node.type === "trigger" && (
              <label>
                <span>{t("flowTriggerType")}</span>
                <select
                  value={node.config.trigger_type || "manual"}
                  onChange={(e) => canWrite && onUpdate(node.id, { trigger_type: e.target.value as any })}
                  disabled={!canWrite}
                >
                  {TRIGGER_TYPES.map((tt) => (
                    <option key={tt} value={tt}>
                      {t(TRIGGER_LABELS[tt] || tt)}
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
                    min={0}
                    value={node.config.duration || 0}
                    onChange={(e) => canWrite && onUpdate(node.id, { duration: Number(e.target.value) })}
                    disabled={!canWrite}
                  />
                </label>
                <label>
                  <span>{t("flowDurationUnit")}</span>
                  <select
                    value={node.config.duration_unit || "hours"}
                    onChange={(e) => canWrite && onUpdate(node.id, { duration_unit: e.target.value as any })}
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
                    value={node.config.condition_field || ""}
                    onChange={(e) => {
                      if (!canWrite) return;
                      const field = e.target.value as any;
                      const patch: Partial<FlowNodeConfig> = { condition_field: field };
                      if (BOOLEAN_FIELDS.has(field)) {
                        patch.condition_operator = "is_true";
                        patch.condition_value = true;
                      } else if (NUMERIC_FIELDS.has(field)) {
                        patch.condition_operator = "gt";
                        patch.condition_value = 0;
                      } else {
                        patch.condition_operator = "equals";
                        patch.condition_value = "";
                      }
                      onUpdate(node.id, patch);
                    }}
                    disabled={!canWrite}
                  >
                    <option value="">{t("flowSelectField")}</option>
                    {CONDITION_FIELDS.map((f) => (
                      <option key={f} value={f}>
                        {t(FIELD_LABELS[f] || f)}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  <span>{t("flowConditionOperator")}</span>
                  <select
                    value={node.config.condition_operator || "equals"}
                    onChange={(e) => canWrite && onUpdate(node.id, { condition_operator: e.target.value as any })}
                    disabled={!canWrite}
                  >
                    {CONDITION_OPERATORS.map((op) => (
                      <option key={op} value={op}>
                        {t(OPERATOR_LABELS[op] || op)}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  <span>{t("flowConditionValue")}</span>
                  {BOOLEAN_FIELDS.has(node.config.condition_field || "") ? (
                    <select
                      value={String(node.config.condition_value ?? "true")}
                      onChange={(e) => canWrite && onUpdate(node.id, { condition_value: e.target.value === "true" })}
                      disabled={!canWrite}
                    >
                      <option value="true">{t("flowOperator_is_true")}</option>
                      <option value="false">{t("flowOperator_is_false")}</option>
                    </select>
                  ) : NUMERIC_FIELDS.has(node.config.condition_field || "") ? (
                    <input
                      type="number"
                      value={Number(node.config.condition_value ?? 0)}
                      onChange={(e) => canWrite && onUpdate(node.id, { condition_value: Number(e.target.value) })}
                      disabled={!canWrite}
                    />
                  ) : (
                    <input
                      type="text"
                      value={String(node.config.condition_value ?? "")}
                      onChange={(e) => canWrite && onUpdate(node.id, { condition_value: e.target.value })}
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
                    onChange={(e) => canWrite && onUpdate(node.id, { message_mode: e.target.value as any })}
                    disabled={!canWrite}
                  >
                    <option value="free_form">{t("flowMessageMode_free_form")}</option>
                    <option value="template">{t("flowMessageMode_template")}</option>
                    <option value="auto">{t("flowMessageMode_auto")}</option>
                  </select>
                </label>
                {node.config.message_mode === "template" && (
                  <small style={{ color: "var(--text-muted)", fontSize: 12 }}>
                    {t("flowTemplateHint")}
                  </small>
                )}
                {node.config.message_mode !== "template" && (
                  <label>
                    <span>{t("flowMessageLabel")}</span>
                    <textarea
                      rows={3}
                      value={node.config.label || ""}
                      onChange={(e) => canWrite && onUpdate(node.id, { label: e.target.value })}
                      disabled={!canWrite}
                      placeholder={t("flowMessagePlaceholder")}
                      style={{
                        width: "100%",
                        boxSizing: "border-box",
                        padding: "10px 12px",
                        border: "1px solid var(--border)",
                        borderRadius: 10,
                        background: "transparent",
                        color: "var(--text)",
                        font: "inherit",
                        resize: "vertical",
                        outline: "none",
                      }}
                    />
                  </label>
                )}
              </>
            )}

            {node.type === "end" && (
              <label>
                <span>{t("flowEndLabel")}</span>
                <input
                  type="text"
                  value={node.config.label || ""}
                  onChange={(e) => canWrite && onUpdate(node.id, { label: e.target.value })}
                  disabled={!canWrite}
                  placeholder={t("flowEndPlaceholder")}
                />
              </label>
            )}
          </div>

          {node.type !== "trigger" && canWrite && (
            <div
              style={{
                padding: "16px 20px",
                borderTop: "1px solid var(--border)",
                flexShrink: 0,
              }}
            >
              <button
                className="secondary-button"
                style={{ width: "100%", color: "#ef4444", borderColor: "rgba(239,68,68,0.3)" }}
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
