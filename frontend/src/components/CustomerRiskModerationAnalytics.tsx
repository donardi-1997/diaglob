import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Building2,
  Clock3,
  LoaderCircle,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  getAdminRiskAnalytics,
  type AdminRiskModerationAnalytics,
} from "../services/adminRisk";
import type { CustomerRiskReason } from "../services/customerRisk";
import "../customer-risk-moderation-analytics.css";


type LocaleKey = "es" | "en" | "pt-BR";

const COPY = {
  es: {
    title: "Analítica de moderación",
    subtitle: "Carga operativa, resultados y tiempos de respuesta de la red de señales compartidas.",
    days: "días",
    reportsCreated: "Reportes creados",
    moderatedReports: "Reportes moderados",
    disputesCreated: "Apelaciones creadas",
    reportResponse: "Tiempo medio de reporte",
    disputeResponse: "Tiempo medio de apelación",
    confirmationRate: "Tasa de confirmación",
    appealAcceptance: "Apelaciones aceptadas",
    backlog: "Carga pendiente actual",
    pendingReports: "Reportes pendientes",
    disputedReports: "Reportes en disputa",
    openDisputes: "Apelaciones abiertas",
    older24h: "con más de 24 h",
    trend: "Actividad diaria",
    reports: "Reportes",
    moderated: "Moderados",
    disputes: "Apelaciones",
    resolved: "Resueltas",
    outcomes: "Resultados de moderación",
    confirmed: "Confirmados",
    dismissed: "Descartados",
    disputed: "En disputa",
    resetPending: "Restablecidos",
    accepted: "Aceptadas",
    rejected: "Rechazadas",
    reasons: "Motivos reportados",
    organizations: "Organizaciones reportantes",
    organization: "Organización",
    volume: "Volumen",
    evidence: "Con evidencia",
    dismissalRate: "Tasa de descarte",
    statusMix: "Estado actual",
    governance: "Estas métricas sirven para priorizar revisión humana. No deben bloquear automáticamente clientes, pedidos ni organizaciones.",
    loading: "Cargando analítica...",
    failed: "No se pudo cargar la analítica de moderación.",
    refresh: "Actualizar",
    noData: "Todavía no hay datos suficientes para este período.",
    hours: "h",
    minutes: "min",
    reasonsMap: {
      suspected_fraud: "Posible fraude",
      payment_abuse: "Pago o contracargo",
      delivery_claim: "Reclamo de entrega",
      identity_mismatch: "Identidad inconsistente",
      abusive_behavior: "Comportamiento abusivo",
      other: "Otro",
    },
  },
  en: {
    title: "Moderation analytics",
    subtitle: "Operational workload, outcomes, and response times for the shared-signal network.",
    days: "days",
    reportsCreated: "Reports created",
    moderatedReports: "Reports moderated",
    disputesCreated: "Appeals created",
    reportResponse: "Average report response",
    disputeResponse: "Average appeal response",
    confirmationRate: "Confirmation rate",
    appealAcceptance: "Appeal acceptance",
    backlog: "Current backlog",
    pendingReports: "Pending reports",
    disputedReports: "Disputed reports",
    openDisputes: "Open appeals",
    older24h: "older than 24 h",
    trend: "Daily activity",
    reports: "Reports",
    moderated: "Moderated",
    disputes: "Appeals",
    resolved: "Resolved",
    outcomes: "Moderation outcomes",
    confirmed: "Confirmed",
    dismissed: "Dismissed",
    disputed: "Disputed",
    resetPending: "Reset pending",
    accepted: "Accepted",
    rejected: "Rejected",
    reasons: "Reported reasons",
    organizations: "Reporting organizations",
    organization: "Organization",
    volume: "Volume",
    evidence: "With evidence",
    dismissalRate: "Dismissal rate",
    statusMix: "Current status",
    governance: "These metrics are for human review prioritization. They must not automatically block customers, orders, or organizations.",
    loading: "Loading analytics...",
    failed: "Moderation analytics could not be loaded.",
    refresh: "Refresh",
    noData: "There is not enough data for this period yet.",
    hours: "h",
    minutes: "min",
    reasonsMap: {
      suspected_fraud: "Suspected fraud",
      payment_abuse: "Payment or chargeback",
      delivery_claim: "Delivery claim",
      identity_mismatch: "Identity mismatch",
      abusive_behavior: "Abusive behavior",
      other: "Other",
    },
  },
  "pt-BR": {
    title: "Analítica de moderação",
    subtitle: "Carga operacional, resultados e tempos de resposta da rede de sinais compartilhados.",
    days: "dias",
    reportsCreated: "Relatos criados",
    moderatedReports: "Relatos moderados",
    disputesCreated: "Contestações criadas",
    reportResponse: "Tempo médio do relato",
    disputeResponse: "Tempo médio da contestação",
    confirmationRate: "Taxa de confirmação",
    appealAcceptance: "Contestações aceitas",
    backlog: "Carga pendente atual",
    pendingReports: "Relatos pendentes",
    disputedReports: "Relatos em disputa",
    openDisputes: "Contestações abertas",
    older24h: "com mais de 24 h",
    trend: "Atividade diária",
    reports: "Relatos",
    moderated: "Moderados",
    disputes: "Contestações",
    resolved: "Resolvidas",
    outcomes: "Resultados da moderação",
    confirmed: "Confirmados",
    dismissed: "Descartados",
    disputed: "Em disputa",
    resetPending: "Redefinidos",
    accepted: "Aceitas",
    rejected: "Rejeitadas",
    reasons: "Motivos reportados",
    organizations: "Organizações reportantes",
    organization: "Organização",
    volume: "Volume",
    evidence: "Com evidência",
    dismissalRate: "Taxa de descarte",
    statusMix: "Estado atual",
    governance: "Estas métricas servem para priorizar revisão humana. Não devem bloquear automaticamente clientes, pedidos ou organizações.",
    loading: "Carregando analítica...",
    failed: "Não foi possível carregar a analítica de moderação.",
    refresh: "Atualizar",
    noData: "Ainda não há dados suficientes para este período.",
    hours: "h",
    minutes: "min",
    reasonsMap: {
      suspected_fraud: "Possível fraude",
      payment_abuse: "Pagamento ou chargeback",
      delivery_claim: "Reclamação de entrega",
      identity_mismatch: "Identidade inconsistente",
      abusive_behavior: "Comportamento abusivo",
      other: "Outro",
    },
  },
} as const;

