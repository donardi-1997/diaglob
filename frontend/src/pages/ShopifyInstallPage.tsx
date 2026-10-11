import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, LockKeyhole, ShieldCheck, Store } from "lucide-react";

import { connectShopify, getPendingShopifyInstall, claimPendingShopifyInstall } from "../services/integrations";
import { getStoresForManagement, type Store as DiaglobStore } from "../services/stores";
import {
  eligibleShopifyInstallStores,
  parseShopifyInstallHint,
  validatedShopifyAuthorizationUrl,
} from "../shopifyInstall";
import "../shopify-install.css";

interface Props {
  canWrite: boolean;
}

export default function ShopifyInstallPage({ canWrite }: Props) {
  const location = useLocation();
  const navigate = useNavigate();
  const oauthCompleted = location.search === "?authorized=1";
  const [authorizedShop, setAuthorizedShop] = useState<string | null>(null);
  const [checkingGrant, setCheckingGrant] = useState(oauthCompleted);
  const shop = useMemo(
    () => oauthCompleted ? authorizedShop : parseShopifyInstallHint(location.search),
    [location.search, oauthCompleted, authorizedShop],
  );
  const [stores, setStores] = useState<DiaglobStore[]>([]);
  const [selected, setSelected] = useState("");
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!oauthCompleted || !canWrite) {
      setCheckingGrant(false);
      return;
    }
    let live = true;
    setCheckingGrant(true);
    getPendingShopifyInstall()
      .then((result) => {
        if (!live) return;
        if (!result.pending || !result.shop_domain) {
          setError("La autorización de Shopify expiró o ya fue utilizada. Inicia la instalación nuevamente desde Shopify.");
          return;
        }
        setAuthorizedShop(result.shop_domain);
      })
      .catch(() => {
        if (live) setError("No fue posible recuperar la autorización de Shopify.");
      })
      .finally(() => { if (live) setCheckingGrant(false); });
    return () => { live = false; };
  }, [oauthCompleted, canWrite]);

  useEffect(() => {
    let active = true;
    if (!canWrite || !shop) {
      setLoading(false);
      return () => { active = false; };
    }

    setLoading(true);
    getStoresForManagement()
      .then((result) => {
        if (!active) return;
        setStores(result.items);
        setError("");
      })
      .catch(() => {
        if (active) setError("No pudimos cargar las tiendas autorizadas.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [shop, canWrite]);

  const eligibleStores = useMemo(
    () => shop ? eligibleShopifyInstallStores(stores, shop) : [],
    [stores, shop],
  );

  async function handleConnect() {
    if (!canWrite || !shop || connecting) return;
    const chosen = eligibleStores.find((store) => String(store.id) === selected);
    if (!chosen) {
      setError("Selecciona una tienda válida antes de continuar.");
      return;
    }
    setConnecting(true);
    setError("");
    try {
      if (oauthCompleted) {
        // The grant is already verified by Shopify and bound by an HttpOnly,
        // short-lived one-use cookie. Tenant authorization stays server-side.
        await claimPendingShopifyInstall(chosen.id);
        navigate("/app/stores?shopify=connected", { replace: true });
      } else {
        const result = await connectShopify(chosen.id, shop);
        const destination = validatedShopifyAuthorizationUrl(
          result.authorization_url, shop,
        );
        window.location.assign(destination);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "No fue posible conectar Shopify.");
      setConnecting(false);
    }
  }

  return (
    <main className="shopify-install-page">
      <section className="shopify-install-card">
        <div className="shopify-install-icon"><Store size={25} aria-hidden="true" /></div>
        <p className="shopify-install-eyebrow">DIAGLOB + SHOPIFY</p>
        <h1>Conecta tu tienda Shopify</h1>
        <p>Selecciona la tienda de Diaglob que administrará tu operación. Solo después de confirmarlo te enviaremos a Shopify para aprobar los permisos.</p>
        {checkingGrant ? (
          <p role="status">Validando la autorización de Shopify…</p>
        ) : !shop ? (
          <p className="shopify-install-error" role="alert">
            {oauthCompleted ? (error || "La autorización de Shopify no está disponible.") : "El enlace de instalación no contiene una tienda Shopify válida."}
          </p>
        ) : (
          <>
            <div className="shopify-install-shop">
              <ShieldCheck size={19} aria-hidden="true" />
              <span>Dominio solicitado</span>
              <strong>{shop}</strong>
            </div>
            <p className="shopify-install-hint">
              {oauthCompleted
                ? "Shopify confirmó la tienda. Selecciona a qué espacio autorizado de Diaglob vincularla. No se generará ningún cargo."
                : "El dominio aún no está verificado. La conexión solo se establecerá al completar la autorización de Shopify."}
            </p>
            {!canWrite ? (
              <p className="shopify-install-error" role="alert">
                Necesitas permisos para administrar las tiendas de Diaglob.
              </p>
            ) : loading ? (
              <p role="status">Cargando las tiendas de tu organización…</p>
            ) : eligibleStores.length === 0 ? (
              <p role="status">
                No hay tiendas disponibles. Crea una tienda en Diaglob o revisa si ya tiene una integración asignada.
              </p>
            ) : (
              <label className="shopify-install-label" htmlFor="shopify-install-store">
                Tienda de Diaglob
                <select
                  id="shopify-install-store"
                  value={selected}
                  onChange={(event) => setSelected(event.target.value)}
                  disabled={connecting}
                >
                  <option value="">Seleccionar tienda…</option>
                  {eligibleStores.map((store) => (
                    <option value={store.id} key={store.id}>
                      {store.name} — {store.country_code}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {error && <p className="shopify-install-error" role="alert">{error}</p>}
            <button
              className="shopify-install-primary"
              type="button"
              disabled={!canWrite || !selected || !shop || connecting || loading}
              onClick={() => { void handleConnect(); }}
            >
              {connecting ? "Conectando…" : oauthCompleted ? "Finalizar conexión" : "Continuar a Shopify"}
              {!connecting && <ArrowRight size={18} aria-hidden="true" />}
            </button>
          </>
        )}
        <button className="shopify-install-secondary" type="button" onClick={() => navigate("/app/stores")}>
          Administrar tiendas en Diaglob
        </button>
        <p className="shopify-install-footer">
          <LockKeyhole size={16} aria-hidden="true" />
          No compartiremos credenciales, crearemos cargos ni vincularemos tiendas sin tu autorización.
        </p>
      </section>
    </main>
  );
}
