import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import PlansPage from "./PlansPage";
import { normalizeBillingLocale, type BillingLocale } from "./shopifyBillingCopy";
import ShopifyBillingWorkspace from "./ShopifyBillingWorkspace";
import { getShopifyBillingCapabilities } from "../services/shopifyBilling";
import {
  getCurrentOrganization,
  type Organization,
} from "../services/organizations";
import { billingChannel } from "../services/billingChannel";
import { createPaddlePortalSession, getPaddleBillingStatus, type PaddleBillingStatus } from "../services/billing";
import "../shopify-billing-workspace.css";

const CHANNEL_COPY: Record<BillingLocale, {
  loading: string;
  errorTitle: string;
  errorBody: string;
  retry: string;
  portalError: string;
  accountBillingTitle: string;
  accountBillingBody: string;
  openingPortal: string;
  managePaddle: string;
  pendingShopifyTitle: string;
  pendingShopifyBody: string;
  pendingShopifyNote: string;
  goToStores: string;
  unknownTitle: string;
  unknownBody: string;
  checkAgain: string;
}> = {
  es: {
    loading: "Cargando facturación…",
    errorTitle: "No fue posible consultar tu facturación",
    errorBody: "Por seguridad, no mostramos enlaces de pago hasta confirmar tu organización.",
    retry: "Reintentar",
    portalError: "No fue posible abrir el portal de Paddle. Inténtalo de nuevo.",
    accountBillingTitle: "Facturación de tu cuenta",
    accountBillingBody: "Consulta facturas, medios de pago y renovaciones en el portal seguro de Paddle.",
    openingPortal: "Abriendo portal…",
    managePaddle: "Administrar facturación en Paddle",
    pendingShopifyTitle: "Termina de conectar tu tienda Shopify",
    pendingShopifyBody: "Tu cuenta de Diaglob está preparada para Shopify, pero todavía debemos verificar la instalación. Crea o selecciona una tienda y completa su autorización OAuth desde la sección Tiendas.",
    pendingShopifyNote: "Mientras la conexión esté pendiente, los pagos y los cambios de plan permanecerán deshabilitados. No se ha creado ninguna suscripción.",
    goToStores: "Ir a mis tiendas",
    unknownTitle: "Proveedor de facturación por confirmar",
    unknownBody: "No hemos podido determinar el canal de facturación de tu organización. Por seguridad, las operaciones de pago están deshabilitadas. Contacta con soporte para revisar tu cuenta.",
    checkAgain: "Volver a consultar",
  },
  en: {
    loading: "Loading billing…",
    errorTitle: "We couldn't load your billing",
    errorBody: "For security, we don't show payment links until your organization is confirmed.",
    retry: "Retry",
    portalError: "We couldn't open the Paddle portal. Please try again.",
    accountBillingTitle: "Account billing",
    accountBillingBody: "View invoices, payment methods and renewals in Paddle's secure portal.",
    openingPortal: "Opening portal…",
    managePaddle: "Manage billing in Paddle",
    pendingShopifyTitle: "Finish connecting your Shopify store",
    pendingShopifyBody: "Your Diaglob account is ready for Shopify, but we still need to verify the installation. Create or select a store and complete its authorization from the Stores section.",
    pendingShopifyNote: "While the connection is pending, payments and plan changes stay disabled. No subscription has been created.",
    goToStores: "Go to my stores",
    unknownTitle: "Billing provider not confirmed",
    unknownBody: "We couldn't determine your organization's billing channel. For security, payment operations are disabled. Contact support to review your account.",
    checkAgain: "Check again",
  },
  "pt-BR": {
    loading: "Carregando cobrança…",
    errorTitle: "Não foi possível consultar sua cobrança",
    errorBody: "Por segurança, não mostramos links de pagamento até confirmar sua organização.",
    retry: "Tentar novamente",
    portalError: "Não foi possível abrir o portal da Paddle. Tente novamente.",
    accountBillingTitle: "Cobrança da sua conta",
    accountBillingBody: "Consulte faturas, meios de pagamento e renovações no portal seguro da Paddle.",
    openingPortal: "Abrindo portal…",
    managePaddle: "Gerenciar cobrança na Paddle",
    pendingShopifyTitle: "Termine de conectar sua loja Shopify",
    pendingShopifyBody: "Sua conta Diaglob está pronta para a Shopify, mas ainda precisamos verificar a instalação. Crie ou selecione uma loja e conclua a autorização na seção Lojas.",
    pendingShopifyNote: "Enquanto a conexão estiver pendente, pagamentos e mudanças de plano ficam desativados. Nenhuma assinatura foi criada.",
    goToStores: "Ir para minhas lojas",
    unknownTitle: "Provedor de cobrança a confirmar",
    unknownBody: "Não conseguimos determinar o canal de cobrança da sua organização. Por segurança, as operações de pagamento estão desativadas. Fale com o suporte para revisar sua conta.",
    checkAgain: "Consultar novamente",
  },
};

