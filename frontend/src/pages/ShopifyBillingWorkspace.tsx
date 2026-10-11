import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle, ArrowRight, CheckCircle2, Clock3, RefreshCw, ShieldCheck,
} from "lucide-react";

import type { Organization } from "../services/organizations";
import {
  assessShopifyPlanReview,
  applyVerifiedShopifyPlan,
  checkShopifyBilling,
  getShopifyBillingCapabilities,
  getShopifyHostedPlanSelection,
  refreshShopifySubscription,
  getShopifyBillingHistory,
  getShopifyPlanReviews,
  stageShopifyPlanReview,
  verifyShopifyTrial,
  type ShopifyBillingCapabilities,
  type ShopifyBillingCheck,
  type ShopifyBillingVerification,
  type ShopifyPlanReview,
  type ShopifyReviewAssessment,
  type ShopifyTrialVerification,
} from "../services/shopifyBilling";

interface Props {
  organization: Organization;
}

const explanations: Record<string, string> = {
  REVIEW_NOT_PENDING: "La propuesta ya no está pendiente.",
  REVIEW_EXPIRED: "La propuesta superó el tiempo de vigencia.",
  VERIFICATION_MISSING: "No se encontró la verificación original.",
  NEWER_VERIFICATION_EXISTS: "Existe una verificación de Shopify más reciente.",
  VERIFICATION_EXPIRED: "La verificación de Shopify ya caducó.",
  VERIFICATION_MISMATCH: "Los datos del plan ya no coinciden.",
  ORGANIZATION_INACTIVE: "La organización está inactiva.",
  BILLING_CHANNEL_CHANGED: "Cambió el proveedor de facturación.",
  BASELINE_PLAN_CHANGED: "Cambió el plan actual.",
  LEGACY_BILLING_REFERENCES: "Hay una suscripción anterior que requiere revisión.",
  SHOPIFY_BINDINGS_CHANGED: "Cambió la cantidad de tiendas vinculadas.",
  SHOPIFY_INSTALLATION_CHANGED: "La conexión de Shopify fue reemplazada o desconectada.",
  STORE_UNAVAILABLE: "La tienda está pausada o eliminada.",
};

const statusLabels: Record<string, string> = {
  plan_verified_no_change: "Plan verificado sin cambios",
  plan_transition_requires_review: "Cambio de plan para revisión",
  subscription_inactive_requires_review: "Suscripción inactiva: revisión necesaria",
  pending_review: "Pendiente de revisión",
  applied: "Plan aplicado y verificado",
  stale: "Caducada",
  blocked: "Bloqueada",
  ready_for_manual_review: "Lista para revisión manual",
};

const knownErrorCodes: Record<string, string> = {
  SHOPIFY_BILLING_PROVENANCE_REQUIRED: "La organización no está configurada para facturación Shopify.",
  SHOPIFY_MULTISTORE_BILLING_REVIEW_REQUIRED: "Hay varias vinculaciones Shopify; se necesita revisión de facturación.",
  SHOPIFY_BILLING_CONNECTION_REVIEW_REQUIRED: "La conexión Shopify necesita revisión.",
  SHOPIFY_BILLING_STATE_CHANGED: "Cambió el estado de la conexión durante la verificación.",
  SHOPIFY_PLAN_PRICE_UNVERIFIED: "Shopify no confirmó un precio verificable.",
  SHOPIFY_PLAN_PRICE_MISMATCH: "El precio Shopify no coincide con el precio aprobado.",
  SHOPIFY_PLAN_CATALOG_INVALID: "El catálogo de precios aprobados requiere configuración.",
  SHOPIFY_TRANSITION_STALE_VERIFICATION: "La verificación caducó o ya no es la más reciente.",
  SHOPIFY_TRANSITION_REVIEW_ALREADY_PENDING: "Ya hay otra revisión de plan pendiente.",
  SHOPIFY_TRANSITION_INSTALLATION_OR_PLAN_CHANGED: "La instalación o el plan cambiaron.",
  SHOPIFY_TRANSITION_CONCURRENT_REVIEW: "Se está procesando otra propuesta. Actualiza el historial.",
  SHOPIFY_ENTITLEMENT_ACTIVATION_DISABLED: "La aplicación de planes todavía no está autorizada en Diaglob.",
  SHOPIFY_TRANSITION_PROVIDER_MISMATCH: "Shopify confirmó un plan o periodo diferente al esperado.",
  SHOPIFY_TRANSITION_STATE_CHANGED: "La instalación o suscripción cambió durante la operación.",
  SHOPIFY_SUBSCRIPTION_CANCELLATION_SCHEDULED: "Hay una cancelación programada; revisa el contrato en Shopify.",
  SHOPIFY_HOSTED_PRICING_NOT_CONFIGURED: "Falta configurar el identificador de la app en Shopify.",
  SHOPIFY_TRIAL_EVIDENCE_NOT_FOUND: "Shopify aún no devolvió evidencia de trial para el plan activo.",
  SHOPIFY_TRIAL_EVIDENCE_INVALID: "La evidencia de trial devuelta por Shopify no es válida.",
  SHOPIFY_TRIAL_EVIDENCE_NO_ACTIVE_PLAN: "No hay un plan Shopify activo que permita verificar el trial.",
};

