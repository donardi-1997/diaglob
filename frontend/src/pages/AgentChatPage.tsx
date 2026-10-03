import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  Archive,
  Bot,
  Check,
  ChevronRight,
  CircleDollarSign,
  Loader2,
  MessageSquarePlus,
  Send,
  ShieldCheck,
  Sparkles,
  Wrench,
  X,
} from "lucide-react";
import {
  approveAgentChatAction,
  archiveAgentChatSession,
  cancelAgentChatAction,
  createAgentChatSession,
  getAgentChatSession,
  listAgentChatSessions,
  sendAgentChatMessage,
  type AgentChatSession,
  type AgentToolCall,
} from "../services/agentChat";
import {
  buildCopilotPageContext,
  captureCopilotPageText,
  type CopilotPageContextInput,
} from "../services/copilotPageContext";
import "../agent-chat.css";

interface Props {
  storeId: number;
  storeName?: string;
  mode?: "page" | "panel";
  pageContext?: CopilotPageContextInput;
  onClose?: () => void;
}

const suggestions = [
  "¿Qué pedidos pagados siguen pendientes de fulfillment?",
  "Analiza el estado de mi operación y dime qué necesita atención.",
  "Ayúdame a crear una automatización para pedidos de alto valor.",
  "Muéstrame las automatizaciones activas y explícame qué hacen.",
];

function suggestionsForPage(page?: string, label?: string) {
  const pageLabel = label || "esta vista";
  const contextual: Record<string, string[]> = {
    overview: [
      "Resume lo más importante de este tablero.",
      "¿Qué necesita atención ahora mismo?",
      "Dame tres acciones concretas para mejorar la operación.",
    ],
    analytics: [
      "Explícame las métricas que estoy viendo.",
      "¿Qué tendencia o anomalía debería revisar primero?",
      "Resume esta vista para una decisión comercial.",
    ],
    customers: [
      "Resume los clientes visibles y qué requiere atención.",
      "¿Qué señales de riesgo o seguimiento ves aquí?",
      "Ayúdame a priorizar los clientes de esta vista.",
    ],
    commerce: [
      "Explícame los pedidos o productos visibles en esta vista.",
      "¿Qué debería atender primero aquí?",
      "Resume los datos visibles y dame próximos pasos.",
    ],
    "post-sales": [
      "Resume los casos visibles y priorízalos por urgencia.",
      "¿Qué casos requieren intervención humana?",
      "¿Qué acción recomiendas para esta vista?",
    ],
    integrations: [
      "Explícame el estado de las integraciones visibles.",
      "¿Qué integración parece requerir atención?",
      "Guíame para completar la configuración de esta vista.",
    ],
    automations: [
      "Explícame la automatización que estoy viendo.",
      "¿Qué está incompleto o puede fallar en este flujo?",
      "Ayúdame a mejorar esta automatización.",
    ],
    agents: [
      "Explícame los agentes visibles y sus funciones.",
      "¿Qué agente debería usar para esta tarea?",
      "¿Ves alguna configuración que deba revisar?",
    ],
    knowledge: [
      "Resume el estado de esta base de conocimiento.",
      "¿Qué fuente o sincronización requiere atención?",
      "Explícame lo que estoy viendo sin lenguaje técnico.",
    ],
  };

  return contextual[page || ""] || [
    `Explícame lo que estoy viendo en ${pageLabel}.`,
    "¿Qué información de esta vista requiere atención?",
    "Resume esta página y dame los próximos pasos.",
  ];
}

function errorMessage(error: unknown, fallback: string) {
  const candidate = error as {
    response?: { data?: { detail?: { message?: string; code?: string } | string } };
    message?: string;
  };
  const detail = candidate?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    return detail.message || detail.code || fallback;
  }
  return candidate?.message || fallback;
}

function compactJson(value: Record<string, unknown>) {
  const keys = Object.keys(value);
  if (keys.length === 0) return "Sin parámetros";
  return keys
    .slice(0, 4)
    .map((key) => {
      const raw = value[key];
      const text =
        typeof raw === "string"
          ? raw
          : JSON.stringify(raw);
      return `${key}: ${String(text).slice(0, 80)}`;
    })
    .join(" · ");
}

function ToolActivity({ call }: { call: AgentToolCall }) {
  const completed = call.status === "success";
  const waiting = call.status === "approval_required";
  const failed = ["error", "denied", "unavailable"].includes(call.status);

  return (
    <div className={`copilot-tool ${waiting ? "waiting" : failed ? "failed" : completed ? "done" : ""}`}>
      <div className="copilot-tool-icon">
        {waiting ? (
          <ShieldCheck size={15} />
        ) : failed ? (
          <AlertTriangle size={15} />
        ) : completed ? (
          <Check size={15} />
        ) : (
          <Wrench size={15} />
        )}
      </div>
      <div className="copilot-tool-copy">
        <strong>{call.title || call.tool_name}</strong>
        <span>{compactJson(call.arguments)}</span>
      </div>
      <span className="copilot-tool-status">
        {waiting
          ? "Requiere aprobación"
          : completed
            ? "Completado"
            : failed
              ? "Error"
              : call.status}
      </span>
    </div>
  );
}

