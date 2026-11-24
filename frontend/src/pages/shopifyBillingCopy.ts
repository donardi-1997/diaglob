export type BillingLocale = "es" | "en" | "pt-BR";

export function normalizeBillingLocale(language: string | undefined): BillingLocale {
  const value = (language || "").toLowerCase();
  if (value.startsWith("pt")) return "pt-BR";
  if (value.startsWith("en")) return "en";
  return "es";
}

export const BILLING_DATE_LOCALE: Record<BillingLocale, string> = {
  es: "es-CO",
  en: "en-US",
  "pt-BR": "pt-BR",
};

export interface BillingCopy {
  explanations: Record<string, string>;
  statusLabels: Record<string, string>;
  knownErrorCodes: Record<string, string>;
  errorForbidden: string;
  errorConflict: string;
  errorUnavailable: string;
  errorGeneric: string;
  reviewRequired: string;
  dateUnavailable: string;
  orgMismatch: string;
  channelMismatch: string;
  applyConfirm: string;
  trialMatches: (days: number | null) => string;
  trialMismatch: (observed: string, expected: number) => string;
  noTrial: string;
  subscriptionActive: string;
  subscriptionInactive: string;
  subscriptionDifferent: string;
  openHostedNotice: string;
  planApplied: string;
  planAlreadyApplied: string;
  checkRegistered: string;
  noTransitionVerification: string;
  reviewPrepared: string;
  historyUpdated: string;
  returnVerifying: string;
  returnScheduledChange: string;
  returnPlanConfirmed: string;
  returnOwnerActivation: string;
  returnNeedsRecheck: string;
  returnApplied: (plan: string) => string;
  returnAlreadyApplied: (plan: string) => string;
  title: string;
  subtitle: string;
  managedInShopify: string;
  cautionApplyEnabled: string;
  cautionApplyDisabled: string;
  cautionBody: string;
  reviewNeeded: string;
  currentPlan: string;
  currentStatus: string;
  notConfirmed: string;
  notCurrentVerification: string;
  lastVerification: string;
  noVerifications: string;
  restrictedTitle: string;
  restrictedBody: string;
  hostedTitle: string;
  hostedBody: string;
  plansLabel: string;
  freeTrial: (days: number) => string;
  billingMonthlyOrAnnual: string;
  billingMonthly: string;
  billingLabel: (period: string) => string;
  verifyingStore: string;
  openShopifyPlans: string;
  goToShopifyPlans: string;
  hostedNotConfigured: string;
  verificationTitle: string;
  verificationBody: string;
  refreshHistory: string;
  checkingAccess: string;
  checkAccess: string;
  verifyingTrial: string;
  verifyTrial: (days: number) => string;
  verifying: string;
  verifySubscription: string;
  loadingHistory: string;
  noHistory: string;
  checkLine: (id: number, date: string, storeId: number) => string;
  planLabel: string;
  noConfirmedPlan: string;
  lastSessionCheck: (id: number, date: string) => string;
  trialStatus: (ok: boolean) => string;
  trialDetails: (expected: number, observed: string, remaining: string) => string;
  notConfigured: string;
  daysSuffix: string;
  annual: string;
  monthly: string;
  annualCap: string;
  monthlyCap: string;
  endsOn: (date: string) => string;
  proposalsTitle: string;
  proposalsBody: string;
  preparing: string;
  prepareReview: string;
  prepareHint: string;
  noProposals: string;
  reviewLine: (id: number, date: string) => string;
  checkValidity: string;
  assessmentTitle: (id: number, ready: boolean) => string;
  assessmentReady: string;
  assessmentBlocked: string;
  newVerificationRequired: string;
  checkedAt: (date: string) => string;
  confirmingWithShopify: string;
  applyVerifiedPlan: string;
  footer: string;
}

