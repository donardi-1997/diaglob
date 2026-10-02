import { useState } from "react";
import {
  Bot,
  Check,
  Loader2,
  Send,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import {
  approveAgentChatAction,
  cancelAgentChatAction,
  createAgentChatSession,
  sendAgentChatMessage,
  type AgentChatSession,
  type AgentToolCall,
} from "../../services/agentChat";

interface Props {
  storeId: number;
  flowId: number;
  flowName: string;
  onApplied: () => Promise<void> | void;
  onClose: () => void;
}

function errorMessage(error: unknown) {
  const candidate = error as {
    response?: { data?: { detail?: string | { message?: string } } };
    message?: string;
  };
  const detail = candidate.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && detail.message) {
    return detail.message;
  }
  return candidate.message || "No pudimos completar la solicitud.";
}

function pendingApproval(
  session: AgentChatSession | null,
): AgentToolCall | null {
  return (
    session?.pending_actions?.find(
      (call) =>
        call.status === "approval_required"
        && call.approval?.status === "pending",
    )
    || null
  );
}

function flowWasUpdated(
  session: AgentChatSession | null,
  flowId: number,
): boolean {
  if (!session?.messages) return false;

  return session.messages.some((message) =>
    message.tool_calls.some((call) => {
      if (
        call.tool_name !== "automations.update"
        || call.status !== "success"
      ) {
        return false;
      }

      return Number(call.arguments.flow_id) === flowId;
    }),
  );
}

export default function FlowCopilotPanel({
  storeId,
  flowId,
  flowName,
  onApplied,
  onClose,
}: Props) {
  const [prompt, setPrompt] = useState("");
  const [session, setSession] = useState<AgentChatSession | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const approval = pendingApproval(session);

  let lastAssistantText = "";
  const messages = session?.messages || [];
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role === "assistant" && message.text?.trim()) {
      lastAssistantText = message.text.trim();
      break;
    }
  }

  async function syncIfApplied(next: AgentChatSession) {
    if (flowWasUpdated(next, flowId)) {
      await onApplied();
    }
  }

  async function submit() {
    const request = prompt.trim();
    if (!request || busy) return;

    setBusy(true);
    setError("");

    try {
      const created = await createAgentChatSession(storeId, {
        page: "automation-builder",
        entity_id: flowId,
        flow_name: flowName,
      });

      const instruction = [
        `Estás editando la automatización existente flow_id=${flowId} llamada "${flowName}".`,
        "Trabaja únicamente sobre ese flow usando automations.update.",
        "No crees otro flow, no publiques y no actives la automatización.",
        "Conserva el resultado como borrador editable y usa un grafo DAG válido.",
        "Solicitud del usuario:",
        request,
      ].join("\n");

      const next = await sendAgentChatMessage(
        created.id,
        instruction,
        {
          page: "automation-builder",
          entity_id: flowId,
          flow_name: flowName,
        },
      );

      setSession(next);
      await syncIfApplied(next);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function resolveApproval(approve: boolean) {
    if (!session || !approval?.approval || busy) return;

    setBusy(true);
    setError("");

    try {
      const next = approve
        ? await approveAgentChatAction(
            session.id,
            approval.approval.id,
          )
        : await cancelAgentChatAction(
            session.id,
            approval.approval.id,
          );

      setSession(next);
      await syncIfApplied(next);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className="flow-copilot-panel">
      <header className="flow-copilot-header">
        <div className="flow-copilot-title">
          <span className="flow-copilot-icon">
            <Sparkles size={16} />
          </span>
          <div>
            <span>Copiloto</span>
            <strong>Diseñar con IA</strong>
          </div>
        </div>
        <button
          type="button"
          className="icon-button"
          onClick={onClose}
          aria-label="Cerrar copiloto"
        >
          <X size={16} />
        </button>
      </header>

      <div className="flow-copilot-body">
        <div className="flow-copilot-context">
          <Bot size={16} />
          <div>
            <strong>{flowName}</strong>
            <span>
              La IA puede reorganizar el borrador. Publicar y activar siguen
              siendo acciones separadas.
            </span>
          </div>
        </div>

        <label className="flow-copilot-prompt">
          <span>Describe el flujo que quieres</span>
          <textarea
            rows={6}
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Ej. Cuando llegue un pedido, espera 30 minutos. Si el cliente necesita seguimiento, envíale un WhatsApp y termina el flujo."
            disabled={busy || Boolean(approval)}
          />
        </label>

        <button
          type="button"
          className="primary-button flow-copilot-submit"
          onClick={() => void submit()}
          disabled={busy || !prompt.trim() || Boolean(approval)}
        >
          {busy ? (
            <Loader2 className="spin" size={15} />
          ) : (
            <Send size={15} />
          )}
          Generar cambios
        </button>

        {lastAssistantText && (
          <div className="flow-copilot-response">
            <span>Respuesta del Copiloto</span>
            <p>{lastAssistantText}</p>
          </div>
        )}

        {approval && approval.approval && (
          <div className="flow-copilot-approval">
            <div>
              <ShieldCheck size={17} />
              <div>
                <strong>Revisar cambio antes de aplicarlo</strong>
                <span>
                  {approval.title || "Modificar automatización"}
                </span>
              </div>
            </div>

            <div className="flow-copilot-approval-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={() => void resolveApproval(false)}
                disabled={busy}
              >
                <X size={14} />
                Cancelar
              </button>
              <button
                type="button"
                className="primary-button"
                onClick={() => void resolveApproval(true)}
                disabled={busy}
              >
                {busy ? (
                  <Loader2 className="spin" size={14} />
                ) : (
                  <Check size={14} />
                )}
                Aplicar al canvas
              </button>
            </div>
          </div>
        )}

        {session && flowWasUpdated(session, flowId) && !approval && (
          <div className="flow-copilot-success">
            <Check size={15} />
            Borrador actualizado en el canvas.
          </div>
        )}

        {error && <p className="flow-copilot-error">{error}</p>}
      </div>
    </aside>
  );
}