function ApprovalCard({
  call,
  busy,
  onApprove,
  onCancel,
}: {
  call: AgentToolCall;
  busy: boolean;
  onApprove: () => void;
  onCancel: () => void;
}) {
  const approval = call.approval;
  if (!approval || approval.status !== "pending") return null;

  const critical = approval.confirmation === "critical";
  return (
    <div className={`copilot-approval ${critical ? "critical" : ""}`}>
      <div className="copilot-approval-heading">
        <div className="copilot-approval-icon">
          {critical ? <CircleDollarSign size={18} /> : <ShieldCheck size={18} />}
        </div>
        <div>
          <strong>{critical ? "Confirmación crítica" : "Confirmación requerida"}</strong>
          <p>{call.description || "Diaglob necesita tu aprobación antes de ejecutar esta acción."}</p>
        </div>
      </div>
      <div className="copilot-approval-detail">
        <span>Acción</span>
        <strong>{call.title}</strong>
      </div>
      <div className="copilot-approval-arguments">
        {Object.entries(call.arguments).map(([key, value]) => (
          <div key={key}>
            <span>{key}</span>
            <code>{typeof value === "string" ? value : JSON.stringify(value)}</code>
          </div>
        ))}
      </div>
      {critical && (
        <p className="copilot-critical-note">
          Esta acción puede generar efectos externos o costos reales. Revisa los datos antes de aprobar.
        </p>
      )}
      <div className="copilot-approval-actions">
        <button className="secondary-button" disabled={busy} onClick={onCancel}>
          <X size={14} />
          Cancelar
        </button>
        <button className={critical ? "danger-button" : "primary-button"} disabled={busy} onClick={onApprove}>
          {busy ? <Loader2 className="spin" size={14} /> : <Check size={14} />}
          {critical ? "Confirmar acción" : "Aprobar"}
        </button>
      </div>
    </div>
  );
}