const es: BillingCopy = {
  explanations: {
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
  },
  statusLabels: {
    plan_verified_no_change: "Plan verificado sin cambios",
    plan_transition_requires_review: "Cambio de plan para revisión",
    subscription_inactive_requires_review: "Suscripción inactiva: revisión necesaria",
    pending_review: "Pendiente de revisión",
    applied: "Plan aplicado y verificado",
    stale: "Caducada",
    blocked: "Bloqueada",
    ready_for_manual_review: "Lista para revisión manual",
  },
  knownErrorCodes: {
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
  },
  errorForbidden: "No tienes permisos para esta operación.",
  errorConflict: "No se pudo confirmar el estado actual. Revisa el historial.",
  errorUnavailable: "La verificación con Shopify no está disponible. Revisa la configuración Partner.",
  errorGeneric: "No fue posible completar la consulta. Puedes intentarlo nuevamente.",
  reviewRequired: "Revisión requerida",
  dateUnavailable: "Fecha no disponible",
  orgMismatch: "No se pudo confirmar la organización de facturación.",
  channelMismatch: "No se pudo validar el canal de facturación.",
  applyConfirm: "Confirmar: Diaglob volverá a consultar Shopify y solo aplicará el plan si existe una suscripción activa y aprobada. No se efectuará ningún cobro desde Diaglob.",
  trialMatches: (days) => `Shopify confirmó un trial de ${days} días para el plan activo.`,
  trialMismatch: (observed, expected) => `Atención: Shopify reporta ${observed}; Diaglob espera ${expected} días.`,
  noTrial: "sin trial",
  subscriptionActive: "Suscripción confirmada y activa en Shopify.",
  subscriptionInactive: "Shopify confirmó que no existe una suscripción activa. El acceso de pago se suspendió.",
  subscriptionDifferent: "Shopify confirmó un contrato diferente; las funciones de pago quedan en revisión.",
  openHostedNotice: "Abre la página de planes de Shopify usando el enlace seguro.",
  planApplied: "Shopify confirmó el contrato y el plan fue aplicado. Actualiza la página para ver los límites.",
  planAlreadyApplied: "El plan ya había sido aplicado; no se repitió ninguna operación.",
  checkRegistered: "Verificación registrada. Esto no modifica el plan.",
  noTransitionVerification: "No hay una verificación de cambio de plan disponible.",
  reviewPrepared: "Propuesta preparada para revisión. No activa ni cobra un plan.",
  historyUpdated: "Historial actualizado.",
  returnVerifying: "Shopify devolvió el control a Diaglob. Verificando el contrato activo…",
  returnScheduledChange: "Shopify confirmó un cambio programado para un próximo ciclo. Diaglob mantendrá el plan activo actual hasta que Shopify haga efectivo el cambio.",
  returnPlanConfirmed: "Shopify confirmó el plan activo. No hay cambios de acceso pendientes.",
  returnOwnerActivation: "Shopify confirmó un cambio de plan. La verificación quedó registrada y requiere la activación segura del propietario.",
  returnNeedsRecheck: "Shopify confirmó el cambio, pero la revisión interna necesita una nueva comprobación.",
  returnApplied: (plan) => `Plan ${plan} aplicado después de una segunda verificación con Shopify.`,
  returnAlreadyApplied: (plan) => `El plan ${plan} ya estaba aplicado; no se repitió ninguna operación.`,
  title: "Planes y facturación Shopify",
  subtitle: "Consulta el estado de la suscripción vinculada a tu tienda y revisa cualquier diferencia antes de modificar el acceso.",
  managedInShopify: "Gestionado en Shopify",
  cautionApplyEnabled: "Los cambios requieren una confirmación nueva de Shopify.",
  cautionApplyDisabled: "La activación de planes aún no está habilitada.",
  cautionBody: "Shopify administra los cobros. Verificar o preparar una propuesta no cambia el plan; la aplicación, si está habilitada, requiere confirmación activa de Shopify y autorización del propietario.",
  reviewNeeded: "revisión necesaria",
  currentPlan: "Plan actual en Diaglob",
  currentStatus: "Estado actual de la suscripción",
  notConfirmed: "No confirmado",
  notCurrentVerification: "No equivale a una verificación actual en Shopify",
  lastVerification: "Última verificación registrada",
  noVerifications: "Sin verificaciones",
  restrictedTitle: "Consulta restringida",
  restrictedBody: "Solo propietarios y administradores pueden revisar los datos de facturación de la organización.",
  hostedTitle: "Planes alojados en Shopify",
  hostedBody: "Los cambios y los cobros se realizan en Shopify Admin, no en Diaglob.",
  plansLabel: "Planes",
  freeTrial: (days) => `prueba gratis de ${days} días`,
  billingMonthlyOrAnnual: "mensual o anual",
  billingMonthly: "mensual",
  billingLabel: (period) => `facturación ${period}`,
  verifyingStore: "Verificando tienda…",
  openShopifyPlans: "Abrir planes de Shopify",
  goToShopifyPlans: "Ir a la selección de planes en Shopify Admin",
  hostedNotConfigured: "Los planes alojados aún requieren la configuración Partner de Diaglob.",
  verificationTitle: "Verificación con Shopify",
  verificationBody: "Consulta nuevamente a Shopify únicamente cuando necesites revisar el contrato y sus condiciones.",
  refreshHistory: "Actualizar historial",
  checkingAccess: "Comprobando acceso…",
  checkAccess: "Comprobar acceso activo",
  verifyingTrial: "Verificando trial…",
  verifyTrial: (days) => `Verificar trial de ${days} días`,
  verifying: "Verificando…",
  verifySubscription: "Verificar suscripción",
  loadingHistory: "Consultando historial…",
  noHistory: "Aún no hay verificaciones registradas. El estado del plan no se modificará al consultar Shopify.",
  checkLine: (id, date, storeId) => `Consulta #${id} · ${date} · Tienda #${storeId}`,
  planLabel: "Plan",
  noConfirmedPlan: " · sin plan confirmado",
  lastSessionCheck: (id, date) => `Última consulta realizada en esta sesión: #${id} · ${date}`,
  trialStatus: (ok) => `Trial Shopify: ${ok ? "configuración correcta" : "requiere corrección"}`,
  trialDetails: (expected, observed, remaining) => `Esperado: ${expected} días · observado: ${observed} · restantes: ${remaining}.`,
  notConfigured: "sin configurar",
  daysSuffix: " días",
  annual: "anual",
  monthly: "mensual",
  annualCap: "Anual",
  monthlyCap: "Mensual",
  endsOn: (date) => ` · termina ${date}`,
  proposalsTitle: "Propuestas de cambio",
  proposalsBody: "Cada propuesta requiere una verificación reciente y puede caducar o quedar invalidada si cambia la conexión.",
  preparing: "Preparando…",
  prepareReview: "Preparar revisión",
  prepareHint: "Para preparar una revisión necesitas una verificación reciente que recomiende revisar un cambio de plan.",
  noProposals: "No hay propuestas de cambio de plan registradas.",
  reviewLine: (id, date) => `Revisión #${id} · caduca ${date}`,
  checkValidity: "Comprobar vigencia",
  assessmentTitle: (id, ready) => `Revisión #${id}: ${ready ? "Sin bloqueos internos actuales" : "Revisión bloqueada"}`,
  assessmentReady: "La información interna parece vigente, pero es obligatorio volver a verificar Shopify antes de cualquier activación.",
  assessmentBlocked: "La propuesta requiere revisión antes de poder continuar.",
  newVerificationRequired: "Se requiere una nueva verificación.",
  checkedAt: (date) => `Comprobado: ${date} · Los contratos se revalidan antes de cualquier cambio.`,
  confirmingWithShopify: "Confirmando con Shopify…",
  applyVerifiedPlan: "Aplicar plan verificado",
  footer: "Las suscripciones se contratan, cambian y cobran en Shopify. Esta sección no inicia pagos.",
};

