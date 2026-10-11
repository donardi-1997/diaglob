import { useCallback, useEffect, useState } from "react";

import PlansPage from "./PlansPage";
import ShopifyBillingWorkspace from "./ShopifyBillingWorkspace";
import {
  getCurrentOrganization,
  type Organization,
} from "../services/organizations";
import { billingChannel } from "../services/billingChannel";
import "../shopify-billing-workspace.css";

/** Prevents accidentally presenting Paddle checkout to Shopify-managed shops. */
export default function BillingChannelPage() {
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (isCurrent: () => boolean = () => true) => {
    setLoading(true);
    setError(false);
    setOrganization(null);
    try {
      const result = await getCurrentOrganization();
      if (isCurrent()) setOrganization(result);
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

  switch (billingChannel(organization.billing_provider)) {
    case "shopify":
      return <ShopifyBillingWorkspace organization={organization} />;
    case "paddle":
      return <PlansPage />;
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