export default function AgentChatPage({
  storeId,
  storeName,
  mode = "page",
  pageContext,
  onClose,
}: Props) {
  const { t } = useTranslation();
  const panelMode = mode === "panel";
  const [includePageContext, setIncludePageContext] = useState(panelMode);
  const [sessions, setSessions] = useState<AgentChatSession[]>([]);
  const [session, setSession] = useState<AgentChatSession | null>(null);
  const [input, setInput] = useState("");
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [loadingChat, setLoadingChat] = useState(false);
  const [approvalBusy, setApprovalBusy] = useState<number | null>(null);
  const [error, setError] = useState("");
  const endRef = useRef<HTMLDivElement | null>(null);

  const messageContext = useCallback(() => {
    if (!panelMode || !includePageContext || !pageContext) {
      return { page: "copilot" };
    }

    const root = document.querySelector(".dg-main-content");
    const pageText = captureCopilotPageText(root);

    return buildCopilotPageContext(pageContext, pageText);
  }, [includePageContext, pageContext, panelMode]);

  const activeSuggestions = useMemo(
    () =>
      panelMode
        ? suggestionsForPage(pageContext?.page, pageContext?.pageLabel)
        : suggestions,
    [pageContext?.page, pageContext?.pageLabel, panelMode],
  );

  const copy = useMemo(
    () => ({
      title: t("copilotTitle", { defaultValue: "Copiloto IA" }),
      subtitle: t("copilotSubtitle", {
        defaultValue: "Consulta tu operación y ejecuta acciones con los permisos de tu usuario.",
      }),
      newChat: t("copilotNewChat", { defaultValue: "Nuevo chat" }),
      emptyTitle: panelMode
        ? "¿Qué quieres saber de esta vista?"
        : t("copilotEmptyTitle", { defaultValue: "¿Qué quieres hacer hoy?" }),
      emptyBody: panelMode
        ? `Puedo usar el contenido visible de ${pageContext?.pageLabel || "esta página"} y combinarlo con los datos permitidos de Diaglob.`
        : t("copilotEmptyBody", {
            defaultValue: "Puedo consultar pedidos, clientes, productos, tracking, CJ y ayudarte a construir automatizaciones.",
          }),
      placeholder: t("copilotPlaceholder", {
        defaultValue: "Pregunta por tu operación o pide una acción...",
      }),
      history: t("copilotHistory", { defaultValue: "Historial" }),
      loadError: t("copilotLoadError", { defaultValue: "No pudimos cargar el Copiloto." }),
      sendError: t("copilotSendError", { defaultValue: "No pudimos procesar el mensaje." }),
    }),
    [pageContext?.pageLabel, panelMode, t],
  );

  const loadSessions = useCallback(async () => {
    if (!storeId) {
      setSessions([]);
      setSession(null);
      return;
    }
    setLoadingSessions(true);
    setError("");
    try {
      const result = await listAgentChatSessions(storeId);
      setSessions(result.items);
      if (result.items.length > 0) {
        const active = await getAgentChatSession(result.items[0].id);
        setSession(active);
      } else {
        setSession(null);
      }
    } catch (err) {
      setError(errorMessage(err, copy.loadError));
    } finally {
      setLoadingSessions(false);
    }
  }, [copy.loadError, storeId]);

  useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.messages?.length, session?.pending_actions?.length, loadingChat]);

  const refreshSessionList = useCallback(async (current: AgentChatSession) => {
    const result = await listAgentChatSessions(storeId);
    setSessions(result.items);
    setSession(current);
  }, [storeId]);

  async function openSession(id: number) {
    setLoadingChat(true);
    setError("");
    try {
      setSession(await getAgentChatSession(id));
    } catch (err) {
      setError(errorMessage(err, copy.loadError));
    } finally {
      setLoadingChat(false);
    }
  }

  async function newChat() {
    if (!storeId) return;
    setLoadingChat(true);
    setError("");
    try {
      const created = await createAgentChatSession(storeId, messageContext());
      await refreshSessionList(created);
      setInput("");
    } catch (err) {
      setError(errorMessage(err, copy.loadError));
    } finally {
      setLoadingChat(false);
    }
  }

  async function ensureSession() {
    if (session) return session;
    const created = await createAgentChatSession(storeId, messageContext());
    setSession(created);
    return created;
  }

  async function send(textOverride?: string) {
    const text = (textOverride ?? input).trim();
    if (!text || !storeId || loadingChat) return;

    setLoadingChat(true);
    setError("");
    if (!textOverride) setInput("");
    try {
      const current = await ensureSession();
      const updated = await sendAgentChatMessage(
        current.id,
        text,
        messageContext(),
      );
      await refreshSessionList(updated);
    } catch (err) {
      setError(errorMessage(err, copy.sendError));
      if (!textOverride) setInput(text);
    } finally {
      setLoadingChat(false);
    }
  }

  async function resolveApproval(call: AgentToolCall, approve: boolean) {
    if (!session || !call.approval) return;
    setApprovalBusy(call.approval.id);
    setError("");
    try {
      const updated = approve
        ? await approveAgentChatAction(session.id, call.approval.id)
        : await cancelAgentChatAction(session.id, call.approval.id);
      await refreshSessionList(updated);
    } catch (err) {
      setError(errorMessage(err, copy.sendError));
    } finally {
      setApprovalBusy(null);
    }
  }

  async function archiveCurrent() {
    if (!session || session.has_pending_turn) return;
    setLoadingChat(true);
    try {
      await archiveAgentChatSession(session.id);
      await loadSessions();
    } catch (err) {
      setError(errorMessage(err, copy.loadError));
    } finally {
      setLoadingChat(false);
    }
  }

  if (!storeId) {
    return (
      <section className={`copilot-page ${panelMode ? "copilot-panel-root" : ""}`}>
        <div className="copilot-no-store">
          <Bot size={28} />
          <h2>{copy.title}</h2>
          <p>Selecciona una tienda para usar el Copiloto.</p>
        </div>
      </section>
    );
  }

  const messages = session?.messages || [];
  const pendingActions = session?.pending_actions || [];

  return (
    <section className={`copilot-page ${panelMode ? "copilot-panel-root" : ""}`}>
      {!panelMode && (
      <aside className="copilot-sessions">
        <div className="copilot-sessions-header">
          <div>
            <span>DIAGLOB</span>
            <strong>{copy.history}</strong>
          </div>
          <button className="icon-button" title={copy.newChat} onClick={() => void newChat()}>
            <MessageSquarePlus size={16} />
          </button>
        </div>

        <button className="copilot-new-chat" onClick={() => void newChat()}>
          <Sparkles size={15} />
          {copy.newChat}
        </button>

        <div className="copilot-session-list">
          {loadingSessions && (
            <div className="copilot-session-loading">
              <Loader2 className="spin" size={16} />
              Cargando...
            </div>
          )}
          {sessions.map((item) => (
            <button
              key={item.id}
              className={`copilot-session-item ${session?.id === item.id ? "active" : ""}`}
              onClick={() => void openSession(item.id)}
            >
              <div>
                <strong>{item.title}</strong>
                <span>{new Date(item.updated_at).toLocaleString([], { dateStyle: "short", timeStyle: "short" })}</span>
              </div>
              <ChevronRight size={14} />
            </button>
          ))}
        </div>
      </aside>
      )}

      <div className="copilot-workspace">
        <header className="copilot-header">
          <div className="copilot-heading-icon">
            <Sparkles size={19} />
          </div>
          <div>
            <h1>{copy.title}</h1>
            <p>{copy.subtitle}</p>
          </div>
          <div className="copilot-header-meta">
            <span className="copilot-online"><span /> Permisos protegidos</span>
            {!panelMode && <span>{storeName || `Tienda #${storeId}`}</span>}
            {panelMode && (
              <button
                type="button"
                className="icon-button"
                title="Cerrar Copiloto"
                aria-label="Cerrar Copiloto"
                onClick={onClose}
              >
                <X size={16} />
              </button>
            )}
            {!panelMode && session && !session.has_pending_turn && (
              <button className="icon-button" title="Archivar chat" onClick={() => void archiveCurrent()}>
                <Archive size={15} />
              </button>
            )}
          </div>
        </header>

        {error && <div className="copilot-error">{error}</div>}

        {panelMode && (
          <div className="copilot-context-strip" data-copilot-private>
            <button
              type="button"
              className={`copilot-context-toggle ${includePageContext ? "is-active" : ""}`}
              aria-pressed={includePageContext}
              onClick={() => setIncludePageContext((current) => !current)}
            >
              <Sparkles size={14} />
              <span>
                <strong>Contexto de esta vista</strong>
                <small>{pageContext?.pageLabel || "Página actual"}</small>
              </span>
              <em>{includePageContext ? "Activo" : "Desactivado"}</em>
            </button>
            <p>
              {includePageContext
                ? "Se enviará texto visible de esta vista. No se incluyen formularios, campos de entrada, código ni elementos marcados como privados."
                : "El Copiloto responderá sin leer el contenido visible de esta vista."}
            </p>
          </div>
        )}

        <div className="copilot-transcript">
          {messages.length === 0 && !loadingChat ? (
            <div className="copilot-empty">
              <div className="copilot-empty-mark">
                <Bot size={28} />
              </div>
              <h2>{copy.emptyTitle}</h2>
              <p>{copy.emptyBody}</p>
              <div className="copilot-suggestions">
                {activeSuggestions.map((suggestion) => (
                  <button key={suggestion} onClick={() => void send(suggestion)}>
                    <Sparkles size={14} />
                    <span>{suggestion}</span>
                    <ChevronRight size={14} />
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="copilot-messages">
              {messages.map((message) => (
                <article key={message.id} className={`copilot-message ${message.role}`}>
                  <div className="copilot-avatar">
                    {message.role === "assistant" ? <Bot size={16} /> : <span>Tú</span>}
                  </div>
                  <div className="copilot-message-body">
                    {message.text && <div className="copilot-message-text">{message.text}</div>}
                    {message.tool_calls.length > 0 && (
                      <div className="copilot-tools">
                        {message.tool_calls.map((call) => (
                          <ToolActivity key={call.id} call={call} />
                        ))}
                      </div>
                    )}
                    <small>
                      {new Date(message.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </small>
                  </div>
                </article>
              ))}

              {pendingActions.map((call) => (
                <ApprovalCard
                  key={call.id}
                  call={call}
                  busy={approvalBusy === call.approval?.id}
                  onApprove={() => void resolveApproval(call, true)}
                  onCancel={() => void resolveApproval(call, false)}
                />
              ))}

              {loadingChat && (
                <div className="copilot-thinking">
                  <Loader2 className="spin" size={16} />
                  <span>Diaglob está trabajando...</span>
                </div>
              )}
              <div ref={endRef} />
            </div>
          )}
        </div>

        <footer className="copilot-composer" data-copilot-private>
          <div className="copilot-composer-box">
            <textarea
              value={input}
              rows={1}
              disabled={loadingChat || pendingActions.length > 0}
              placeholder={
                pendingActions.length > 0
                  ? "Aprueba o cancela la acción pendiente para continuar."
                  : copy.placeholder
              }
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void send();
                }
              }}
            />
            <button
              className="copilot-send"
              disabled={!input.trim() || loadingChat || pendingActions.length > 0}
              onClick={() => void send()}
            >
              {loadingChat ? <Loader2 className="spin" size={17} /> : <Send size={17} />}
            </button>
          </div>
          <p>
            {panelMode && includePageContext
              ? `Usando contexto de ${pageContext?.pageLabel || "esta vista"} · Las acciones sensibles siguen requiriendo aprobación.`
              : "El Copiloto solo puede usar herramientas permitidas para tu rol y tienda. Las acciones sensibles requieren tu aprobación."}
          </p>
        </footer>
      </div>
    </section>
  );
}
