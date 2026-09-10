import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  CircleDot,
  LoaderCircle,
  RefreshCw,
  Scale,
  ShieldCheck,
  ShieldX,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  getAdminRiskDispute,
  getAdminRiskReport,
  getAdminRiskStats,
  listAdminRiskDisputes,
  listAdminRiskReports,
  moderateAdminRiskReport,
  resolveAdminRiskDispute,
  type AdminRiskDisputeDetail,
  type AdminRiskDisputeListItem,
  type AdminRiskReportDetail,
  type AdminRiskReportListItem,
  type AdminRiskStats,
  type RiskDisputeStatus,
  type RiskReportStatus,
} from "../services/adminRisk";
import type { CustomerRiskReason } from "../services/customerRisk";
import "../customer-risk-moderation.css";
import "../customer-risk-moderation-v2.css";


type LocaleKey = "es" | "en" | "pt-BR";
type Tab = "reports" | "disputes";

const PAGE_SIZE = 25;

const COPY = {
  es: {
    title: "Moderación de riesgo",
    subtitle: "Cola interna de señales compartidas, apelaciones y auditoría.",
    platformAdmin: "Administrador de plataforma",
    open: "Abrir moderación",
    close: "Cerrar moderación",
    reports: "Reportes",
    report: "Reporte",
    disputes: "Apelaciones",
    appeal: "Apelación",
    pending: "Pendientes",
    confirmed: "Confirmados",
    disputed: "En disputa",
    dismissed: "Descartados",
    openDisputes: "Apelaciones abiertas",
    rateLimit: "Límite 24 h",
    reportWrites: "reportes/org",
    disputeWrites: "apelaciones/org",
    all: "Todos los estados",
    allReasons: "Todos los motivos",
    statusFilter: "Filtrar por estado",
    reasonFilter: "Filtrar por motivo",
    priority: "Prioridad",
    organization: "Organización",
    reporter: "Reportante",
    reputation: "Reputación",
    evidence: "Evidencia",
    notes: "Notas privadas",
    noEvidence: "Sin referencia de evidencia",
    noNotes: "Sin notas privadas",
    customer: "Cliente relacionado",
    masked: "Identificadores enmascarados",
    moderation: "Decisión de moderación",
    moderationNote: "Motivo de la decisión (obligatorio)",
    confirm: "Confirmar señal",
    dismiss: "Descartar señal",
    markDisputed: "Marcar en disputa",
    resetPending: "Volver a pendiente",
    acceptDispute: "Aceptar apelación",
    rejectDispute: "Rechazar apelación",
    audit: "Historial inmutable",
    noAudit: "Todavía no hay eventos de auditoría.",
    noItems: "No hay elementos para este filtro.",
    selectItem: "Selecciona un elemento de la cola para revisarlo.",
    loading: "Cargando moderación...",
    loadFailed: "No se pudo cargar la cola de moderación.",
    actionFailed: "No se pudo guardar la decisión.",
    saving: "Guardando...",
    refresh: "Actualizar",
    status: "Estado",
    reason: "Motivo",
    disputesCount: "apelaciones abiertas",
    statement: "Declaración de la apelación",
    resolution: "Resolución",
    matchingReports: "Señales externas coincidentes",
    established: "Establecida",
    trusted: "Confiable",
    watch: "Revisar",
    newReporter: "Nueva",
    moderatedReports: "reportes moderados",
    pageInfo: "elementos",
    page: "Página",
    of: "de",
    previous: "Anterior",
    next: "Siguiente",
    privacy: "Esta consola es interna. La identidad del reportante y su evidencia nunca se exponen a otras organizaciones.",
    statuses: {
      pending: "Pendiente",
      confirmed: "Confirmado",
      disputed: "En disputa",
      dismissed: "Descartado",
      open: "Abierta",
      accepted: "Aceptada",
      rejected: "Rechazada",
      withdrawn: "Retirada",
    },
    reasons: {
      suspected_fraud: "Posible fraude",
      payment_abuse: "Pago o contracargo",
      delivery_claim: "Reclamo de entrega",
      identity_mismatch: "Identidad inconsistente",
      abusive_behavior: "Comportamiento abusivo",
      other: "Otro",
    },
    auditActions: {
      report_submitted: "Reporte enviado",
      report_updated: "Reporte actualizado",
      moderation_confirmed: "Señal confirmada",
      moderation_dismissed: "Señal descartada",
      moderation_disputed: "Señal marcada en disputa",
      moderation_reset_pending: "Señal restablecida a pendiente",
      dispute_submitted: "Apelación enviada",
      dispute_updated: "Apelación actualizada",
      dispute_accepted: "Apelación aceptada",
      dispute_rejected: "Apelación rechazada",
      dispute_withdrawn: "Apelación retirada",
    },
    actorRoles: {
      platform_admin: "Administrador de plataforma",
      reporter: "Reportante",
      requester: "Solicitante",
      system: "Sistema",
    },
  },
  en: {
    title: "Risk moderation",
    subtitle: "Internal queue for shared signals, appeals, and audit history.",
    platformAdmin: "Platform admin",
    open: "Open moderation",
    close: "Close moderation",
    reports: "Reports",
    report: "Report",
    disputes: "Appeals",
    appeal: "Appeal",
    pending: "Pending",
    confirmed: "Confirmed",
    disputed: "Disputed",
    dismissed: "Dismissed",
    openDisputes: "Open appeals",
    rateLimit: "24 h limit",
    reportWrites: "reports/org",
    disputeWrites: "appeals/org",
    all: "All statuses",
    allReasons: "All reasons",
    statusFilter: "Filter by status",
    reasonFilter: "Filter by reason",
    priority: "Priority",
    organization: "Organization",
    reporter: "Reporter",
    reputation: "Reputation",
    evidence: "Evidence",
    notes: "Private notes",
    noEvidence: "No evidence reference",
    noNotes: "No private notes",
    customer: "Related customer",
    masked: "Masked identifiers",
    moderation: "Moderation decision",
    moderationNote: "Decision reason (required)",
    confirm: "Confirm signal",
    dismiss: "Dismiss signal",
    markDisputed: "Mark disputed",
    resetPending: "Reset to pending",
    acceptDispute: "Accept appeal",
    rejectDispute: "Reject appeal",
    audit: "Immutable history",
    noAudit: "There are no audit events yet.",
    noItems: "No items match this filter.",
    selectItem: "Select an item from the queue to review it.",
    loading: "Loading moderation...",
    loadFailed: "The moderation queue could not be loaded.",
    actionFailed: "The decision could not be saved.",
    saving: "Saving...",
    refresh: "Refresh",
    status: "Status",
    reason: "Reason",
    disputesCount: "open appeals",
    statement: "Appeal statement",
    resolution: "Resolution",
    matchingReports: "Matching external signals",
    established: "Established",
    trusted: "Trusted",
    watch: "Review",
    newReporter: "New",
    moderatedReports: "moderated reports",
    pageInfo: "items",
    page: "Page",
    of: "of",
    previous: "Previous",
    next: "Next",
    privacy: "This console is internal. Reporter identity and evidence are never exposed to other organizations.",
    statuses: {
      pending: "Pending",
      confirmed: "Confirmed",
      disputed: "Disputed",
      dismissed: "Dismissed",
      open: "Open",
      accepted: "Accepted",
      rejected: "Rejected",
      withdrawn: "Withdrawn",
    },
    reasons: {
      suspected_fraud: "Suspected fraud",
      payment_abuse: "Payment or chargeback",
      delivery_claim: "Delivery claim",
      identity_mismatch: "Identity mismatch",
      abusive_behavior: "Abusive behavior",
      other: "Other",
    },
    auditActions: {
      report_submitted: "Report submitted",
      report_updated: "Report updated",
      moderation_confirmed: "Signal confirmed",
      moderation_dismissed: "Signal dismissed",
      moderation_disputed: "Signal marked disputed",
      moderation_reset_pending: "Signal reset to pending",
      dispute_submitted: "Appeal submitted",
      dispute_updated: "Appeal updated",
      dispute_accepted: "Appeal accepted",
      dispute_rejected: "Appeal rejected",
      dispute_withdrawn: "Appeal withdrawn",
    },
    actorRoles: {
      platform_admin: "Platform admin",
      reporter: "Reporter",
      requester: "Requester",
      system: "System",
    },
  },
  "pt-BR": {
    title: "Moderação de risco",
    subtitle: "Fila interna de sinais compartilhados, contestações e auditoria.",
    platformAdmin: "Administrador da plataforma",
    open: "Abrir moderação",
    close: "Fechar moderação",
    reports: "Relatos",
    report: "Relato",
    disputes: "Contestações",
    appeal: "Contestação",
    pending: "Pendentes",
    confirmed: "Confirmados",
    disputed: "Em disputa",
    dismissed: "Descartados",
    openDisputes: "Contestações abertas",
    rateLimit: "Limite 24 h",
    reportWrites: "relatos/org",
    disputeWrites: "contestações/org",
    all: "Todos os estados",
    allReasons: "Todos os motivos",
    statusFilter: "Filtrar por estado",
    reasonFilter: "Filtrar por motivo",
    priority: "Prioridade",
    organization: "Organização",
    reporter: "Reportante",
    reputation: "Reputação",
    evidence: "Evidência",
    notes: "Notas privadas",
    noEvidence: "Sem referência de evidência",
    noNotes: "Sem notas privadas",
    customer: "Cliente relacionado",
    masked: "Identificadores mascarados",
    moderation: "Decisão de moderação",
    moderationNote: "Motivo da decisão (obrigatório)",
    confirm: "Confirmar sinal",
    dismiss: "Descartar sinal",
    markDisputed: "Marcar em disputa",
    resetPending: "Voltar a pendente",
    acceptDispute: "Aceitar contestação",
    rejectDispute: "Rejeitar contestação",
    audit: "Histórico imutável",
    noAudit: "Ainda não há eventos de auditoria.",
    noItems: "Nenhum item para este filtro.",
    selectItem: "Selecione um item da fila para revisar.",
    loading: "Carregando moderação...",
    loadFailed: "Não foi possível carregar a fila de moderação.",
    actionFailed: "Não foi possível salvar a decisão.",
    saving: "Salvando...",
    refresh: "Atualizar",
    status: "Estado",
    reason: "Motivo",
    disputesCount: "contestações abertas",
    statement: "Declaração da contestação",
    resolution: "Resolução",
    matchingReports: "Sinais externos coincidentes",
    established: "Estabelecida",
    trusted: "Confiável",
    watch: "Revisar",
    newReporter: "Nova",
    moderatedReports: "relatos moderados",
    pageInfo: "itens",
    page: "Página",
    of: "de",
    previous: "Anterior",
    next: "Próxima",
    privacy: "Este console é interno. A identidade do reportante e suas evidências nunca são expostas a outras organizações.",
    statuses: {
      pending: "Pendente",
      confirmed: "Confirmado",
      disputed: "Em disputa",
      dismissed: "Descartado",
      open: "Aberta",
      accepted: "Aceita",
      rejected: "Rejeitada",
      withdrawn: "Retirada",
    },
    reasons: {
      suspected_fraud: "Possível fraude",
      payment_abuse: "Pagamento ou chargeback",
      delivery_claim: "Reclamação de entrega",
      identity_mismatch: "Identidade inconsistente",
      abusive_behavior: "Comportamento abusivo",
      other: "Outro",
    },
    auditActions: {
      report_submitted: "Relato enviado",
      report_updated: "Relato atualizado",
      moderation_confirmed: "Sinal confirmado",
      moderation_dismissed: "Sinal descartado",
      moderation_disputed: "Sinal marcado em disputa",
      moderation_reset_pending: "Sinal redefinido como pendente",
      dispute_submitted: "Contestação enviada",
      dispute_updated: "Contestação atualizada",
      dispute_accepted: "Contestação aceita",
      dispute_rejected: "Contestação rejeitada",
      dispute_withdrawn: "Contestação retirada",
    },
    actorRoles: {
      platform_admin: "Administrador da plataforma",
      reporter: "Reportante",
      requester: "Solicitante",
      system: "Sistema",
    },
  },
} as const;

