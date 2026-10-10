import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, LockKeyhole, ShieldCheck, Store } from "lucide-react";

import { connectShopify } from "../services/integrations";
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
  const shop = useMemo(
    () => parseShopifyInstallHint(location.search),
    [location.search],
  );
  const [stores, setStores] = useState<DiaglobStore[]>([]);
  const [selected, setSelected] = useState("");
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState("");

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
      // Authorization is determined by DIAGLOB stores.write and OAuth state,
      // not by the untrusted public Shopify 'shop' query parameter.
      const result = await connectShopify(chosen.id, shop);
      const destination = validatedShopifyAuthorizationUrl(
        result.authorization_url, shop,
      );
      window.location.assign(destination);
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
        {!shop ? (
          <p className="shopify-install-error" role="alert">
            El enlace de instalación no contiene una tienda Shopify válida.
          </p>
        ) : (
          <>
            <div className="shopify-install-shop">
              <ShieldCheck size={19} aria-hidden="true" />
              <span>Dominio solicitado</span>
              <strong>{shop}</strong>
            </div>
            <p className="shopify-install-hint">
              El dominio aún no está verificado. La conexión solo se establecerá al completar la autorización de Shopify.
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
              {connecting ? "Redirigiendo a Shopify…" : "Continuar a Shopify"}
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