const en: BillingCopy = {
  explanations: {
    REVIEW_NOT_PENDING: "The proposal is no longer pending.",
    REVIEW_EXPIRED: "The proposal has expired.",
    VERIFICATION_MISSING: "The original verification was not found.",
    NEWER_VERIFICATION_EXISTS: "There is a more recent Shopify verification.",
    VERIFICATION_EXPIRED: "The Shopify verification has expired.",
    VERIFICATION_MISMATCH: "The plan details no longer match.",
    ORGANIZATION_INACTIVE: "The organization is inactive.",
    BILLING_CHANNEL_CHANGED: "The billing provider changed.",
    BASELINE_PLAN_CHANGED: "The current plan changed.",
    LEGACY_BILLING_REFERENCES: "A previous subscription needs review.",
    SHOPIFY_BINDINGS_CHANGED: "The number of linked stores changed.",
    SHOPIFY_INSTALLATION_CHANGED: "The Shopify connection was replaced or disconnected.",
    STORE_UNAVAILABLE: "The store is paused or deleted.",
  },
  statusLabels: {
    plan_verified_no_change: "Plan verified, no changes",
    plan_transition_requires_review: "Plan change pending review",
    subscription_inactive_requires_review: "Inactive subscription: review needed",
    pending_review: "Pending review",
    applied: "Plan applied and verified",
    stale: "Expired",
    blocked: "Blocked",
    ready_for_manual_review: "Ready for manual review",
  },
  knownErrorCodes: {
    SHOPIFY_BILLING_PROVENANCE_REQUIRED: "This organization is not set up for Shopify billing.",
    SHOPIFY_MULTISTORE_BILLING_REVIEW_REQUIRED: "There are several Shopify links; a billing review is needed.",
    SHOPIFY_BILLING_CONNECTION_REVIEW_REQUIRED: "The Shopify connection needs review.",
    SHOPIFY_BILLING_STATE_CHANGED: "The connection status changed during verification.",
    SHOPIFY_PLAN_PRICE_UNVERIFIED: "Shopify did not confirm a verifiable price.",
    SHOPIFY_PLAN_PRICE_MISMATCH: "The Shopify price does not match the approved price.",
    SHOPIFY_PLAN_CATALOG_INVALID: "The approved price catalog needs configuration.",
    SHOPIFY_TRANSITION_STALE_VERIFICATION: "The verification expired or is no longer the latest.",
    SHOPIFY_TRANSITION_REVIEW_ALREADY_PENDING: "Another plan review is already pending.",
    SHOPIFY_TRANSITION_INSTALLATION_OR_PLAN_CHANGED: "The installation or plan changed.",
    SHOPIFY_TRANSITION_CONCURRENT_REVIEW: "Another proposal is being processed. Refresh the history.",
    SHOPIFY_ENTITLEMENT_ACTIVATION_DISABLED: "Applying plans is not yet enabled in Diaglob.",
    SHOPIFY_TRANSITION_PROVIDER_MISMATCH: "Shopify confirmed a different plan or period than expected.",
    SHOPIFY_TRANSITION_STATE_CHANGED: "The installation or subscription changed during the operation.",
    SHOPIFY_SUBSCRIPTION_CANCELLATION_SCHEDULED: "A cancellation is scheduled; review the contract in Shopify.",
    SHOPIFY_HOSTED_PRICING_NOT_CONFIGURED: "The app identifier in Shopify still needs to be configured.",
    SHOPIFY_TRIAL_EVIDENCE_NOT_FOUND: "Shopify has not returned trial evidence for the active plan yet.",
    SHOPIFY_TRIAL_EVIDENCE_INVALID: "The trial evidence returned by Shopify is not valid.",
    SHOPIFY_TRIAL_EVIDENCE_NO_ACTIVE_PLAN: "There is no active Shopify plan to verify the trial against.",
  },
  errorForbidden: "You don't have permission for this operation.",
  errorConflict: "The current status could not be confirmed. Check the history.",
  errorUnavailable: "Verification with Shopify is unavailable. Check the Partner configuration.",
  errorGeneric: "The request could not be completed. You can try again.",
  reviewRequired: "Review required",
  dateUnavailable: "Date unavailable",
  orgMismatch: "The billing organization could not be confirmed.",
  channelMismatch: "The billing channel could not be validated.",
  applyConfirm: "Confirm: Diaglob will check Shopify again and only apply the plan if there is an active, approved subscription. Diaglob will not charge you.",
  trialMatches: (days) => `Shopify confirmed a ${days}-day trial for the active plan.`,
  trialMismatch: (observed, expected) => `Attention: Shopify reports ${observed}; Diaglob expects ${expected} days.`,
  noTrial: "no trial",
  subscriptionActive: "Subscription confirmed and active in Shopify.",
  subscriptionInactive: "Shopify confirmed there is no active subscription. Paid access was suspended.",
  subscriptionDifferent: "Shopify confirmed a different contract; paid features are under review.",
  openHostedNotice: "Open the Shopify plans page using the secure link.",
  planApplied: "Shopify confirmed the contract and the plan was applied. Refresh the page to see the limits.",
  planAlreadyApplied: "The plan was already applied; no operation was repeated.",
  checkRegistered: "Verification recorded. This does not change the plan.",
  noTransitionVerification: "There is no plan-change verification available.",
  reviewPrepared: "Proposal prepared for review. It does not activate or charge a plan.",
  historyUpdated: "History updated.",
  returnVerifying: "Shopify returned control to Diaglob. Verifying the active contract…",
  returnScheduledChange: "Shopify confirmed a change scheduled for an upcoming cycle. Diaglob keeps the current plan until Shopify applies the change.",
  returnPlanConfirmed: "Shopify confirmed the active plan. There are no pending access changes.",
  returnOwnerActivation: "Shopify confirmed a plan change. The verification was recorded and needs secure activation by the owner.",
  returnNeedsRecheck: "Shopify confirmed the change, but the internal review needs a new check.",
  returnApplied: (plan) => `Plan ${plan} applied after a second verification with Shopify.`,
  returnAlreadyApplied: (plan) => `Plan ${plan} was already applied; no operation was repeated.`,
  title: "Shopify plans and billing",
  subtitle: "Check the status of the subscription linked to your store and review any difference before changing access.",
  managedInShopify: "Managed in Shopify",
  cautionApplyEnabled: "Changes require a new confirmation from Shopify.",
  cautionApplyDisabled: "Plan activation is not enabled yet.",
  cautionBody: "Shopify handles charges. Verifying or preparing a proposal does not change the plan; applying it, when enabled, requires an active Shopify confirmation and the owner's authorization.",
  reviewNeeded: "review needed",
  currentPlan: "Current plan in Diaglob",
  currentStatus: "Current subscription status",
  notConfirmed: "Not confirmed",
  notCurrentVerification: "This is not a current Shopify verification",
  lastVerification: "Last recorded verification",
  noVerifications: "No verifications",
  restrictedTitle: "Restricted",
  restrictedBody: "Only owners and managers can review the organization's billing details.",
  hostedTitle: "Plans hosted by Shopify",
  hostedBody: "Changes and charges happen in Shopify Admin, not in Diaglob.",
  plansLabel: "Plans",
  freeTrial: (days) => `${days}-day free trial`,
  billingMonthlyOrAnnual: "monthly or annual",
  billingMonthly: "monthly",
  billingLabel: (period) => `${period} billing`,
  verifyingStore: "Verifying store…",
  openShopifyPlans: "Open Shopify plans",
  goToShopifyPlans: "Go to plan selection in Shopify Admin",
  hostedNotConfigured: "Hosted plans still need Diaglob's Partner configuration.",
  verificationTitle: "Verification with Shopify",
  verificationBody: "Check Shopify again only when you need to review the contract and its terms.",
  refreshHistory: "Refresh history",
  checkingAccess: "Checking access…",
  checkAccess: "Check active access",
  verifyingTrial: "Verifying trial…",
  verifyTrial: (days) => `Verify ${days}-day trial`,
  verifying: "Verifying…",
  verifySubscription: "Verify subscription",
  loadingHistory: "Loading history…",
  noHistory: "No verifications recorded yet. Checking Shopify does not change the plan.",
  checkLine: (id, date, storeId) => `Check #${id} · ${date} · Store #${storeId}`,
  planLabel: "Plan",
  noConfirmedPlan: " · no confirmed plan",
  lastSessionCheck: (id, date) => `Last check in this session: #${id} · ${date}`,
  trialStatus: (ok) => `Shopify trial: ${ok ? "set up correctly" : "needs correction"}`,
  trialDetails: (expected, observed, remaining) => `Expected: ${expected} days · observed: ${observed} · remaining: ${remaining}.`,
  notConfigured: "not set up",
  daysSuffix: " days",
  annual: "annual",
  monthly: "monthly",
  annualCap: "Annual",
  monthlyCap: "Monthly",
  endsOn: (date) => ` · ends ${date}`,
  proposalsTitle: "Change proposals",
  proposalsBody: "Each proposal needs a recent verification and may expire or become invalid if the connection changes.",
  preparing: "Preparing…",
  prepareReview: "Prepare review",
  prepareHint: "To prepare a review you need a recent verification that recommends reviewing a plan change.",
  noProposals: "No plan-change proposals recorded.",
  reviewLine: (id, date) => `Review #${id} · expires ${date}`,
  checkValidity: "Check validity",
  assessmentTitle: (id, ready) => `Review #${id}: ${ready ? "No current internal blockers" : "Review blocked"}`,
  assessmentReady: "Internal data looks current, but Shopify must be verified again before any activation.",
  assessmentBlocked: "The proposal needs review before it can continue.",
  newVerificationRequired: "A new verification is required.",
  checkedAt: (date) => `Checked: ${date} · Contracts are revalidated before any change.`,
  confirmingWithShopify: "Confirming with Shopify…",
  applyVerifiedPlan: "Apply verified plan",
  footer: "Subscriptions are purchased, changed and billed in Shopify. This section does not start payments.",
};

