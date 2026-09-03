import { Handle, Position } from "@xyflow/react";
import { Zap, Clock, MessageSquare, GitBranch, Square } from "lucide-react";
import { humanizeNodeSummary, humanizeNodeType, type FlowNode as FlowNodeData, type FlowNodeType } from "./flowGraphUtils";

const TYPE_COLORS: Record<FlowNodeType, string> = {
  trigger: "var(--accent)",
  wait: "#e6a817",
  condition: "#4a9eff",
  message: "var(--green)",
  end: "var(--text-muted)",
};

const TYPE_ICONS: Record<FlowNodeType, typeof Zap> = {
  trigger: Zap,
  wait: Clock,
  condition: GitBranch,
  message: MessageSquare,
  end: Square,
};

export default function FlowNode({ data, selected }: { data: Record<string, unknown>; selected?: boolean }) {
  const nodeData = data as unknown as FlowNodeData;
  const nodeType = nodeData.type as FlowNodeType;
  const Icon = TYPE_ICONS[nodeType] || Square;
  const color = TYPE_COLORS[nodeType] || "var(--text-muted)";

  return (
    <div
      className="flow-node-card"
      style={{
        padding: "14px 16px",
        borderRadius: 12,
        background: "var(--panel)",
        border: selected ? "2px solid var(--accent)" : "1px solid var(--border)",
        borderLeft: `4px solid ${color}`,
        cursor: "pointer",
        transition: "all 150ms ease",
        minWidth: 180,
        maxWidth: 240,
        boxShadow: selected ? "0 0 0 3px rgba(124, 92, 255, 0.12)" : "none",
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

      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <Icon size={16} style={{ color, flexShrink: 0 }} />
        <span
          style={{
            fontSize: 9,
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: "0.12em",
            color: "var(--text-muted)",
          }}
        >
          {humanizeNodeType(nodeType, (k: string) => k)}
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
      >
        {humanizeNodeSummary(nodeData, (k: string) => k)}
      </p>

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
          <span
            style={{
              position: "absolute",
              bottom: -18,
              left: "63%",
              fontSize: 9,
              color: "var(--green)",
              fontWeight: 600,
            }}
          >
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
          <span
            style={{
              position: "absolute",
              bottom: -18,
              left: "20%",
              fontSize: 9,
              color: "#ef4444",
              fontWeight: 600,
            }}
          >
            NO
          </span>
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
