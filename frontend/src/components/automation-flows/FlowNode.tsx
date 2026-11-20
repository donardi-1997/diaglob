import { Handle, Position } from "@xyflow/react";
import { useTranslation } from "react-i18next";
import {
  Clock,
  GitBranch,
  MessageSquare,
  PhoneCall,
  Square,
  Wrench,
  Zap,
} from "lucide-react";
import {
  humanizeNodeSummary,
  humanizeNodeType,
  type FlowNode as FlowNodeData,
  type FlowNodeType,
} from "./flowGraphUtils";

const TYPE_COLORS: Record<FlowNodeType, string> = {
  trigger: "var(--flow-trigger)",
  wait: "var(--flow-wait)",
  condition: "var(--flow-condition)",
  message: "var(--flow-action)",
  call: "var(--flow-human)",
  tool: "var(--flow-ai)",
  end: "var(--flow-neutral)",
};

const TYPE_ICONS: Record<FlowNodeType, typeof Zap> = {
  trigger: Zap,
  wait: Clock,
  condition: GitBranch,
  message: MessageSquare,
  call: PhoneCall,
  tool: Wrench,
  end: Square,
};

const DEBUG_STYLES: Record<
  string,
  { color: string; background: string; label: string }
> = {
  completed: {
    color: "var(--success-primary)",
    background: "var(--success-soft)",
    label: "Completado",
  },
  failed: {
    color: "var(--danger-primary)",
    background: "var(--danger-soft)",
    label: "Falló",
  },
  ambiguous: {
    color: "var(--warning-primary)",
    background: "var(--warning-soft)",
    label: "Ambiguo",
  },
  skipped: {
    color: "var(--flow-neutral)",
    background: "var(--bg-surface-secondary)",
    label: "Omitido",
  },
  running: {
    color: "var(--info-primary)",
    background: "var(--info-soft)",
    label: "Ejecutando",
  },
  waiting: {
    color: "var(--warning-primary)",
    background: "var(--warning-soft)",
    label: "Esperando",
  },
  pending: {
    color: "var(--text-muted)",
    background: "var(--bg-surface-secondary)",
    label: "Pendiente",
  },
};

function formatDuration(duration?: number | null) {
  if (duration == null) return null;
  if (duration < 1000) return `${duration} ms`;
  if (duration < 60_000) {
    return `${(duration / 1000).toFixed(1)} s`;
  }
  return `${(duration / 60_000).toFixed(1)} min`;
}

export default function FlowNode({
  data,
  selected,
}: {
  data: Record<string, unknown>;
  selected?: boolean;
}) {
  const { t } = useTranslation();
  const nodeData = data as unknown as FlowNodeData;
  const nodeType = nodeData.type as FlowNodeType;
  const Icon = TYPE_ICONS[nodeType] || Square;
  const color = TYPE_COLORS[nodeType] || "var(--text-muted)";
  const debug = nodeData.debug;
  const debugStyle = debug
    ? DEBUG_STYLES[debug.status] || DEBUG_STYLES.pending
    : null;
  const duration = formatDuration(debug?.duration_ms);

  return (
    <div
      className={
        debug
          ? `flow-node-card type-${nodeType} flow-node-debug is-${debug.status}`
          : `flow-node-card type-${nodeType}`
      }
      style={{
        position: "relative",
        padding: "14px 16px",
        borderRadius: 12,
        background: "var(--panel)",
        border: selected
          ? "2px solid var(--accent)"
          : debugStyle
            ? `1px solid ${debugStyle.color}`
            : "1px solid var(--border)",
        borderLeft: `4px solid ${debugStyle?.color || color}`,
        cursor: "pointer",
        transition: "all 150ms ease",
        minWidth: 190,
        maxWidth: 250,
        boxShadow: selected
          ? "0 0 0 3px var(--brand-selected-ring)"
          : debugStyle
            ? `0 0 0 2px ${debugStyle.background}`
            : "none",
      }}
    >
      {nodeType !== "trigger" && (
        <Handle
          type="target"
          position={Position.Top}
          style={{
            width: 10,
            height: 10,
            background: "var(--text-muted)",
            border: "2px solid var(--panel)",
          }}
        />
      )}

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          paddingRight: debug ? 8 : 0,
        }}
      >
        <Icon
          size={16}
          style={{
            color: debugStyle?.color || color,
            flexShrink: 0,
          }}
        />
        <span
          style={{
            fontSize: 9,
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: "0.12em",
            color: "var(--text-muted)",
          }}
        >
          {humanizeNodeType(nodeType, t)}
        </span>
      </div>

      <p
        style={{
          margin: "6px 0 0",
          fontSize: 12,
          color: "var(--text-secondary)",
          lineHeight: 1.35,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
        title={humanizeNodeSummary(
          nodeData,
          t,
        )}
      >
        {humanizeNodeSummary(
          nodeData,
          t,
        )}
      </p>

      {debug && debugStyle && (
        <div className="flow-node-debug-meta">
          <span
            className="flow-node-debug-status"
            style={{
              color: debugStyle.color,
              background: debugStyle.background,
            }}
          >
            {debug.label || debugStyle.label}
          </span>
          {duration && <small>{duration}</small>}
          {debug.executions != null && debug.executions > 1 && (
            <small>{debug.executions} ejec.</small>
          )}
        </div>
      )}

      {debug?.error && (
        <p className="flow-node-debug-error" title={debug.error}>
          {debug.error}
        </p>
      )}

      {nodeType === "condition" ? (
        <>
          <Handle
            type="source"
            position={Position.Bottom}
            id="true"
            style={{
              width: 10,
              height: 10,
              background: "var(--green)",
              border: "2px solid var(--panel)",
              left: "70%",
            }}
          />
          <span className="flow-condition-label yes">
            {t("flowBranchYes")}
          </span>
          <Handle
            type="source"
            position={Position.Bottom}
            id="false"
            style={{
              width: 10,
              height: 10,
              background: "var(--danger-primary)",
              border: "2px solid var(--panel)",
              left: "30%",
            }}
          />
          <span className="flow-condition-label no">
            {t("flowBranchNo")}
          </span>
        </>
      ) : nodeType === "call" ? (
        <>
          {[
            ["confirmed", "CONF", "var(--green)", "12%"],
            ["rejected", "RECH", "var(--danger-primary)", "37%"],
            ["no_answer", "SIN", "var(--warning-primary)", "63%"],
            ["failed", "FAIL", "var(--flow-neutral)", "88%"],
          ].map(([id, label, background, left]) => (
            <div key={id}>
              <Handle
                type="source"
                position={Position.Bottom}
                id={id}
                style={{
                  width: 10,
                  height: 10,
                  background,
                  border: "2px solid var(--panel)",
                  left,
                }}
              />
              <span
                style={{
                  position: "absolute",
                  bottom: -18,
                  left,
                  transform: "translateX(-50%)",
                  fontSize: 8,
                  fontWeight: 700,
                  color: "var(--text-muted)",
                }}
              >
                {label}
              </span>
            </div>
          ))}
        </>
      ) : nodeType !== "end" ? (
        <Handle
          type="source"
          position={Position.Bottom}
          style={{
            width: 10,
            height: 10,
            background: "var(--text-muted)",
            border: "2px solid var(--panel)",
          }}
        />
      ) : null}
    </div>
  );
}
