import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Bot,
  Check,
  ExternalLink,
  LoaderCircle,
  Pencil,
  UserRound,
  X,
} from "lucide-react";

import { getAgents, type Agent } from "../services/agents";
import {
  listAttributedCommerceOrders,
  updateOrderSalesAttribution,
  type AttributedCommerceOrder,
} from "../services/orderAttribution";
import { getTeam, type TeamMember } from "../services/team";
import type { CommerceOrder } from "../services/integrations";
import "../commerce-order-attribution.css";


type LocaleKey = "es" | "en" | "pt-BR";
type AttributionDraftType = "human" | "ai" | "unattributed";


interface CommerceOrdersProps {
  storeId: number;
  canWrite: boolean;
  initialOrderId?: number;
  searchRequestKey?: number;
}


const COPY = {
  es: {
    closer: "Cerrada por",
    human: "Equipo",
    ai: "IA",
    unattributed: "Sin atribución",
    manual: "Corregida manualmente",
    assign: "Asignar",
    change: "Cambiar",
    editTitle: "Corregir atribución de venta",
    editHelp: "Selecciona quién cerró realmente esta venta. El cambio alimentará las estadísticas y quedará auditado.",
    employee: "Empleado",
    aiAgent: "Agente IA",
    chooseEmployee: "Selecciona un empleado",
    chooseAgent: "Selecciona un agente IA",
    save: "Guardar",
    cancel: "Cancelar",
    saving: "Guardando...",
    saved: "Atribución actualizada.",
    optionsError: "No se pudieron cargar todos los empleados o agentes. Puedes seguir viendo los pedidos.",
    saveError: "No se pudo actualizar la atribución de esta venta.",
    info: "Los pedidos importados pueden aparecer sin atribución. Puedes asignarlos al empleado o agente IA que realmente cerró la venta.",
  },
  en: {
    closer: "Closed by",
    human: "Team",
    ai: "AI",
    unattributed: "Unattributed",
    manual: "Manually corrected",
    assign: "Assign",
    change: "Change",
    editTitle: "Correct sales attribution",
    editHelp: "Select who actually closed this sale. The change will feed analytics and remain audited.",
    employee: "Employee",
    aiAgent: "AI agent",
    chooseEmployee: "Select an employee",
    chooseAgent: "Select an AI agent",
    save: "Save",
    cancel: "Cancel",
    saving: "Saving...",
    saved: "Attribution updated.",
    optionsError: "Not all employees or agents could be loaded. You can keep viewing orders.",
    saveError: "This sale attribution could not be updated.",
    info: "Imported orders may appear unattributed. You can assign them to the employee or AI agent who actually closed the sale.",
  },
  "pt-BR": {
    closer: "Fechada por",
    human: "Equipe",
    ai: "IA",
    unattributed: "Sem atribuição",
    manual: "Corrigida manualmente",
    assign: "Atribuir",
    change: "Alterar",
    editTitle: "Corrigir atribuição da venda",
    editHelp: "Selecione quem realmente fechou esta venda. A alteração alimentará as estatísticas e ficará auditada.",
    employee: "Colaborador",
    aiAgent: "Agente IA",
    chooseEmployee: "Selecione um colaborador",
    chooseAgent: "Selecione um agente IA",
    save: "Salvar",
    cancel: "Cancelar",
    saving: "Salvando...",
    saved: "Atribuição atualizada.",
    optionsError: "Nem todos os colaboradores ou agentes puderam ser carregados. Você pode continuar vendo os pedidos.",
    saveError: "Não foi possível atualizar a atribuição desta venda.",
    info: "Pedidos importados podem aparecer sem atribuição. Você pode atribuí-los ao colaborador ou agente IA que realmente fechou a venda.",
  },
} as const;


function resolveLocale(language: string): LocaleKey {
  if (language.toLowerCase().startsWith("pt")) return "pt-BR";
  if (language.toLowerCase().startsWith("en")) return "en";
  return "es";
}


function getStatusBadgeClass(order: CommerceOrder): string {
  if (order.external_creation_status === "failed") return "failed";
  if (order.external_creation_status === "pending") return "pending";
  if (order.external_creation_status === "created") return "created";
  return "unknown";
}


function getStatusLabel(order: CommerceOrder, t: (key: string) => string): string {
  if (order.external_creation_status === "failed") {
    return t("commerceOrderStatusFailed");
  }
  if (order.external_creation_status === "pending") {
    return t("commerceOrderStatusPending");
  }
  if (order.external_creation_status === "created") {
    return t("commerceOrderStatusCreated");
  }
  if (order.external_creation_status === "unknown") {
    return t("commerceOrderStatusUnknown");
  }
  return t("commerceOrderStatusHistorical");
}


