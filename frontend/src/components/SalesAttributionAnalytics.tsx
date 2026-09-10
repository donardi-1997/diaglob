import type { ReactNode } from "react";
import {
  Bot,
  CircleHelp,
  ShieldCheck,
  Trophy,
  Users,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import type {
  SalesAttributionActorPerformance,
  SalesAttributionAnalytics,
  SalesAttributionMetrics,
} from "../services/analytics";
import "../sales-attribution-analytics.css";

type LocaleKey = "es" | "en" | "pt-BR";

interface Props {
  data: SalesAttributionAnalytics;
  currency: string;
}

const COPY = {
  es: {
    kicker: "SALES ATTRIBUTION",
    title: "Quién cerró las ventas",
    subtitle: "Compara el rendimiento de la IA y del equipo humano, y descubre qué empleado está generando más ventas rentables.",
    coverage: "Cobertura de atribución",
    aiSales: "Ventas atribuidas a IA",
    humanSales: "Ventas atribuidas al equipo",
    unattributed: "Sin atribución",
    deliveredRevenue: "Ingresos entregados",
    grossProfit: "Utilidad bruta",
    delivered: "Entregados",
    deliveryRate: "Tasa de entrega",
    cancellationRate: "Cancelación",
    avgTicket: "Ticket promedio",
    margin: "Margen",
    orders: "Ventas",
    contribution: "Participación ingresos",
    employees: "Rendimiento por empleado",
    aiAgents: "Rendimiento por agente IA",
    employee: "Empleado",
    agent: "Agente IA",
    noEmployees: "Todavía no hay ventas atribuidas a empleados en este período.",
    noAgents: "Todavía no hay ventas atribuidas a agentes IA en este período.",
    noOrders: "No hay pedidos en el período seleccionado.",
    unattributedHelp: "Sin atribución incluye pedidos importados o históricos donde Diaglob no tiene evidencia confiable de quién cerró la venta.",
    partialCosts: "* La utilidad es parcial cuando no todos los ítems entregados tienen costo registrado.",
    teamVsAi: "IA vs. equipo",
  },
  en: {
    kicker: "SALES ATTRIBUTION",
    title: "Who closed the sales",
    subtitle: "Compare AI and human-team performance and identify which employee is generating the most profitable sales.",
    coverage: "Attribution coverage",
    aiSales: "Sales attributed to AI",
    humanSales: "Sales attributed to team",
    unattributed: "Unattributed",
    deliveredRevenue: "Delivered revenue",
    grossProfit: "Gross profit",
    delivered: "Delivered",
    deliveryRate: "Delivery rate",
    cancellationRate: "Cancellation",
    avgTicket: "Average ticket",
    margin: "Margin",
    orders: "Sales",
    contribution: "Revenue share",
    employees: "Employee performance",
    aiAgents: "AI agent performance",
    employee: "Employee",
    agent: "AI agent",
    noEmployees: "No sales are attributed to employees in this period yet.",
    noAgents: "No sales are attributed to AI agents in this period yet.",
    noOrders: "No orders in the selected period.",
    unattributedHelp: "Unattributed includes imported or historical orders where Diaglob has no trustworthy evidence of who closed the sale.",
    partialCosts: "* Profit is partial when not every delivered item has a recorded cost.",
    teamVsAi: "AI vs. team",
  },
  "pt-BR": {
    kicker: "SALES ATTRIBUTION",
    title: "Quem fechou as vendas",
    subtitle: "Compare o desempenho da IA e da equipe humana e descubra qual colaborador gera mais vendas rentáveis.",
    coverage: "Cobertura de atribuição",
    aiSales: "Vendas atribuídas à IA",
    humanSales: "Vendas atribuídas à equipe",
    unattributed: "Sem atribuição",
    deliveredRevenue: "Receita entregue",
    grossProfit: "Lucro bruto",
    delivered: "Entregues",
    deliveryRate: "Taxa de entrega",
    cancellationRate: "Cancelamento",
    avgTicket: "Ticket médio",
    margin: "Margem",
    orders: "Vendas",
    contribution: "Participação receita",
    employees: "Desempenho por colaborador",
    aiAgents: "Desempenho por agente IA",
    employee: "Colaborador",
    agent: "Agente IA",
    noEmployees: "Ainda não há vendas atribuídas a colaboradores neste período.",
    noAgents: "Ainda não há vendas atribuídas a agentes IA neste período.",
    noOrders: "Não há pedidos no período selecionado.",
    unattributedHelp: "Sem atribuição inclui pedidos importados ou históricos em que a Diaglob não possui evidência confiável de quem fechou a venda.",
    partialCosts: "* O lucro é parcial quando nem todos os itens entregues têm custo registrado.",
    teamVsAi: "IA vs. equipe",
  },
} as const;

function resolveLocale(language: string): LocaleKey {
  if (language.toLowerCase().startsWith("pt")) return "pt-BR";
  if (language.toLowerCase().startsWith("en")) return "en";
  return "es";
}

export default function SalesAttributionAnalytics({ data, currency }: Props) {
  const { i18n } = useTranslation();
  const copy = COPY[resolveLocale(i18n.language)];

  const money = (value: number | null) => {
    if (value === null || value === undefined) return "—";
    try {
      return new Intl.NumberFormat(resolveLocale(i18n.language), {
        style: "currency",
        currency,
        maximumFractionDigits: 0,
      }).format(value);
    } catch {
      return `${Math.round(value).toLocaleString()} ${currency}`;
    }
  };

  const rate = (value: number | null) =>
    value === null || value === undefined ? "—" : `${value}%`;

  if (data.total_orders === 0) {
    return (
      <section className="sales-attribution-shell">
        <div className="sales-attribution-heading">
          <div>
            <span className="sales-attribution-kicker">{copy.kicker}</span>
            <h3>{copy.title}</h3>
            <p>{copy.subtitle}</p>
          </div>
        </div>
        <div className="sales-attribution-empty">{copy.noOrders}</div>
      </section>
    );
  }

  const human = data.by_actor_type.human;
  const ai = data.by_actor_type.ai;
  const unattributed = data.by_actor_type.unattributed;
  const hasPartialCosts = [human, ai, unattributed].some(
    (metrics) => metrics.delivered_orders > 0 && !metrics.profitability_complete,
  );

  return (
    <section className="sales-attribution-shell">
      <div className="sales-attribution-heading">
        <div>
          <span className="sales-attribution-kicker">{copy.kicker}</span>
          <h3>{copy.title}</h3>
          <p>{copy.subtitle}</p>
        </div>
        <div className="sales-attribution-coverage">
          <ShieldCheck size={18} />
          <div>
            <strong>{rate(data.attribution_rate_pct)}</strong>
            <span>{copy.coverage}</span>
          </div>
        </div>
      </div>

      <div className="sales-attribution-type-grid">
        <AttributionCard
          icon={<Bot size={19} />}
          label={copy.aiSales}
          metrics={ai}
          money={money}
          deliveredLabel={copy.deliveredRevenue}
        />
        <AttributionCard
          icon={<Users size={19} />}
          label={copy.humanSales}
          metrics={human}
          money={money}
          deliveredLabel={copy.deliveredRevenue}
        />
        <AttributionCard
          icon={<CircleHelp size={19} />}
          label={copy.unattributed}
          metrics={unattributed}
          money={money}
          deliveredLabel={copy.deliveredRevenue}
          muted
        />
      </div>

      <div className="sales-attribution-note">
        <CircleHelp size={16} />
        <span>{copy.unattributedHelp}</span>
      </div>

      <div className="sales-attribution-panel">
        <div className="sales-attribution-panel-title">
          <Trophy size={18} />
          <h4>{copy.teamVsAi}</h4>
        </div>
        <div className="sales-attribution-comparison-wrap">
          <table className="sales-attribution-comparison">
            <thead>
              <tr>
                <th />
                <th><Users size={15} /> {copy.humanSales}</th>
                <th><Bot size={15} /> {copy.aiSales}</th>
              </tr>
            </thead>
            <tbody>
              <CompareRow label={copy.orders} human={human.total_orders} ai={ai.total_orders} />
              <CompareRow label={copy.delivered} human={human.delivered_orders} ai={ai.delivered_orders} />
              <CompareRow label={copy.deliveredRevenue} human={money(human.delivered_revenue)} ai={money(ai.delivered_revenue)} />
              <CompareRow label={copy.grossProfit} human={money(human.gross_profit)} ai={money(ai.gross_profit)} />
              <CompareRow label={copy.margin} human={rate(human.gross_margin)} ai={rate(ai.gross_margin)} />
              <CompareRow label={copy.avgTicket} human={money(human.delivered_aov)} ai={money(ai.delivered_aov)} />
              <CompareRow label={copy.deliveryRate} human={rate(human.delivery_rate)} ai={rate(ai.delivery_rate)} />
              <CompareRow label={copy.cancellationRate} human={rate(human.cancellation_rate)} ai={rate(ai.cancellation_rate)} />
            </tbody>
          </table>
        </div>
      </div>

      <ActorTable
        title={copy.employees}
        actorLabel={copy.employee}
        rows={data.employees}
        icon={<Users size={18} />}
        copy={copy}
        money={money}
        rate={rate}
      />

      {data.ai_agents.length > 0 && (
        <ActorTable
          title={copy.aiAgents}
          actorLabel={copy.agent}
          rows={data.ai_agents}
          icon={<Bot size={18} />}
          copy={copy}
          money={money}
          rate={rate}
        />
      )}

      {data.employees.length === 0 && (
        <div className="sales-attribution-empty compact">{copy.noEmployees}</div>
      )}
      {data.ai_agents.length === 0 && ai.total_orders > 0 && (
        <div className="sales-attribution-empty compact">{copy.noAgents}</div>
      )}

      {hasPartialCosts && (
        <div className="sales-attribution-footnote">{copy.partialCosts}</div>
      )}
    </section>
  );
}

function AttributionCard({
  icon,
  label,
  metrics,
  money,
  deliveredLabel,
  muted = false,
}: {
  icon: ReactNode;
  label: string;
  metrics: SalesAttributionMetrics;
  money: (value: number | null) => string;
  deliveredLabel: string;
  muted?: boolean;
}) {
  return (
    <article className={`sales-attribution-card${muted ? " muted" : ""}`}>
      <div className="sales-attribution-card-label">{icon}<span>{label}</span></div>
      <strong className="sales-attribution-card-value">{metrics.total_orders}</strong>
      <div className="sales-attribution-card-meta">
        <span>{deliveredLabel}</span>
        <b>{money(metrics.delivered_revenue)}</b>
      </div>
    </article>
  );
}

function CompareRow({
  label,
  human,
  ai,
}: {
  label: string;
  human: ReactNode;
  ai: ReactNode;
}) {
  return (
    <tr>
      <td>{label}</td>
      <td>{human}</td>
      <td>{ai}</td>
    </tr>
  );
}

function ActorTable({
  title,
  actorLabel,
  rows,
  icon,
  copy,
  money,
  rate,
}: {
  title: string;
  actorLabel: string;
  rows: SalesAttributionActorPerformance[];
  icon: ReactNode;
  copy: (typeof COPY)[LocaleKey];
  money: (value: number | null) => string;
  rate: (value: number | null) => string;
}) {
  if (rows.length === 0) return null;

  return (
    <div className="sales-attribution-panel">
      <div className="sales-attribution-panel-title">
        {icon}
        <h4>{title}</h4>
      </div>
      <div className="sales-attribution-table-wrap">
        <table className="sales-attribution-table">
          <thead>
            <tr>
              <th>{actorLabel}</th>
              <th>{copy.orders}</th>
              <th>{copy.delivered}</th>
              <th>{copy.deliveredRevenue}</th>
              <th>{copy.grossProfit}</th>
              <th>{copy.avgTicket}</th>
              <th>{copy.deliveryRate}</th>
              <th>{copy.cancellationRate}</th>
              <th>{copy.contribution}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`${row.actor_id ?? row.actor_label}-${index}`}>
                <td>
                  <div className="sales-attribution-actor">
                    <span className="sales-attribution-rank">#{index + 1}</span>
                    <strong>{row.actor_label}</strong>
                  </div>
                </td>
                <td>{row.total_orders}</td>
                <td>{row.delivered_orders}</td>
                <td>{money(row.delivered_revenue)}</td>
                <td>
                  {money(row.gross_profit)}
                  {!row.profitability_complete && row.delivered_orders > 0 ? " *" : ""}
                </td>
                <td>{money(row.delivered_aov)}</td>
                <td>{rate(row.delivery_rate)}</td>
                <td>{rate(row.cancellation_rate)}</td>
                <td>{rate(row.revenue_share_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