const ptBR: BillingCopy = {
  ...en,
  explanations: {
    REVIEW_NOT_PENDING: "A proposta não está mais pendente.",
    REVIEW_EXPIRED: "A proposta expirou.",
    VERIFICATION_MISSING: "A verificação original não foi encontrada.",
    NEWER_VERIFICATION_EXISTS: "Existe uma verificação mais recente da Shopify.",
    VERIFICATION_EXPIRED: "A verificação da Shopify expirou.",
    VERIFICATION_MISMATCH: "Os dados do plano não coincidem mais.",
    ORGANIZATION_INACTIVE: "A organização está inativa.",
    BILLING_CHANNEL_CHANGED: "O provedor de cobrança mudou.",
    BASELINE_PLAN_CHANGED: "O plano atual mudou.",
    LEGACY_BILLING_REFERENCES: "Há uma assinatura anterior que precisa de revisão.",
    SHOPIFY_BINDINGS_CHANGED: "A quantidade de lojas vinculadas mudou.",
    SHOPIFY_INSTALLATION_CHANGED: "A conexão com a Shopify foi substituída ou desconectada.",
    STORE_UNAVAILABLE: "A loja está pausada ou excluída.",
  },
  statusLabels: {
    plan_verified_no_change: "Plano verificado sem alterações",
    plan_transition_requires_review: "Mudança de plano para revisão",
    subscription_inactive_requires_review: "Assinatura inativa: revisão necessária",
    pending_review: "Revisão pendente",
    applied: "Plano aplicado e verificado",
    stale: "Expirada",
    blocked: "Bloqueada",
    ready_for_manual_review: "Pronta para revisão manual",
  },
  errorForbidden: "Você não tem permissão para esta operação.",
  errorConflict: "Não foi possível confirmar o status atual. Revise o histórico.",
  errorUnavailable: "A verificação com a Shopify não está disponível. Revise a configuração Partner.",
  errorGeneric: "Não foi possível concluir a consulta. Tente novamente.",
  reviewRequired: "Revisão necessária",
  dateUnavailable: "Data indisponível",
  title: "Planos e cobrança Shopify",
  subtitle: "Consulte o status da assinatura vinculada à sua loja e revise qualquer diferença antes de alterar o acesso.",
  managedInShopify: "Gerenciado na Shopify",
  cautionApplyEnabled: "As mudanças exigem uma nova confirmação da Shopify.",
  cautionApplyDisabled: "A ativação de planos ainda não está habilitada.",
  cautionBody: "A Shopify administra as cobranças. Verificar ou preparar uma proposta não altera o plano; a aplicação, quando habilitada, exige confirmação ativa da Shopify e autorização do proprietário.",
  currentPlan: "Plano atual na Diaglob",
  currentStatus: "Status atual da assinatura",
  notConfirmed: "Não confirmado",
  notCurrentVerification: "Não equivale a uma verificação atual na Shopify",
  lastVerification: "Última verificação registrada",
  noVerifications: "Sem verificações",
  restrictedTitle: "Consulta restrita",
  restrictedBody: "Somente proprietários e administradores podem revisar os dados de cobrança da organização.",
  hostedTitle: "Planos hospedados na Shopify",
  hostedBody: "As mudanças e cobranças acontecem no Shopify Admin, não na Diaglob.",
  plansLabel: "Planos",
  freeTrial: (days) => `teste grátis de ${days} dias`,
  billingMonthlyOrAnnual: "mensal ou anual",
  billingMonthly: "mensal",
  billingLabel: (period) => `cobrança ${period}`,
  verifyingStore: "Verificando loja…",
  openShopifyPlans: "Abrir planos da Shopify",
  goToShopifyPlans: "Ir para a seleção de planos no Shopify Admin",
  hostedNotConfigured: "Os planos hospedados ainda exigem a configuração Partner da Diaglob.",
  verificationTitle: "Verificação com a Shopify",
  verificationBody: "Consulte a Shopify novamente apenas quando precisar revisar o contrato e suas condições.",
  refreshHistory: "Atualizar histórico",
  checkingAccess: "Verificando acesso…",
  checkAccess: "Verificar acesso ativo",
  verifyingTrial: "Verificando teste…",
  verifyTrial: (days) => `Verificar teste de ${days} dias`,
  verifying: "Verificando…",
  verifySubscription: "Verificar assinatura",
  loadingHistory: "Consultando histórico…",
  noHistory: "Ainda não há verificações registradas. Consultar a Shopify não altera o plano.",
  checkLine: (id, date, storeId) => `Consulta #${id} · ${date} · Loja #${storeId}`,
  planLabel: "Plano",
  noConfirmedPlan: " · sem plano confirmado",
  daysSuffix: " dias",
  annual: "anual",
  monthly: "mensal",
  annualCap: "Anual",
  monthlyCap: "Mensal",
  proposalsTitle: "Propostas de mudança",
  proposalsBody: "Cada proposta exige uma verificação recente e pode expirar ou ser invalidada se a conexão mudar.",
  preparing: "Preparando…",
  prepareReview: "Preparar revisão",
  prepareHint: "Para preparar uma revisão, você precisa de uma verificação recente que recomende revisar uma mudança de plano.",
  noProposals: "Não há propostas de mudança de plano registradas.",
  reviewLine: (id, date) => `Revisão #${id} · expira ${date}`,
  checkValidity: "Verificar validade",
  applyVerifiedPlan: "Aplicar plano verificado",
  footer: "As assinaturas são contratadas, alteradas e cobradas na Shopify. Esta seção não inicia pagamentos.",
};

export const BILLING_COPY: Record<BillingLocale, BillingCopy> = {
  es,
  en,
  "pt-BR": ptBR,
};