export default function CommerceOrders({
  storeId,
  canWrite,
  initialOrderId,
  searchRequestKey,
}: CommerceOrdersProps) {
  const { t, i18n } = useTranslation();
  const copy = COPY[resolveLocale(i18n.language)];

  const [orders, setOrders] = useState<AttributedCommerceOrder[]>([]);
  const [team, setTeam] = useState<TeamMember[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [optionsError, setOptionsError] = useState("");
  const [editingOrderId, setEditingOrderId] = useState<number | null>(null);
  const [draftType, setDraftType] = useState<AttributionDraftType>("human");
  const [draftActorId, setDraftActorId] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState("");
  const [saveError, setSaveError] = useState("");
  const focusedOrderRef = useRef<HTMLTableRowElement>(null);

  const employees = useMemo(
    () => team.filter(
      (member) =>
        member.active
        && (
          member.all_stores
          || member.stores.some((store) => store.id === storeId)
        ),
    ),
    [team, storeId],
  );

  const storeAgents = useMemo(
    () => agents.filter(
      (agent) =>
        agent.active
        && agent.stores.some((store) => store.id === storeId),
    ),
    [agents, storeId],
  );

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");
      setOptionsError("");
      setEditingOrderId(null);

      const requests: Promise<unknown>[] = [
        listAttributedCommerceOrders(storeId),
      ];
      if (canWrite) {
        requests.push(getTeam(), getAgents());
      }

      const results = await Promise.allSettled(requests);
      if (cancelled) return;

      const orderResult = results[0];
      if (orderResult.status === "rejected") {
        setError(t("commerceOrdersError"));
        setLoading(false);
        return;
      }

      const orderData = orderResult.value as Awaited<
        ReturnType<typeof listAttributedCommerceOrders>
      >;
      setOrders(orderData.items);

      if (canWrite) {
        const teamResult = results[1];
        const agentsResult = results[2];

        if (teamResult?.status === "fulfilled") {
          const teamData = teamResult.value as Awaited<ReturnType<typeof getTeam>>;
          setTeam(teamData.items);
        } else {
          setTeam([]);
          setOptionsError(copy.optionsError);
        }

        if (agentsResult?.status === "fulfilled") {
          const agentData = agentsResult.value as Awaited<ReturnType<typeof getAgents>>;
          setAgents(agentData.items);
        } else {
          setAgents([]);
          setOptionsError(copy.optionsError);
        }
      } else {
        setTeam([]);
        setAgents([]);
      }

      setLoading(false);
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [storeId, canWrite, t, copy.optionsError]);

  useEffect(() => {
    if (loading || !initialOrderId) return;

    const timer = window.setTimeout(() => {
      focusedOrderRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }, 60);

    return () => window.clearTimeout(timer);
  }, [loading, initialOrderId, searchRequestKey]);

  function startEditing(order: AttributedCommerceOrder) {
    const attribution = order.sales_attribution;
    setEditingOrderId(order.id);
    setSaveMessage("");
    setSaveError("");

    if (attribution?.actor_type === "human") {
      setDraftType("human");
      setDraftActorId(String(attribution.actor_id ?? ""));
    } else if (attribution?.actor_type === "ai") {
      setDraftType("ai");
      setDraftActorId(String(attribution.actor_id ?? ""));
    } else {
      setDraftType("human");
      setDraftActorId("");
    }
  }

  function cancelEditing() {
    setEditingOrderId(null);
    setDraftActorId("");
    setSaveError("");
  }

  function changeDraftType(nextType: AttributionDraftType) {
    setDraftType(nextType);
    setDraftActorId("");
    setSaveError("");
  }

  async function saveAttribution(orderId: number) {
    if (draftType !== "unattributed" && !draftActorId) return;

    setSaving(true);
    setSaveError("");
    setSaveMessage("");

    try {
      const result = await updateOrderSalesAttribution(
        storeId,
        orderId,
        draftType === "unattributed"
          ? { actor_type: null, actor_id: null }
          : {
              actor_type: draftType,
              actor_id: Number(draftActorId),
            },
      );

      setOrders((current) => current.map(
        (order) => order.id === orderId
          ? { ...order, sales_attribution: result.sales_attribution }
          : order,
      ));
      setEditingOrderId(null);
      setSaveMessage(copy.saved);
    } catch (err: unknown) {
      const apiError = err as {
        response?: { data?: { detail?: string } };
      };
      setSaveError(apiError.response?.data?.detail || copy.saveError);
    } finally {
      setSaving(false);
    }
  }

  function attributionLabel(order: AttributedCommerceOrder) {
    const attribution = order.sales_attribution;
    if (!attribution) {
      return (
        <span className="order-attribution-badge unattributed">
          {copy.unattributed}
        </span>
      );
    }

    const isHuman = attribution.actor_type === "human";
    return (
      <div className="order-attribution-cell">
        <span className={`order-attribution-badge ${attribution.actor_type}`}>
          {isHuman ? <UserRound size={13} /> : <Bot size={13} />}
          {isHuman ? copy.human : copy.ai} · {attribution.actor_label}
        </span>
        {attribution.source === "manual_reclassification" && (
          <small>{copy.manual}</small>
        )}
      </div>
    );
  }

  if (loading) {
    return (
      <div className="commerce-loading">
        <LoaderCircle className="spin" size={24} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="commerce-empty">
        <p>{error}</p>
      </div>
    );
  }

  if (orders.length === 0) {
    return (
      <div className="commerce-empty">
        <p>{t("commerceNoOrders")}</p>
      </div>
    );
  }

  return (
    <div className="commerce-orders">
      <div className="commerce-orders-meta">
        <div className="commerce-count">
          {t("commerceOrdersCount", { count: orders.length })}
        </div>
        <p className="order-attribution-info">{copy.info}</p>
      </div>

      {optionsError && (
        <div className="order-attribution-notice warning">{optionsError}</div>
      )}
      {saveMessage && (
        <div className="order-attribution-notice success">
          <Check size={15} /> {saveMessage}
        </div>
      )}

      <div className="commerce-orders-table-wrapper">
        <table className="commerce-orders-table attribution-enabled">
          <thead>
            <tr>
              <th>{t("commerceOrderNumber")}</th>
              <th>{t("commerceOrderTotal")}</th>
              <th>{t("commerceOrderStatus")}</th>
              <th>{copy.closer}</th>
              <th>{t("commerceOrderSource")}</th>
              <th>{t("commerceOrderDate")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {orders.map((order) => (
              <>
                <tr
                  key={order.id}
                  ref={order.id === initialOrderId ? focusedOrderRef : undefined}
                  className={order.id === initialOrderId ? "commerce-order-search-hit" : undefined}
                >
                  <td className="commerce-order-number">#{order.order_number}</td>
                  <td>{order.currency} {order.total_amount.toFixed(2)}</td>
                  <td>
                    <span className={`commerce-badge ${getStatusBadgeClass(order)}`}>
                      {getStatusLabel(order, t)}
                    </span>
                  </td>
                  <td>{attributionLabel(order)}</td>
                  <td className="commerce-order-source">{order.source ?? "—"}</td>
                  <td className="commerce-order-date">
                    {order.created_at
                      ? new Date(order.created_at).toLocaleDateString()
                      : "—"}
                  </td>
                  <td className="order-attribution-actions">
                    {canWrite && (
                      <button
                        type="button"
                        className="order-attribution-edit-button"
                        onClick={() => startEditing(order)}
                        aria-label={order.sales_attribution ? copy.change : copy.assign}
                      >
                        <Pencil size={14} />
                        <span>{order.sales_attribution ? copy.change : copy.assign}</span>
                      </button>
                    )}
                    {order.invoice_url && (
                      <a
                        href={order.invoice_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="commerce-link"
                      >
                        <ExternalLink size={14} />
                      </a>
                    )}
                  </td>
                </tr>

                {editingOrderId === order.id && (
                  <tr key={`${order.id}-editor`} className="order-attribution-editor-row">
                    <td colSpan={7}>
                      <div className="order-attribution-editor">
                        <div className="order-attribution-editor-heading">
                          <div>
                            <strong>{copy.editTitle}</strong>
                            <p>{copy.editHelp}</p>
                          </div>
                          <button
                            type="button"
                            className="order-attribution-close"
                            onClick={cancelEditing}
                            disabled={saving}
                            aria-label={copy.cancel}
                          >
                            <X size={16} />
                          </button>
                        </div>

                        <div className="order-attribution-type-picker">
                          <button
                            type="button"
                            className={draftType === "human" ? "active" : ""}
                            onClick={() => changeDraftType("human")}
                          >
                            <UserRound size={15} /> {copy.human}
                          </button>
                          <button
                            type="button"
                            className={draftType === "ai" ? "active" : ""}
                            onClick={() => changeDraftType("ai")}
                          >
                            <Bot size={15} /> {copy.ai}
                          </button>
                          <button
                            type="button"
                            className={draftType === "unattributed" ? "active" : ""}
                            onClick={() => changeDraftType("unattributed")}
                          >
                            {copy.unattributed}
                          </button>
                        </div>

                        {draftType !== "unattributed" && (
                          <label className="order-attribution-select-field">
                            <span>{draftType === "human" ? copy.employee : copy.aiAgent}</span>
                            <select
                              value={draftActorId}
                              onChange={(event) => setDraftActorId(event.target.value)}
                            >
                              <option value="">
                                {draftType === "human"
                                  ? copy.chooseEmployee
                                  : copy.chooseAgent}
                              </option>
                              {(draftType === "human" ? employees : storeAgents).map((actor) => (
                                <option
                                  key={draftType === "human"
                                    ? (actor as TeamMember).user_id
                                    : actor.id}
                                  value={draftType === "human"
                                    ? (actor as TeamMember).user_id
                                    : actor.id}
                                >
                                  {actor.name}
                                </option>
                              ))}
                            </select>
                          </label>
                        )}

                        {saveError && (
                          <div className="order-attribution-inline-error">{saveError}</div>
                        )}

                        <div className="order-attribution-editor-footer">
                          <button
                            type="button"
                            className="order-attribution-secondary"
                            onClick={cancelEditing}
                            disabled={saving}
                          >
                            {copy.cancel}
                          </button>
                          <button
                            type="button"
                            className="order-attribution-primary"
                            onClick={() => void saveAttribution(order.id)}
                            disabled={
                              saving
                              || (draftType !== "unattributed" && !draftActorId)
                            }
                          >
                            {saving && <LoaderCircle className="spin" size={14} />}
                            {saving ? copy.saving : copy.save}
                          </button>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
