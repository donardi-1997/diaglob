import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  BadgeDollarSign,
  BarChart3,
  CircleDollarSign,
  LoaderCircle,
  Megaphone,
  MousePointerClick,
  RefreshCw,
  Rocket,
  Target,
  Users,
  type LucideIcon,
} from "lucide-react";

import {
  getAdminGrowth,
  type AdminGrowth,
} from "../services/adminAnalytics";
import "../growth-center.css";

type GrowthWindow = 7 | 30 | 90;

const RANGE_OPTIONS: GrowthWindow[] = [7, 30, 90];

function FunnelStep({
  label,
  value,
  max,
  helper,
}: {
  label: string;
  value: number;
  max: number;
  helper?: string;
}) {
  const width = max > 0 ? Math.max(8, (value / max) * 100) : 8;

  return (
    <div className="growth-funnel-step">
      <div className="growth-funnel-copy">
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
      <div className="growth-funnel-track">
        <span style={{ width: `${width}%` }} />
      </div>
      {helper && <small>{helper}</small>}
    </div>
  );
}

function EmptyMetric({
  icon: Icon,
  label,
  helper,
}: {
  icon: LucideIcon;
  label: string;
  helper: string;
}) {
  return (
    <article className="growth-stat-card growth-stat-card-muted">
      <div className="growth-stat-icon"><Icon size={18} /></div>
      <strong>—</strong>
      <span>{label}</span>
      <small>{helper}</small>
    </article>
  );
}

