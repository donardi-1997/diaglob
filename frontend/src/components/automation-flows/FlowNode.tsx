import { Handle, Position } from "@xyflow/react";
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
  trigger: "var(--accent)",
  wait: "#e6a817",
  condition: "#4a9eff",
  message: "var(--green)",
  call: "#06b6d4",
  tool: "#8b5cf6",
  end: "var(--text-muted)",
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
    color: "#22c55e",
    background: "rgba(34,197,94,0.12)",
    label: "Completado",
  },
  failed: {
    color: "#ef4444",
    background: "rgba(239,68,68,0.12)",
    label: "Falló",
  },
  ambiguous: {
    color: "#f59e0b",
    background: "rgba(245,158,11,0.12)",
    label: "Ambiguo",
  },
  skipped: {
    color: "#94a3b8",
    background: "rgba(148,163,184,0.12)",
    label: "Omitido",
  },
  running: {
    color: "#3b82f6",
    background: "rgba(59,130,246,0.12)",
    label: "Ejecutando",
  },
  waiting: {
    color: "#e6a817",
    background: "rgba(230,168,23,0.12)",
    label: "Esperando",
  },
  pending: {
    color: "var(--text-muted)",
    background: "rgba(255,255,255,0.06)",
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
          ? `flow-node-card flow-node-debug is-${debug.status}`
          : "flow-node-card"
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
          ? "0 0 0 3px rgba(124, 92, 255, 0.12)"
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
          {humanizeNodeType(nodeType, (key: string) => key)}
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
          (key: string) => key,
        )}
      >
        {humanizeNodeSummary(
          nodeData,
          (key: string) => key,
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
            YES
          </span>
          <Handle
            type="source"
            position={Position.Bottom}
            id="false"
            style={{
              width: 10,
              height: 10,
              background: "#ef4444",
              border: "2px solid var(--panel)",
              left: "30%",
            }}
          />
          <span className="flow-condition-label no">
            NO
          </span>
        </>
      ) : nodeType === "call" ? (
        <>
          {[
            ["confirmed", "CONF", "var(--green)", "12%"],
            ["rejected", "RECH", "#ef4444", "37%"],
            ["no_answer", "SIN", "#f59e0b", "63%"],
            ["failed", "FAIL", "#94a3b8", "88%"],
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