/** Prevents accidentally presenting Paddle checkout to Shopify-managed shops. */
export default function BillingChannelPage({
  userEmail,
}: {
  userEmail?: string | null;
}) {
  const { i18n } = useTranslation();
  const copy = CHANNEL_COPY[normalizeBillingLocale(i18n.resolvedLanguage || i18n.language)];
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [portalLoading, setPortalLoading] = useState(false);
  const [portalError, setPortalError] = useState("");
  const [paddleStatus, setPaddleStatus] = useState<PaddleBillingStatus | null>(null);
  const [shopifyMigrationRequired, setShopifyMigrationRequired] = useState(false);

  const load = useCallback(async (isCurrent: () => boolean = () => true) => {
    setLoading(true);
    setError(false);
    setOrganization(null);
    setPaddleStatus(null);
    setShopifyMigrationRequired(false);
    try {
      const result = await getCurrentOrganization();
      let migrationRequired = false;
      let status: PaddleBillingStatus | null = null;
      if (billingChannel(result.billing_provider) === "paddle") {
        try {
          status = await getPaddleBillingStatus();
          migrationRequired = status.migration_required === true;
        } catch {
          try {
            migrationRequired = (await getShopifyBillingCapabilities()).paddle_migration_required;
          } catch {
            status = null;
          }
        }
      }
      if (isCurrent()) {
        setOrganization(result);
        setPaddleStatus(status);
        setShopifyMigrationRequired(migrationRequired);
      }
    } catch {
      if (isCurrent()) setError(true);
    } finally {
      if (isCurrent()) setLoading(false);
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    void load(() => mounted);
    return () => { mounted = false; };
  }, [load]);

  if (loading) {
    return <main className="billing-channel-state" role="status">{copy.loading}</main>;
  }
  if (error || !organization) {
    return (
      <main className="billing-channel-state">
        <h1>{copy.errorTitle}</h1>
        <p>{copy.errorBody}</p>
        <button type="button" onClick={() => { void load(); }}>{copy.retry}</button>
      </main>
    );
  }

  async function openPortal() {
    if (portalLoading || !paddleStatus?.portal_available) return;
    setPortalError("");
    setPortalLoading(true);
    try {
      // The authenticated server resolves the Paddle customer for this tenant.
      const { url } = await createPaddlePortalSession();
      window.location.assign(url);
    } catch {
      setPortalError(copy.portalError);
    } finally {
      setPortalLoading(false);
    }
  }

  switch (billingChannel(organization.billing_provider)) {
    case "shopify":
      return <ShopifyBillingWorkspace organization={organization} />;
    case "paddle":
      if (shopifyMigrationRequired) {
        // Shopify-connected tenants only see Shopify App Pricing. Any legacy
        // off-platform renewal is handled by DIAGLOB support, never in-app.
        return <ShopifyBillingWorkspace organization={organization} />;
      }
      return (
        <>
          {paddleStatus?.portal_available && (
            <section className="billing-channel-state">
              <h2>{copy.accountBillingTitle}</h2>
              <p>{copy.accountBillingBody}</p>
              <button type="button" disabled={portalLoading} onClick={() => { void openPortal(); }}>
                {portalLoading ? copy.openingPortal : copy.managePaddle}
              </button>
              {portalError && <p role="alert">{portalError}</p>}
            </section>
          )}
          <PlansPage
            userEmail={userEmail}
            paddlePlanChangesAvailable={Boolean(paddleStatus?.plan_changes_available)}
          />
        </>
      );
    default:
      if (organization.billing_onboarding_channel === "shopify_install") {
        return (
          <main className="billing-channel-state">
            <h1>{copy.pendingShopifyTitle}</h1>
            <p>{copy.pendingShopifyBody}</p>
            <p>{copy.pendingShopifyNote}</p>
            <a href="/app/stores">{copy.goToStores}</a>
          </main>
        );
      }
      return (
        <main className="billing-channel-state">
          <h1>{copy.unknownTitle}</h1>
          <p>{copy.unknownBody}</p>
          <button type="button" onClick={() => { void load(); }}>{copy.checkAgain}</button>
        </main>
      );
  }
}