export default function GrowthPage() {
  const [days, setDays] = useState<GrowthWindow>(30);
  const [data, setData] = useState<AdminGrowth | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async (nextDays: GrowthWindow, initial = false) => {
    if (initial) setLoading(true);
    else setRefreshing(true);

    try {
      const response = await getAdminGrowth(nextDays);
      setData(response);
      setError("");
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ||
          "No fue posible cargar el centro de adquisición.",
      );
    } finally {
      if (initial) setLoading(false);
      else setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load(days, true);
  }, [days, load]);

  const funnelMax = Math.max(1, data?.acquisition.tracked_registrations || 0);

  const metaStatuses = useMemo(
    () =>
      Object.entries(data?.acquisition.meta_delivery_statuses || {})
        .sort(([, a], [, b]) => b - a),
    [data],
  );

  if (loading) {
    return (
      <div className="growth-loading">
        <LoaderCircle className="spin" size={24} />
        Cargando adquisición...
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="growth-error">
        <strong>No pudimos cargar Growth.</strong>
        <span>{error || "Sin datos disponibles."}</span>
        <button type="button" onClick={() => void load(days, true)}>
          Reintentar
        </button>
      </div>
    );
  }

  const acquisition = data.acquisition;

  return (
    <div className="growth-center">
      <section className="growth-hero">
        <div>
          <span className="growth-kicker"><Megaphone size={14} /> GROWTH · PLATFORM ADMIN</span>
          <h1>Adquisición de Diaglob</h1>
          <p>
            Sigue el recorrido desde la campaña hasta la suscripción paga.
            Los datos de conversión vienen de Diaglob; gasto y performance de
            medios aparecerán cuando conectemos la cuenta corporativa de Meta.
          </p>
        </div>

        <div className="growth-actions">
          <div className="growth-range" aria-label="Ventana de análisis">
            {RANGE_OPTIONS.map((option) => (
              <button
                key={option}
                type="button"
                className={days === option ? "is-active" : ""}
                onClick={() => setDays(option)}
              >
                {option}d
              </button>
            ))}
          </div>
          <button
            type="button"
            className="growth-refresh"
            onClick={() => void load(days)}
            disabled={refreshing}
          >
            <RefreshCw size={16} className={refreshing ? "spin" : ""} />
            Actualizar
          </button>
        </div>
      </section>

      <section className="growth-stat-grid">
        <article className="growth-stat-card">
          <div className="growth-stat-icon"><Users size={18} /></div>
          <strong>{acquisition.tracked_registrations}</strong>
          <span>Registros atribuidos</span>
          <small>CompleteRegistration</small>
        </article>
        <article className="growth-stat-card">
          <div className="growth-stat-icon"><Rocket size={18} /></div>
          <strong>{acquisition.start_trials}</strong>
          <span>Trials activados</span>
          <small>{acquisition.registration_to_trial_pct.toFixed(1)}% desde registro</small>
        </article>
        <article className="growth-stat-card">
          <div className="growth-stat-icon"><BadgeDollarSign size={18} /></div>
          <strong>{acquisition.paid_subscriptions}</strong>
          <span>Suscripciones pagas</span>
          <small>{acquisition.registration_to_paid_pct.toFixed(1)}% desde registro</small>
        </article>
        <EmptyMetric
          icon={CircleDollarSign}
          label="Gasto"
          helper="Conectar Meta Ads"
        />
        <EmptyMetric
          icon={MousePointerClick}
          label="CPC / CTR"
          helper="Conectar Meta Ads"
        />
        <EmptyMetric
          icon={Target}
          label="CAC"
          helper="Se calculará con spend + pagos"
        />
      </section>

      <section className="growth-grid growth-grid-main">
        <article className="growth-panel">
          <header className="growth-panel-header">
            <div>
              <span>FUNNEL</span>
              <h2>De registro a cliente pago</h2>
            </div>
            <small>{data.window_days} días</small>
          </header>

          <div className="growth-funnel">
            <FunnelStep
              label="Registros"
              value={acquisition.tracked_registrations}
              max={funnelMax}
              helper="Usuarios con attribution capturada"
            />
            <div className="growth-funnel-arrow"><ArrowRight size={17} /></div>
            <FunnelStep
              label="Trials"
              value={acquisition.start_trials}
              max={funnelMax}
              helper={`${acquisition.registration_to_trial_pct.toFixed(1)}% de registros`}
            />
            <div className="growth-funnel-arrow"><ArrowRight size={17} /></div>
            <FunnelStep
              label="Pagos"
              value={acquisition.paid_subscriptions}
              max={funnelMax}
              helper={`${acquisition.registration_to_paid_pct.toFixed(1)}% de registros`}
            />
          </div>
        </article>

        <article className="growth-panel">
          <header className="growth-panel-header">
            <div>
              <span>MEDIA</span>
              <h2>Meta Ads</h2>
            </div>
            <span className="growth-connection-badge is-pending">Pendiente</span>
          </header>

          <div className="growth-media-empty">
            <Megaphone size={30} />
            <strong>Falta conectar el Ad Account corporativo</strong>
            <p>
              Diaglob ya mide conversiones propias. Cuando conectemos Meta
              añadiremos spend, impresiones, clicks, CPM, CPC y CTR para
              calcular CAC por campaña y creativo.
            </p>
          </div>
        </article>
      </section>

      <section className="growth-panel">
        <header className="growth-panel-header">
          <div>
            <span>CAMPAIGNS</span>
            <h2>Rendimiento por campaña</h2>
          </div>
          <small>Ordenado por pagos, trials y registros</small>
        </header>

        {acquisition.campaign_performance.length === 0 ? (
          <div className="growth-empty">Todavía no hay campañas atribuidas en esta ventana.</div>
        ) : (
          <div className="growth-table-wrap">
            <table className="growth-table">
              <thead>
                <tr>
                  <th>Campaña</th>
                  <th>Registros</th>
                  <th>Trials</th>
                  <th>Pagos</th>
                  <th>Reg → Trial</th>
                  <th>Reg → Pago</th>
                  <th>Spend</th>
                  <th>CAC</th>
                </tr>
              </thead>
              <tbody>
                {acquisition.campaign_performance.map((item) => (
                  <tr key={item.campaign}>
                    <td><strong>{item.campaign}</strong></td>
                    <td>{item.registrations}</td>
                    <td>{item.trials}</td>
                    <td>{item.paid_subscriptions}</td>
                    <td>{item.registration_to_trial_pct.toFixed(1)}%</td>
                    <td>{item.registration_to_paid_pct.toFixed(1)}%</td>
                    <td className="growth-muted-cell">—</td>
                    <td className="growth-muted-cell">—</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="growth-grid">
        <article className="growth-panel">
          <header className="growth-panel-header">
            <div>
              <span>CREATIVES</span>
              <h2>Rendimiento por creativo</h2>
            </div>
          </header>

          {acquisition.creative_performance.length === 0 ? (
            <div className="growth-empty">Aún no hay creativos atribuidos.</div>
          ) : (
            <div className="growth-creative-list">
              {acquisition.creative_performance.slice(0, 12).map((item) => (
                <div className="growth-creative-row" key={`${item.campaign}:${item.content}`}>
                  <div>
                    <strong>{item.content}</strong>
                    <span>{item.campaign}</span>
                  </div>
                  <div className="growth-creative-metrics">
                    <span><b>{item.registrations}</b> reg</span>
                    <span><b>{item.trials}</b> trials</span>
                    <span><b>{item.paid_subscriptions}</b> pagos</span>
                    <span><b>{item.registration_to_paid_pct.toFixed(1)}%</b> reg→pago</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </article>

        <article className="growth-panel">
          <header className="growth-panel-header">
            <div>
              <span>ATTRIBUTION</span>
              <h2>Fuentes y entrega CAPI</h2>
            </div>
          </header>

          <div className="growth-metric-list">
            {acquisition.by_source.map((source) => (
              <div className="growth-metric-row" key={source.source}>
                <span>Fuente · {source.source}</span>
                <strong>{source.registrations}</strong>
              </div>
            ))}
            {metaStatuses.map(([status, count]) => (
              <div className="growth-metric-row" key={status}>
                <span>CAPI · {status}</span>
                <strong>{count}</strong>
              </div>
            ))}
            {acquisition.by_source.length === 0 && metaStatuses.length === 0 && (
              <div className="growth-empty">Todavía no hay eventos atribuidos.</div>
            )}
          </div>
        </article>
      </section>

      <section className="growth-panel growth-next-step">
        <div className="growth-next-icon"><BarChart3 size={22} /></div>
        <div>
          <span>SIGUIENTE CONEXIÓN</span>
          <h2>Unir datos de Meta con conversiones propias</h2>
          <p>
            El modelo ya está preparado para completar Spend → Click → Registro
            → Trial → Pago y calcular CAC real por campaña y creativo.
          </p>
        </div>
      </section>
    </div>
  );
}
