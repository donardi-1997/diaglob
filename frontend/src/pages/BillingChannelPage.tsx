import { useCallback, useEffect, useState } from "react";

import PlansPage from "./PlansPage";
import ShopifyBillingWorkspace from "./ShopifyBillingWorkspace";
import { getShopifyBillingCapabilities } from "../services/shopifyBilling";
import {
  getCurrentOrganization,
  type Organization,
} from "../services/organizations";
import { billingChannel } from "../services/billingChannel";
import { createPaddlePortalSession, getPaddleBillingStatus, type PaddleBillingStatus } from "../services/billing";
import "../shopify-billing-workspace.css";

/** Prevents accidentally presenting Paddle checkout to Shopify-managed shops. */
export default function BillingChannelPage({
  userEmail,
}: {
  userEmail?: string | null;
}) {
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
    return <main className="billing-channel-state" role="status">Cargando facturación…</main>;
  }
  if (error || !organization) {
    return (
      <main className="billing-channel-state">
        <h1>No fue posible consultar tu facturación</h1>
        <p>Por seguridad, no mostramos enlaces de pago hasta confirmar tu organización.</p>
        <button type="button" onClick={() => { void load(); }}>Reintentar</button>
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
      setPortalError("No fue posible abrir el portal de Paddle. Inténtalo de nuevo.");
    } finally {
      setPortalLoading(false);
    }
  }

  switch (billingChannel(organization.billing_provider)) {
    case "shopify":
      return <ShopifyBillingWorkspace organization={organization} />;
    case "paddle":
      if (shopifyMigrationRequired) {
        return (
          <ShopifyBillingWorkspace
            organization={organization}
            paddleMigrationStatus={paddleStatus}
            onPaddleMigrationRefresh={() => { void load(); }}
          />
        );
      }
      return (
        <>
          {paddleStatus?.portal_available && (
            <section className="billing-channel-state">
              <h2>Facturación de tu cuenta</h2>
              <p>Consulta facturas, medios de pago y renovaciones en el portal seguro de Paddle.</p>
              <button type="button" disabled={portalLoading} onClick={() => { void openPortal(); }}>
                {portalLoading ? "Abriendo portal…" : "Administrar facturación en Paddle"}
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
            <h1>Termina de conectar tu tienda Shopify</h1>
            <p>Tu cuenta de Diaglob está preparada para Shopify, pero todavía debemos verificar la instalación. Crea o selecciona una tienda y completa su autorización OAuth desde la sección Tiendas.</p>
            <p>Mientras la conexión esté pendiente, los pagos y los cambios de plan permanecerán deshabilitados. No se ha creado ninguna suscripción.</p>
            <a href="/app/stores">Ir a mis tiendas</a>
          </main>
        );
      }
      return (
        <main className="billing-channel-state">
          <h1>Proveedor de facturación por confirmar</h1>
          <p>No hemos podido determinar si tu organización se factura por Shopify o Paddle. Por seguridad, las operaciones de pago están deshabilitadas. Contacta con soporte para revisar tu cuenta.</p>
          <button type="button" onClick={() => { void load(); }}>Volver a consultar</button>
        </main>
      );
  }
}