type ModerationCopy = (typeof COPY)[LocaleKey];

function localeFor(language: string): LocaleKey {
  if (language.toLowerCase().startsWith("pt")) return "pt-BR";
  if (language.toLowerCase().startsWith("en")) return "en";
  return "es";
}

function humanizeCode(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function statusLabel(status: string, copy: ModerationCopy): string {
  return copy.statuses[status as keyof typeof copy.statuses] ?? humanizeCode(status);
}

function auditActionLabel(action: string, copy: ModerationCopy): string {
  return copy.auditActions[action as keyof typeof copy.auditActions] ?? humanizeCode(action);
}

function actorRoleLabel(role: string, copy: ModerationCopy): string {
  return copy.actorRoles[role as keyof typeof copy.actorRoles] ?? humanizeCode(role);
}

function formatDate(value: string | null, locale: LocaleKey): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(locale);
}

export default function CustomerRiskModerationPanel() {
  const { i18n } = useTranslation();
  const locale = localeFor(i18n.language);
  const copy = COPY[locale];
  const [stats, setStats] = useState<AdminRiskStats | null>(null);
  const [authorized, setAuthorized] = useState<boolean | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [tab, setTab] = useState<Tab>("reports");
  const [reportStatus, setReportStatus] = useState<RiskReportStatus | "">("pending");
  const [reportReason, setReportReason] = useState<CustomerRiskReason | "">("");
  const [disputeStatus, setDisputeStatus] = useState<RiskDisputeStatus | "">("open");
  const [reports, setReports] = useState<AdminRiskReportListItem[]>([]);
  const [disputes, setDisputes] = useState<AdminRiskDisputeListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [reportDetail, setReportDetail] = useState<AdminRiskReportDetail | null>(null);
  const [disputeDetail, setDisputeDetail] = useState<AdminRiskDisputeDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function probe() {
      try {
        const next = await getAdminRiskStats();
        if (!cancelled) {
          setStats(next);
          setAuthorized(true);
        }
      } catch (err: unknown) {
        if (cancelled) return;
        const apiError = err as { response?: { status?: number } };
        if (apiError.response?.status === 403) {
          setAuthorized(false);
        } else {
          setAuthorized(false);
        }
      }
    }
    void probe();
    return () => {
      cancelled = true;
    };
  }, []);

  const activeDetail = tab === "reports" ? reportDetail : disputeDetail;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  async function refreshStats() {
    setStats(await getAdminRiskStats());
  }

  async function fetchReportQueue(targetPage: number) {
    const result = await listAdminRiskReports({
      page: targetPage,
      page_size: PAGE_SIZE,
      status: reportStatus,
      reason: reportReason,
    });
    setReports(result.items);
    setTotal(result.total);
    return result;
  }

  async function fetchDisputeQueue(targetPage: number) {
    const result = await listAdminRiskDisputes({
      page: targetPage,
      page_size: PAGE_SIZE,
      status: disputeStatus,
    });
    setDisputes(result.items);
    setTotal(result.total);
    return result;
  }

  async function loadQueue(nextTab = tab, targetPage = page) {
    setLoading(true);
    setError("");
    try {
      if (nextTab === "reports") {
        await fetchReportQueue(targetPage);
      } else {
        await fetchDisputeQueue(targetPage);
      }
      await refreshStats();
    } catch {
      setError(copy.loadFailed);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!expanded || !authorized) return;
    setReportDetail(null);
    setDisputeDetail(null);
    setNote("");
    void loadQueue();
    // Filters, pagination and the active tab intentionally trigger a fresh server read.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expanded, authorized, tab, reportStatus, reportReason, disputeStatus, page]);

  async function selectReport(id: number) {
    setDetailLoading(true);
    setError("");
    setNote("");
    try {
      setReportDetail(await getAdminRiskReport(id));
      setDisputeDetail(null);
    } catch {
      setError(copy.loadFailed);
    } finally {
      setDetailLoading(false);
    }
  }

  async function selectDispute(id: number) {
    setDetailLoading(true);
    setError("");
    setNote("");
    try {
      setDisputeDetail(await getAdminRiskDispute(id));
      setReportDetail(null);
    } catch {
      setError(copy.loadFailed);
    } finally {
      setDetailLoading(false);
    }
  }

  async function moderateReport(
    action: "confirm" | "dismiss" | "mark_disputed" | "reset_pending",
  ) {
    if (!reportDetail || note.trim().length < 5) return;
    const currentId = reportDetail.id;
    const currentIndex = Math.max(0, reports.findIndex((item) => item.id === currentId));
    setSaving(true);
    setError("");
    try {
      await moderateAdminRiskReport(currentId, {
        action,
        note: note.trim(),
      });
      setNote("");
      const result = await fetchReportQueue(page);
      await refreshStats();
      const candidates = result.items.filter((item) => item.id !== currentId);
      if (candidates.length > 0) {
        await selectReport(candidates[Math.min(currentIndex, candidates.length - 1)].id);
      } else if (page > 1 && result.total > 0) {
        setReportDetail(null);
        setPage((value) => Math.max(1, value - 1));
      } else {
        setReportDetail(null);
      }
    } catch {
      setError(copy.actionFailed);
    } finally {
      setSaving(false);
    }
  }

  async function resolveDispute(outcome: "accepted" | "rejected") {
    if (!disputeDetail || note.trim().length < 5) return;
    const currentId = disputeDetail.id;
    const currentIndex = Math.max(0, disputes.findIndex((item) => item.id === currentId));
    setSaving(true);
    setError("");
    try {
      await resolveAdminRiskDispute(currentId, {
        outcome,
        note: note.trim(),
      });
      setNote("");
      const result = await fetchDisputeQueue(page);
      await refreshStats();
      const candidates = result.items.filter((item) => item.id !== currentId);
      if (candidates.length > 0) {
        await selectDispute(candidates[Math.min(currentIndex, candidates.length - 1)].id);
      } else if (page > 1 && result.total > 0) {
        setDisputeDetail(null);
        setPage((value) => Math.max(1, value - 1));
      } else {
        setDisputeDetail(null);
      }
    } catch {
      setError(copy.actionFailed);
    } finally {
      setSaving(false);
    }
  }

  const reputationLabel = useMemo(() => {
    const level = reportDetail?.reporter.reputation.level;
    if (!level) return "";
    if (level === "trusted") return copy.trusted;
    if (level === "watch") return copy.watch;
    if (level === "established") return copy.established;
    return copy.newReporter;
  }, [copy, reportDetail]);

  if (authorized !== true || !stats) return null;

  return (
    <section className={`risk-moderation-shell ${expanded ? "expanded" : ""}`}>
      <div className="risk-moderation-header">
        <div>
          <span className="risk-moderation-eyebrow"><ShieldCheck size={14} /> {copy.platformAdmin}</span>
          <h2>{copy.title}</h2>
          <p>{copy.subtitle}</p>
        </div>
        <button
          type="button"
          className="risk-moderation-toggle"
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? copy.close : copy.open}
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
      </div>

      <div className="risk-moderation-stats">
        <div><strong>{stats.reports.pending}</strong><span>{copy.pending}</span></div>
        <div><strong>{stats.reports.confirmed}</strong><span>{copy.confirmed}</span></div>
        <div><strong>{stats.reports.disputed}</strong><span>{copy.disputed}</span></div>
        <div><strong>{stats.disputes.open}</strong><span>{copy.openDisputes}</span></div>
        <div className="limit-card">
          <strong>{copy.rateLimit}</strong>
          <span>{stats.limits.report_writes_24h} {copy.reportWrites}</span>
          <span>{stats.limits.dispute_writes_24h} {copy.disputeWrites}</span>
        </div>
      </div>

      {expanded && (
        <div className="risk-moderation-console">
          <div className="risk-moderation-toolbar">
            <div className="risk-moderation-tabs">
              <button
                type="button"
                className={tab === "reports" ? "active" : ""}
                onClick={() => {
                  setTab("reports");
                  setPage(1);
                }}
              >
                <ShieldCheck size={15} /> {copy.reports}
              </button>
              <button
                type="button"
                className={tab === "disputes" ? "active" : ""}
                onClick={() => {
                  setTab("disputes");
                  setPage(1);
                }}
              >
                <Scale size={15} /> {copy.disputes}
              </button>
            </div>

            {tab === "reports" ? (
              <>
                <select
                  aria-label={copy.statusFilter}
                  value={reportStatus}
                  onChange={(event) => {
                    setReportStatus(event.target.value as RiskReportStatus | "");
                    setPage(1);
                  }}
                >
                  <option value="">{copy.all}</option>
                  <option value="pending">{copy.statuses.pending}</option>
                  <option value="confirmed">{copy.statuses.confirmed}</option>
                  <option value="disputed">{copy.statuses.disputed}</option>
                  <option value="dismissed">{copy.statuses.dismissed}</option>
                </select>
                <select
                  aria-label={copy.reasonFilter}
                  value={reportReason}
                  onChange={(event) => {
                    setReportReason(event.target.value as CustomerRiskReason | "");
                    setPage(1);
                  }}
                >
                  <option value="">{copy.allReasons}</option>
                  {(Object.keys(copy.reasons) as CustomerRiskReason[]).map((reason) => (
                    <option key={reason} value={reason}>{copy.reasons[reason]}</option>
                  ))}
                </select>
              </>
            ) : (
              <select
                aria-label={copy.statusFilter}
                value={disputeStatus}
                onChange={(event) => {
                  setDisputeStatus(event.target.value as RiskDisputeStatus | "");
                  setPage(1);
                }}
              >
                <option value="">{copy.all}</option>
                <option value="open">{copy.statuses.open}</option>
                <option value="accepted">{copy.statuses.accepted}</option>
                <option value="rejected">{copy.statuses.rejected}</option>
                <option value="withdrawn">{copy.statuses.withdrawn}</option>
              </select>
            )}

            <button
              type="button"
              className="risk-refresh"
              disabled={loading}
              onClick={() => void loadQueue()}
            >
              <RefreshCw className={loading ? "spin" : ""} size={14} /> {copy.refresh}
            </button>
          </div>

          <p className="risk-moderation-privacy"><AlertTriangle size={14} /> {copy.privacy}</p>
          {error && <div className="risk-moderation-error">{error}</div>}

          <div className="risk-moderation-layout">
            <aside className="risk-moderation-queue">
              <div className="risk-queue-header">
                <div className="risk-queue-count">{total} {copy.pageInfo}</div>
                <div className="risk-pagination" aria-label={`${copy.page} ${page} ${copy.of} ${totalPages}`}>
                  <button
                    type="button"
                    aria-label={copy.previous}
                    title={copy.previous}
                    disabled={loading || page <= 1}
                    onClick={() => setPage((value) => Math.max(1, value - 1))}
                  >
                    <ChevronLeft size={14} />
                  </button>
                  <span>{copy.page} {page} {copy.of} {totalPages}</span>
                  <button
                    type="button"
                    aria-label={copy.next}
                    title={copy.next}
                    disabled={loading || page >= totalPages}
                    onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
                  >
                    <ChevronRight size={14} />
                  </button>
                </div>
              </div>

              {loading ? (
                <div className="risk-moderation-loading"><LoaderCircle className="spin" size={20} /> {copy.loading}</div>
              ) : tab === "reports" ? (
                reports.length === 0 ? <p className="risk-empty">{copy.noItems}</p> : reports.map((item) => (
                  <button
                    type="button"
                    key={item.id}
                    className={reportDetail?.id === item.id ? "risk-queue-item selected" : "risk-queue-item"}
                    onClick={() => void selectReport(item.id)}
                  >
                    <div className="risk-queue-item-top">
                      <span className={`risk-status status-${item.status}`}>{statusLabel(item.status, copy)}</span>
                      <span>{copy.priority} {item.priority_score}</span>
                    </div>
                    <strong>{copy.reasons[item.reason]}</strong>
                    <span>{item.reporter_organization_name ?? `Org #${item.reporter_organization_id}`}</span>
                    <small>
                      {item.open_disputes} {copy.disputesCount} · {formatDate(item.updated_at, locale)}
                    </small>
                  </button>
                ))
              ) : disputes.length === 0 ? (
                <p className="risk-empty">{copy.noItems}</p>
              ) : disputes.map((item) => (
                <button
                  type="button"
                  key={item.id}
                  className={disputeDetail?.id === item.id ? "risk-queue-item selected" : "risk-queue-item"}
                  onClick={() => void selectDispute(item.id)}
                >
                  <div className="risk-queue-item-top">
                    <span className={`risk-status status-${item.status}`}>{statusLabel(item.status, copy)}</span>
                    <span>#{item.id}</span>
                  </div>
                  <strong>{item.requester_organization_name ?? `Org #${item.requester_organization_id}`}</strong>
                  <span className="risk-statement-preview">{item.statement}</span>
                  <small>{formatDate(item.updated_at, locale)}</small>
                </button>
              ))}
            </aside>

            <main className="risk-moderation-detail">
              {detailLoading ? (
                <div className="risk-moderation-loading"><LoaderCircle className="spin" size={20} /> {copy.loading}</div>
              ) : !activeDetail ? (
                <div className="risk-detail-placeholder"><CircleDot size={24} /><p>{copy.selectItem}</p></div>
              ) : reportDetail ? (
                <>
                  <div className="risk-detail-heading">
                    <div>
                      <span className={`risk-status status-${reportDetail.status}`}>{statusLabel(reportDetail.status, copy)}</span>
                      <h3>{copy.report} #{reportDetail.id} · {copy.reasons[reportDetail.reason]}</h3>
                    </div>
                    <span>{formatDate(reportDetail.updated_at, locale)}</span>
                  </div>

                  <div className="risk-detail-grid">
                    <article>
                      <span>{copy.organization}</span>
                      <strong>{reportDetail.reporter.organization_name ?? `#${reportDetail.reporter.organization_id}`}</strong>
                      <small>{copy.reporter}: {reportDetail.reporter.user_label ?? "—"}</small>
                    </article>
                    <article>
                      <span>{copy.reputation}</span>
                      <strong>{reportDetail.reporter.reputation.score}/100 · {reputationLabel}</strong>
                      <small>{reportDetail.reporter.reputation.moderated_reports} {copy.moderatedReports}</small>
                    </article>
                    <article>
                      <span>{copy.customer}</span>
                      <strong>{reportDetail.customer?.name ?? "—"}</strong>
                      <small>
                        {copy.masked}: {reportDetail.customer?.phone_masked ?? "—"} · {reportDetail.customer?.email_masked ?? "—"}
                      </small>
                    </article>
                    <article>
                      <span>{copy.status}</span>
                      <strong>{statusLabel(reportDetail.status, copy)}</strong>
                      <small>{reportDetail.disputes.filter((item) => item.status === "open").length} {copy.disputesCount}</small>
                    </article>
                  </div>

                  <div className="risk-private-evidence">
                    <div><span>{copy.notes}</span><p>{reportDetail.notes || copy.noNotes}</p></div>
                    <div><span>{copy.evidence}</span><p>{reportDetail.evidence_reference || copy.noEvidence}</p></div>
                  </div>

                  <ModerationControls
                    title={copy.moderation}
                    placeholder={copy.moderationNote}
                    note={note}
                    setNote={setNote}
                    saving={saving}
                    savingLabel={copy.saving}
                    buttons={[
                      { label: copy.confirm, icon: <CheckCircle2 size={14} />, onClick: () => void moderateReport("confirm") },
                      { label: copy.dismiss, icon: <ShieldX size={14} />, onClick: () => void moderateReport("dismiss") },
                      { label: copy.markDisputed, icon: <Scale size={14} />, onClick: () => void moderateReport("mark_disputed") },
                      { label: copy.resetPending, icon: <RefreshCw size={14} />, onClick: () => void moderateReport("reset_pending") },
                    ]}
                  />

                  <AuditTimeline copy={copy} locale={locale} events={reportDetail.audit} />
                </>
              ) : disputeDetail ? (
                <>
                  <div className="risk-detail-heading">
                    <div>
                      <span className={`risk-status status-${disputeDetail.status}`}>{statusLabel(disputeDetail.status, copy)}</span>
                      <h3>{copy.appeal} #{disputeDetail.id}</h3>
                    </div>
                    <span>{formatDate(disputeDetail.updated_at, locale)}</span>
                  </div>

                  <div className="risk-detail-grid">
                    <article>
                      <span>{copy.organization}</span>
                      <strong>{disputeDetail.requester_organization_name ?? `#${disputeDetail.requester_organization_id}`}</strong>
                      <small>{disputeDetail.requester_label ?? "—"}</small>
                    </article>
                    <article>
                      <span>{copy.customer}</span>
                      <strong>{disputeDetail.customer?.name ?? "—"}</strong>
                      <small>
                        {copy.masked}: {disputeDetail.customer?.phone_masked ?? "—"} · {disputeDetail.customer?.email_masked ?? "—"}
                      </small>
                    </article>
                  </div>

                  <div className="risk-private-evidence">
                    <div><span>{copy.statement}</span><p>{disputeDetail.statement}</p></div>
                    <div><span>{copy.evidence}</span><p>{disputeDetail.evidence_reference || copy.noEvidence}</p></div>
                    {disputeDetail.resolution_note && (
                      <div><span>{copy.resolution}</span><p>{disputeDetail.resolution_note}</p></div>
                    )}
                  </div>

                  <div className="risk-matching-reports">
                    <span>{copy.matchingReports}</span>
                    {disputeDetail.matching_reports.map((item) => (
                      <div key={item.id}>
                        <strong>#{item.id} · {copy.reasons[item.reason]}</strong>
                        <span>{item.reporter_organization_name ?? `Org #${item.reporter_organization_id}`} · {statusLabel(item.status, copy)}</span>
                      </div>
                    ))}
                  </div>

                  {disputeDetail.status === "open" && (
                    <ModerationControls
                      title={copy.moderation}
                      placeholder={copy.moderationNote}
                      note={note}
                      setNote={setNote}
                      saving={saving}
                      savingLabel={copy.saving}
                      buttons={[
                        { label: copy.acceptDispute, icon: <CheckCircle2 size={14} />, onClick: () => void resolveDispute("accepted") },
                        { label: copy.rejectDispute, icon: <ShieldX size={14} />, onClick: () => void resolveDispute("rejected") },
                      ]}
                    />
                  )}

                  <AuditTimeline copy={copy} locale={locale} events={disputeDetail.audit} />
                </>
              ) : null}
            </main>
          </div>
        </div>
      )}
    </section>
  );
}