function localeFor(language: string): LocaleKey {
  if (language.toLowerCase().startsWith("pt")) return "pt-BR";
  if (language.toLowerCase().startsWith("en")) return "en";
  return "es";
}

function formatHours(value: number | null, copy: (typeof COPY)[LocaleKey]): string {
  if (value === null) return "—";
  if (value < 1) return `${Math.round(value * 60)} ${copy.minutes}`;
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${copy.hours}`;
}

export default function CustomerRiskModerationAnalytics() {
  const { i18n } = useTranslation();
  const locale = localeFor(i18n.language);
  const copy = COPY[locale];
  const [days, setDays] = useState(30);
  const [data, setData] = useState<AdminRiskModerationAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const next = await getAdminRiskAnalytics(days);
        if (!cancelled) setData(next);
      } catch {
        if (!cancelled) setError(copy.failed);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [copy.failed, days, refreshKey]);

  const recentDaily = useMemo(() => data?.daily.slice(-14) ?? [], [data]);
  const maxDaily = useMemo(() => {
    const values = recentDaily.map((row) => Math.max(
      row.reports_created,
      row.reports_moderated,
      row.disputes_created,
      row.disputes_resolved,
    ));
    return Math.max(1, ...values);
  }, [recentDaily]);

  if (loading && !data) {
    return (
      <div className="risk-analytics-loading">
        <LoaderCircle className="spin" size={20} /> {copy.loading}
      </div>
    );
  }

  return (
    <section className="risk-analytics">
      <div className="risk-analytics-heading">
        <div>
          <span className="risk-analytics-eyebrow"><BarChart3 size={14} /> {copy.title}</span>
          <p>{copy.subtitle}</p>
        </div>
        <div className="risk-analytics-controls">
          <div className="risk-window-switch" aria-label={copy.days}>
            {[7, 30, 90].map((value) => (
              <button
                type="button"
                key={value}
                className={days === value ? "active" : ""}
                onClick={() => setDays(value)}
              >
                {value} {copy.days}
              </button>
            ))}
          </div>
          <button
            type="button"
            className="risk-analytics-refresh"
            disabled={loading}
            onClick={() => setRefreshKey((value) => value + 1)}
          >
            <RefreshCw className={loading ? "spin" : ""} size={14} /> {copy.refresh}
          </button>
        </div>
      </div>

      {error && <div className="risk-moderation-error">{error}</div>}
      {!data ? <p className="risk-empty">{copy.noData}</p> : (
        <>
          <div className="risk-analytics-kpis">
            <MetricCard icon={<Activity size={16} />} label={copy.reportsCreated} value={data.summary.reports_created} />
            <MetricCard icon={<ShieldAlert size={16} />} label={copy.moderatedReports} value={data.summary.moderated_reports} />
            <MetricCard icon={<Clock3 size={16} />} label={copy.reportResponse} value={formatHours(data.summary.average_report_resolution_hours, copy)} />
            <MetricCard icon={<Clock3 size={16} />} label={copy.disputeResponse} value={formatHours(data.summary.average_dispute_resolution_hours, copy)} />
            <MetricCard icon={<BarChart3 size={16} />} label={copy.confirmationRate} value={`${data.summary.confirmation_rate}%`} />
            <MetricCard icon={<BarChart3 size={16} />} label={copy.appealAcceptance} value={`${data.summary.appeal_acceptance_rate}%`} />
          </div>

          <section className="risk-analytics-section">
            <div className="risk-analytics-section-title"><AlertTriangle size={15} /><strong>{copy.backlog}</strong></div>
            <div className="risk-backlog-grid">
              <BacklogCard
                label={copy.pendingReports}
                value={data.backlog.pending_reports}
                stale={data.backlog.pending_reports_over_24h}
                staleLabel={copy.older24h}
              />
              <BacklogCard label={copy.disputedReports} value={data.backlog.disputed_reports} />
              <BacklogCard
                label={copy.openDisputes}
                value={data.backlog.open_disputes}
                stale={data.backlog.open_disputes_over_24h}
                staleLabel={copy.older24h}
              />
            </div>
          </section>

          <div className="risk-analytics-two-column">
            <section className="risk-analytics-section">
              <div className="risk-analytics-section-title"><Activity size={15} /><strong>{copy.trend}</strong></div>
              {recentDaily.length === 0 ? <p className="risk-empty">{copy.noData}</p> : (
                <div className="risk-daily-chart">
                  <div className="risk-chart-legend">
                    <span><i className="reports" />{copy.reports}</span>
                    <span><i className="moderated" />{copy.moderated}</span>
                    <span><i className="disputes" />{copy.disputes}</span>
                    <span><i className="resolved" />{copy.resolved}</span>
                  </div>
                  <div className="risk-chart-bars">
                    {recentDaily.map((row) => (
                      <div className="risk-chart-day" key={row.date} title={new Date(`${row.date}T00:00:00`).toLocaleDateString(locale)}>
                        <div className="risk-chart-cluster">
                          <span className="reports" style={{ height: `${Math.max(3, (row.reports_created / maxDaily) * 100)}%` }} />
                          <span className="moderated" style={{ height: `${Math.max(3, (row.reports_moderated / maxDaily) * 100)}%` }} />
                          <span className="disputes" style={{ height: `${Math.max(3, (row.disputes_created / maxDaily) * 100)}%` }} />
                          <span className="resolved" style={{ height: `${Math.max(3, (row.disputes_resolved / maxDaily) * 100)}%` }} />
                        </div>
                        <small>{row.date.slice(8)}</small>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </section>

            <section className="risk-analytics-section">
              <div className="risk-analytics-section-title"><BarChart3 size={15} /><strong>{copy.outcomes}</strong></div>
              <div className="risk-outcome-grid">
                <Outcome label={copy.confirmed} value={data.outcomes.reports.confirmed} />
                <Outcome label={copy.dismissed} value={data.outcomes.reports.dismissed} />
                <Outcome label={copy.disputed} value={data.outcomes.reports.disputed} />
                <Outcome label={copy.resetPending} value={data.outcomes.reports.reset_pending} />
                <Outcome label={copy.accepted} value={data.outcomes.disputes.accepted} />
                <Outcome label={copy.rejected} value={data.outcomes.disputes.rejected} />
              </div>
            </section>
          </div>

          <div className="risk-analytics-two-column">
            <section className="risk-analytics-section">
              <div className="risk-analytics-section-title"><ShieldAlert size={15} /><strong>{copy.reasons}</strong></div>
              {data.reason_breakdown.length === 0 ? <p className="risk-empty">{copy.noData}</p> : (
                <div className="risk-reason-list">
                  {data.reason_breakdown.map((item) => (
                    <div key={item.reason}>
                      <div><span>{copy.reasonsMap[item.reason as CustomerRiskReason]}</span><strong>{item.count} · {item.percentage}%</strong></div>
                      <div className="risk-reason-track"><span style={{ width: `${item.percentage}%` }} /></div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className="risk-analytics-section risk-org-section">
              <div className="risk-analytics-section-title"><Building2 size={15} /><strong>{copy.organizations}</strong></div>
              {data.reporting_organizations.length === 0 ? <p className="risk-empty">{copy.noData}</p> : (
                <div className="risk-org-table-wrap">
                  <table className="risk-org-table">
                    <thead>
                      <tr>
                        <th>{copy.organization}</th>
                        <th>{copy.volume}</th>
                        <th>{copy.evidence}</th>
                        <th>{copy.dismissalRate}</th>
                        <th>{copy.statusMix}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.reporting_organizations.map((item) => (
                        <tr key={item.organization_id}>
                          <td>{item.organization_name ?? `Org #${item.organization_id}`}</td>
                          <td>{item.report_count}</td>
                          <td>{item.evidence_rate}%</td>
                          <td>{item.dismissal_rate}%</td>
                          <td>{item.confirmed}/{item.dismissed}/{item.disputed}/{item.pending}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </div>

          <p className="risk-analytics-governance"><AlertTriangle size={14} /> {copy.governance}</p>
        </>
      )}
    </section>
  );
}

function MetricCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string | number }) {
  return (
    <article className="risk-metric-card">
      <div>{icon}<span>{label}</span></div>
      <strong>{value}</strong>
    </article>
  );
}

function BacklogCard({
  label,
  value,
  stale,
  staleLabel,
}: {
  label: string;
  value: number;
  stale?: number;
  staleLabel?: string;
}) {
  return (
    <article className="risk-backlog-card">
      <span>{label}</span>
      <strong>{value}</strong>
      {stale !== undefined && <small>{stale} {staleLabel}</small>}
    </article>
  );
}

function Outcome({ label, value }: { label: string; value: number }) {
  return (
    <div className="risk-outcome-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
