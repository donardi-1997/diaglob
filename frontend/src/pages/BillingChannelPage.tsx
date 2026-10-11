import { useCallback, useEffect, useState } from "react";

import PlansPage from "./PlansPage";
import ShopifyBillingWorkspace from "./ShopifyBillingWorkspace";
import {
  getCurrentOrganization,
  type Organization,
} from "../services/organizations";
import "../shopify-billing-workspace.css";

export type BillingChannel = "shopify" | "paddle" | "unverified";

export function billingChannel(value: string | null | undefined): BillingChannel {
  const normalized = typeof value === "string" ? value.trim().toLowerCase() : "";
  if (normalized === "shopify") return "shopify";
  if (normalized === "paddle") return "paddle";
  return "unverified";
}

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
      return (
        <main className="billing-channel-state">
          <h1>Proveedor de facturación por confirmar</h1>
          <p>No hemos podido determinar si tu organización se factura por Shopify o Paddle. Por seguridad, las operaciones de pago están deshabilitadas. Contacta con soporte para revisar tu cuenta.</p>
          <button type="button" onClick={() => { void load(); }}>Volver a consultar</button>
        </main>
      );
  }
}