function billingErrorMessage(error: unknown): string {
  if (error && typeof error === "object" && "response" in error) {
    const response = (error as { response?: { data?: { detail?: { code?: string } | string }; status?: number } }).response;
    const detail = response?.data?.detail;
    const code = typeof detail === "object" && detail ? detail.code : detail;
    if (typeof code === "string" && Object.prototype.hasOwnProperty.call(knownErrorCodes, code)) {
      return knownErrorCodes[code];
    }
    if (response?.status === 403) return "No tienes permisos para esta operación.";
    if (response?.status === 409) return "No se pudo confirmar el estado actual. Revisa el historial.";
    if (response?.status === 503) return "La verificación con Shopify no está disponible. Revisa la configuración Partner.";
  }
  return "No fue posible completar la consulta. Puedes intentarlo nuevamente.";
}

function labelStatus(value: string) {
  return statusLabels[value] ?? "Revisión requerida";
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Fecha no disponible"
    : new Intl.DateTimeFormat("es-CO", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export default function ShopifyBillingWorkspace({ organization }: Props) {
  const hasBillingAccess = organization.role === "owner" || organization.role === "manager";
  const isOwner = organization.role === "owner";

  const [history, setHistory] = useState<ShopifyBillingVerification[]>([]);
  const [reviews, setReviews] = useState<ShopifyPlanReview[]>([]);
  const [latestCheck, setLatestCheck] = useState<ShopifyBillingCheck | null>(null);
  const [capabilities, setCapabilities] = useState<ShopifyBillingCapabilities | null>(null);
  const [hostedPricingUrl, setHostedPricingUrl] = useState<string | null>(null);
  const [assessment, setAssessment] = useState<ShopifyReviewAssessment | null>(null);
  const [trialVerification, setTrialVerification] = useState<ShopifyTrialVerification | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"refresh" | "check" | "stage" | "assess" | "hosted" | "apply" | "subscription" | "trial" | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refreshHistory = useCallback(async () => {
    const [checks, proposals] = await Promise.all([
      getShopifyBillingHistory(),
      getShopifyPlanReviews(),
    ]);
    // The API enforces the org scope; discard responses inconsistent with
    // the currently displayed organization as an additional UI guard.
    if (checks.organization_id !== organization.id || proposals.organization_id !== organization.id) {
      throw new Error("Mismatched billing tenant");
    }
    setHistory(checks.items);
    setReviews(proposals.items);
  }, [organization.id]);

  useEffect(() => {
    let mounted = true;
    if (!hasBillingAccess) {
      setLoading(false);
      return () => { mounted = false; };
    }
    setLoading(true);
    Promise.all([
      getShopifyBillingHistory(),
      getShopifyPlanReviews(),
      getShopifyBillingCapabilities(),
    ])
      .then(([checks, proposals, flags]) => {
        if (!mounted) return;
        if (checks.organization_id !== organization.id || proposals.organization_id !== organization.id) {
          setError("No se pudo confirmar la organización de facturación.");
          return;
        }
        if (flags.organization_id !== organization.id || flags.paddle_checkout_available !== false) {
          setError("No se pudo validar el canal de facturación.");
          return;
        }
        setCapabilities(flags);
        setHistory(checks.items);
        setReviews(proposals.items);
      })
      .catch((cause: unknown) => { if (mounted) setError(billingErrorMessage(cause)); })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, [hasBillingAccess, organization.id]);

  async function run(
    action: "refresh" | "check" | "stage" | "assess" | "hosted" | "apply" | "subscription" | "trial",
    reviewId?: number,
  ) {
    if (!hasBillingAccess || busy) return;
    if ((action === "stage" || action === "apply") && !isOwner) return;
    if (action === "apply" && (
      !capabilities?.verified_entitlement_apply_enabled ||
      !assessment?.ready_for_manual_review ||
      assessment.review_id !== reviewId
    )) return;
    if (action === "apply" && !window.confirm(
      "Confirmar: Diaglob volverá a consultar Shopify y solo aplicará el plan si existe una suscripción activa y aprobada. No se efectuará ningún cobro desde Diaglob.",
    )) return;
    setBusy(action);
    setError("");
    setNotice("");
    try {
      if (action === "trial") {
        const result = await verifyShopifyTrial();
        if (
          result.organization_id !== organization.id ||
          result.verified_against_shopify !== true ||
          result.applied !== false
        ) {
          throw new Error("Invalid trial verification");
        }
        setTrialVerification(result);
        setNotice(
          result.matches_expected
            ? `Shopify confirmó un trial de ${result.observed_trial_days} días para el plan activo.`
            : `Atención: Shopify reporta ${result.observed_trial_days} días de trial; Diaglob espera ${result.expected_trial_days}.`,
        );
      } else if (action === "subscription") {
        const result = await refreshShopifySubscription();
        if (result.organization_id !== organization.id
          || result.verified_against_shopify !== true) {
          throw new Error("Invalid tenant billing state");
        }
        setNotice(result.subscription_status === "active"
          ? "Suscripción confirmada y activa en Shopify."
          : result.subscription_status === "inactive"
            ? "Shopify confirmó que no existe una suscripción activa. El acceso de pago se suspendió."
            : "Shopify confirmó un contrato diferente; las funciones de pago quedan en revisión.");
        setAssessment(null);
        await refreshHistory();
      } else if (action === "hosted") {
        const result = await getShopifyHostedPlanSelection();
        if (
          result.provider !== "shopify" || result.hosted_by_shopify !== true ||
          result.entitlements_applied !== false ||
          !result.url.startsWith("https://admin.shopify.com/store/")
        ) throw new Error("Invalid Shopify redirect");
        setHostedPricingUrl(result.url);
        setNotice("Abre la página de planes de Shopify usando el enlace seguro.");
      } else if (action === "apply" && reviewId) {
        const result = await applyVerifiedShopifyPlan(reviewId);
        if (result.organization_id !== organization.id) throw new Error("Wrong tenant");
        setAssessment(null);
        await refreshHistory();
        setNotice(result.applied
          ? "Shopify confirmó el contrato y el plan fue aplicado. Actualiza la página para ver los límites."
          : "El plan ya había sido aplicado; no se repitió ninguna operación.");
      } else if (action === "check") {
        const result = await checkShopifyBilling();
        if (result.applied !== false || result.requires_review !== true) {
          throw new Error("Unsafe provider response");
        }
        setLatestCheck(result);
        setAssessment(null);
        setNotice("Verificación registrada. Esto no modifica el plan.");
        await refreshHistory();
      } else if (action === "stage") {
        const latest = history[0];
        if (!latest || latest.status !== "plan_transition_requires_review" || !latest.target_plan) {
          setError("No hay una verificación de cambio de plan disponible.");
          return;
        }
        const result = await stageShopifyPlanReview(latest.id);
        if (result.applied !== false || result.requires_review !== true) {
          throw new Error("Unsafe review response");
        }
        setNotice("Propuesta preparada para revisión. No activa ni cobra un plan.");
        setAssessment(null);
        await refreshHistory();
      } else if (action === "assess" && reviewId) {
        const result = await assessShopifyPlanReview(reviewId);
        if (result.activation_allowed !== false || result.applied !== false || result.shopify_reverified_now !== false) {
          throw new Error("Unsafe assessment response");
        }
        setAssessment(result);
      } else {
        await refreshHistory();
        setAssessment(null);
        setNotice("Historial actualizado.");
      }
    } catch (cause) {
      setError(billingErrorMessage(cause));
    } finally {
      setBusy(null);
    }
  }

  const first = history[0];
  const mayStage = isOwner && first?.status === "plan_transition_requires_review" && !!first.target_plan;
  const activeReview = reviews.find((item) => item.status === "pending_review");

  return (
    <main className="content shopify-billing-workspace">
      <header className="shopify-billing-heading">
        <div>
          <p className="shopify-billing-eyebrow">DIAGLOB · SHOPIFY APP PRICING</p>
          <h1>Planes y facturación Shopify</h1>
          <p>Consulta el estado de la suscripción vinculada a tu tienda y revisa cualquier diferencia antes de modificar el acceso.</p>
        </div>
        <span className="shopify-billing-source"><ShieldCheck size={17} /> Gestionado en Shopify</span>
      </header>

      <div className="shopify-billing-caution" role="note">
        <AlertCircle size={20} aria-hidden="true" />
        <div>
          <strong>{capabilities?.verified_entitlement_apply_enabled
            ? "Los cambios requieren una confirmación nueva de Shopify."
            : "La activación de planes aún no está habilitada."}</strong>
          <p>Shopify administra los cobros. Verificar o preparar una propuesta no cambia el plan; la aplicación, si está habilitada, requiere confirmación activa de Shopify y autorización del propietario.</p>
        </div>
      </div>

      <div className="shopify-billing-stats">
        <section>
          <span>Plan actual en Diaglob</span>
          <strong>{organization.plan_name || organization.plan}</strong>
        </section>
        <section>
          <span>Estado actual de la suscripción</span>
          <strong>{organization.subscription_status || "No confirmado"}</strong>
          <small>No equivale a una verificación actual en Shopify</small>
        </section>
        <section>
          <span>Última verificación registrada</span>
          <strong>{first ? formatDate(first.observed_at) : "Sin verificaciones"}</strong>
        </section>
      </div>

      {!hasBillingAccess ? (
        <section className="shopify-billing-panel">
          <h2>Consulta restringida</h2>
          <p>Solo propietarios y administradores pueden revisar los datos de facturación de la organización.</p>
        </section>
      ) : (
        <>
          <section className="shopify-billing-panel">
            <div className="shopify-billing-panel-title">
              <div>
                <h2>Planes alojados en Shopify</h2>
                <p>Los cambios y los cobros se realizan en Shopify Admin, no en Diaglob.</p>
                {capabilities && (
                  <p className="shopify-billing-muted">
                    Planes: {capabilities.public_plans.map((plan) => (
                      plan.charAt(0).toUpperCase() + plan.slice(1)
                    )).join(" · ")}
                    {" · "}prueba gratis de {capabilities.trial_days} días
                    {" · "}facturación {capabilities.billing_period_months.includes(12) ? "mensual o anual" : "mensual"}.
                  </p>
                )}
              </div>
              <button type="button" className="shopify-billing-primary"
                disabled={Boolean(busy) || loading || !capabilities?.shopify_hosted_pricing_configured}
                onClick={() => { void run("hosted"); }}>
                {busy === "hosted" ? "Verificando tienda…" : "Abrir planes de Shopify"}
              </button>
            </div>
            {hostedPricingUrl && (
              <p className="shopify-billing-notice">
                <a href={hostedPricingUrl} target="_blank" rel="noopener noreferrer">
                  Ir a la selección de planes en Shopify Admin
                </a>
              </p>
            )}
            {!capabilities?.shopify_hosted_pricing_configured && (
              <p className="shopify-billing-muted">Los planes alojados aún requieren la configuración Partner de Diaglob.</p>
            )}
          </section>

          <section className="shopify-billing-panel">
            <div className="shopify-billing-panel-title">
              <div>
                <h2>Verificación con Shopify</h2>
                <p>Consulta nuevamente a Shopify únicamente cuando necesites revisar el contrato y sus condiciones.</p>
              </div>
              <div className="shopify-billing-actions">
                <button type="button" className="shopify-billing-secondary" disabled={Boolean(busy) || loading} onClick={() => { void run("refresh"); }}>
                  <RefreshCw size={16} /> Actualizar historial
                </button>
                {capabilities?.verified_entitlement_apply_enabled && (
                  <button type="button" className="shopify-billing-secondary"
                    disabled={Boolean(busy) || loading || !capabilities?.public_plans.includes(organization.plan)}
                    onClick={() => { void run("subscription"); }}>
                    <RefreshCw size={16} />
                    {busy === "subscription" ? "Comprobando acceso…" : "Comprobar acceso activo"}
                  </button>
                )}
                <button type="button" className="shopify-billing-secondary" disabled={Boolean(busy) || loading} onClick={() => { void run("trial"); }}>
                  <Clock3 size={16} /> {busy === "trial" ? "Verificando trial…" : "Verificar trial de 3 días"}
                </button>
                <button type="button" className="shopify-billing-primary" disabled={Boolean(busy) || loading} onClick={() => { void run("check"); }}>
                  <ShieldCheck size={17} /> {busy === "check" ? "Verificando…" : "Verificar suscripción"}
                </button>
              </div>
            </div>
            {error && <p className="shopify-billing-error" role="alert">{error}</p>}
            {notice && <p className="shopify-billing-notice" role="status">{notice}</p>}
            {loading ? <p role="status">Consultando historial…</p> : (
              <div className="shopify-billing-list">
                {history.length === 0 && <p>Aún no hay verificaciones registradas. El estado del plan no se modificará al consultar Shopify.</p>}
                {history.map((item) => (
                  <article key={item.id} className="shopify-billing-record">
                    <div>
                      <strong>{labelStatus(item.status)}</strong>
                      <small>Consulta #{item.id} · {formatDate(item.observed_at)} · Tienda #{item.store_id}</small>
                      <p>Plan: {item.current_plan} {item.target_plan ? <><ArrowRight size={14} aria-hidden="true" /> {item.target_plan}</> : " · sin plan confirmado"}</p>
                    </div>
                    <span className="shopify-billing-review-pill">Revisión requerida</span>
                  </article>
                ))}
              </div>
            )}
            {latestCheck && <p className="shopify-billing-muted">Última consulta realizada en esta sesión: #{latestCheck.verification_id} · {formatDate(latestCheck.verified_at)}</p>}
            {trialVerification && (
              <div className="shopify-billing-assessment" role="status">
                <strong>
                  Trial Shopify: {trialVerification.matches_expected ? "configuración correcta" : "requiere corrección"}
                </strong>
                <p>
                  Esperado: {trialVerification.expected_trial_days} días · observado: {trialVerification.observed_trial_days} días · restantes: {trialVerification.trial_days_remaining}.
                </p>
                <small>
                  Plan {trialVerification.plan} · {trialVerification.billing_period_months === 12 ? "anual" : "mensual"}
                  {trialVerification.trial_ends_at ? ` · termina ${formatDate(trialVerification.trial_ends_at)}` : ""}
                </small>
              </div>
            )}
          </section>

          <section className="shopify-billing-panel">
            <div className="shopify-billing-panel-title">
              <div>
                <h2>Propuestas de cambio</h2>
                <p>Cada propuesta requiere una verificación reciente y puede caducar o quedar invalidada si cambia la conexión.</p>
              </div>
              {isOwner && (
                <button
                  type="button"
                  className="shopify-billing-secondary"
                  disabled={Boolean(busy) || loading || !mayStage || Boolean(activeReview)}
                  onClick={() => { void run("stage"); }}
                >
                  <Clock3 size={16} /> {busy === "stage" ? "Preparando…" : "Preparar revisión"}
                </button>
              )}
            </div>
            {isOwner && !mayStage && <p className="shopify-billing-muted">Para preparar una revisión necesitas una verificación reciente que recomiende revisar un cambio de plan.</p>}
            <div className="shopify-billing-list">
              {reviews.length === 0 && <p>No hay propuestas de cambio de plan registradas.</p>}
              {reviews.map((review) => (
                <article className="shopify-billing-record" key={review.id}>
                  <div>
                    <strong>{labelStatus(review.status)}</strong>
                    <small>Revisión #{review.id} · caduca {formatDate(review.expires_at)}</small>
                    <p>{review.baseline_plan} <ArrowRight size={14} aria-hidden="true" /> {review.target_plan} · {review.target_billing_period_months === 12 ? "Anual" : "Mensual"}</p>
                  </div>
                  <button type="button" className="shopify-billing-secondary" disabled={Boolean(busy)} onClick={() => { void run("assess", review.id); }}>
                    Comprobar vigencia
                  </button>
                </article>
              ))}
            </div>
            {assessment && (
              <div className="shopify-billing-assessment" role="status">
                <strong>Revisión #{assessment.review_id}: {assessment.ready_for_manual_review ? "Sin bloqueos internos actuales" : "Revisión bloqueada"}</strong>
                <p>{assessment.ready_for_manual_review
                  ? "La información interna parece vigente, pero es obligatorio volver a verificar Shopify antes de cualquier activación."
                  : "La propuesta requiere revisión antes de poder continuar."}</p>
                {assessment.blockers.length > 0 && (
                  <ul>{assessment.blockers.map((code) => <li key={code}>{explanations[code] ?? "Se requiere una nueva verificación."}</li>)}</ul>
                )}
                <small>Comprobado: {formatDate(assessment.checked_at)} · Los contratos se revalidan antes de cualquier cambio.</small>
                {isOwner && capabilities?.verified_entitlement_apply_enabled && assessment.ready_for_manual_review && (
                  <button type="button" className="shopify-billing-primary"
                    disabled={Boolean(busy)}
                    onClick={() => { void run("apply", assessment.review_id); }}>
                    {busy === "apply" ? "Confirmando con Shopify…" : "Aplicar plan verificado"}
                  </button>
                )}
              </div>
            )}
          </section>
        </>
      )}

      <footer className="shopify-billing-footer">
        <CheckCircle2 size={18} aria-hidden="true" />
        <span>Las suscripciones se administran desde Shopify. Esta sección no utiliza Paddle ni inicia pagos.</span>
      </footer>
    </main>
  );
}