interface ModerationButton {
  label: string;
  icon: ReactNode;
  onClick: () => void;
}

function ModerationControls({
  title,
  placeholder,
  note,
  setNote,
  saving,
  savingLabel,
  buttons,
}: {
  title: string;
  placeholder: string;
  note: string;
  setNote: (value: string) => void;
  saving: boolean;
  savingLabel: string;
  buttons: ModerationButton[];
}) {
  return (
    <section className="risk-moderation-actions-panel">
      <strong>{title}</strong>
      <textarea
        value={note}
        maxLength={2000}
        rows={3}
        placeholder={placeholder}
        onChange={(event) => setNote(event.target.value)}
      />
      <div>
        {buttons.map((button) => (
          <button
            type="button"
            key={button.label}
            onClick={button.onClick}
            disabled={saving || note.trim().length < 5}
          >
            {saving ? <LoaderCircle className="spin" size={14} /> : button.icon}
            {saving ? savingLabel : button.label}
          </button>
        ))}
      </div>
    </section>
  );
}

function AuditTimeline({
  copy,
  locale,
  events,
}: {
  copy: ModerationCopy;
  locale: LocaleKey;
  events: Array<{
    id: number;
    action: string;
    actor_role: string;
    actor_label: string | null;
    from_status: string | null;
    to_status: string | null;
    note: string | null;
    created_at: string | null;
  }>;
}) {
  return (
    <section className="risk-audit">
      <strong>{copy.audit}</strong>
      {events.length === 0 ? (
        <p className="risk-empty">{copy.noAudit}</p>
      ) : (
        <div className="risk-audit-timeline">
          {events.map((event) => (
            <article key={event.id}>
              <CircleDot size={13} />
              <div>
                <strong>{auditActionLabel(event.action, copy)}</strong>
                <span>
                  {event.actor_label ?? actorRoleLabel(event.actor_role, copy)} · {formatDate(event.created_at, locale)}
                </span>
                {(event.from_status || event.to_status) && (
                  <small>
                    {event.from_status ? statusLabel(event.from_status, copy) : "—"} → {event.to_status ? statusLabel(event.to_status, copy) : "—"}
                  </small>
                )}
                {event.note && <p>{event.note}</p>}
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
