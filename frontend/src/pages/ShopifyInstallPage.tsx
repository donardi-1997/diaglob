import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, LockKeyhole, ShieldCheck, Store } from "lucide-react";
import { getMarkets, type Market } from "../services/markets";

import { connectShopify, getPendingShopifyInstall, claimPendingShopifyInstall, verifyManagedShopifyClaimCode, claimManagedShopifyInstall } from "../services/integrations";
import { createStore, getStoresForManagement, type Store as DiaglobStore } from "../services/stores";
import {
  eligibleShopifyInstallStores,
  buildPostOAuthStorePayload,
  parseShopifyInstallHint,
  parseShopifyInstallMode,
  validatedShopifyAuthorizationUrl,
} from "../shopifyInstall";
import "../shopify-install.css";

interface Props {
  canWrite: boolean;
  onStoresChanged?: () => void;
}

export default function ShopifyInstallPage({ canWrite, onStoresChanged }: Props) {
  const location = useLocation();
  const navigate = useNavigate();
  const installMode = parseShopifyInstallMode(location.search);
  const oauthCompleted = installMode === "authorized";
  const managedInstall = installMode === "managed";
  const [claimCode, setClaimCode] = useState("");
  const [managedVerifying, setManagedVerifying] = useState(false);
  const [managedVerified, setManagedVerified] = useState(false);
  const authorizedGrant = oauthCompleted || (managedInstall && managedVerified);
  const [authorizedShop, setAuthorizedShop] = useState<string | null>(null);
  const [checkingGrant, setCheckingGrant] = useState(oauthCompleted);
  const shop = useMemo(
    () => authorizedGrant ? authorizedShop : managedInstall ? null : parseShopifyInstallHint(location.search),
    [location.search, authorizedGrant, authorizedShop, managedInstall],
  );
  const [stores, setStores] = useState<DiaglobStore[]>([]);
  const [selected, setSelected] = useState("");
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState("");
  const [markets, setMarkets] = useState<Market[]>([]);
  const [marketsLoading, setMarketsLoading] = useState(false);
  const [marketsError, setMarketsError] = useState(false);
  const [newStoreName, setNewStoreName] = useState("");
  const [newCountry, setNewCountry] = useState("");

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

  async function verifyManagedCode() {
    if (!managedInstall || !canWrite || managedVerifying || !claimCode.trim()) return;
    setManagedVerifying(true);
    setManagedVerified(false);
    setAuthorizedShop(null);
    setError("");
    try {
      const status = await verifyManagedShopifyClaimCode(claimCode.trim());
      if (!status.pending || !status.shop_domain) {
        throw new Error("El código expiró o no pertenece a una instalación disponible.");
      }
      setAuthorizedShop(status.shop_domain);
      setManagedVerified(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo verificar el código.");
    } finally {
      setManagedVerifying(false);
    }
  }

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


  useEffect(() => {
    if (!authorizedGrant || !shop || !canWrite) return;
    let live = true;
    setMarketsLoading(true);
    setMarketsError(false);
    getMarkets()
      .then((result) => {
        if (live) setMarkets(result.items);
      })
      .catch(() => {
        if (live) setMarketsError(true);
      })
      .finally(() => {
        if (live) setMarketsLoading(false);
      });
    return () => { live = false; };
  }, [authorizedGrant, shop, canWrite]);

  // The shop label is merely a draft name. The domain is obtained from
  // Shopify's verified pending grant, not from user input.
  useEffect(() => {
    if (authorizedGrant && shop) setNewStoreName(shop.split(".myshopify.com")[0]);
  }, [authorizedGrant, shop]);

  async function handleCreateAndConnect() {
    if (!authorizedGrant || !authorizedShop || !canWrite || connecting || checkingGrant) return;
    setError("");
    setConnecting(true);
    try {
      const payload = buildPostOAuthStorePayload(
        authorizedShop,
        newStoreName,
        newCountry,
        markets.map((market) => market.country_code),
      );
      const created = await createStore(payload);
      // Retain the new authorized store even if the claim or webhook setup
      // fails. The user can retry binding without creating duplicate stores.
      setStores((current) => [...current, created]);
      setSelected(String(created.id));
      onStoresChanged?.();
      if (managedInstall) await claimManagedShopifyInstall(created.id, claimCode.trim());
      else await claimPendingShopifyInstall(created.id);
      setClaimCode("");
      navigate("/app/stores?shopify=connected", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "No fue posible finalizar la conexión con Shopify.");
    } finally {
      setConnecting(false);
    }
  }

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
      if (authorizedGrant) {
        // A verified managed claim code or HttpOnly OAuth claim is bound only
        // after a separately authenticated, store-authorized DIAGLOB login.
        if (managedInstall) await claimManagedShopifyInstall(chosen.id, claimCode.trim());
        else await claimPendingShopifyInstall(chosen.id);
        setClaimCode("");
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
        <p>{authorizedGrant
          ? "Shopify ya verificó esta instalación. Selecciona una tienda autorizada de Diaglob o crea una nueva para finalizar."
          : managedInstall
            ? "Introduce el código temporal que obtuviste dentro de la aplicación Diaglob en Shopify Admin."
            : "Selecciona la tienda de Diaglob que administrará tu operación. Después te enviaremos a Shopify para aprobar los permisos."}</p>
        {managedInstall && !managedVerified && (
          <div className="shopify-install-bootstrap">
            <label className="shopify-install-label" htmlFor="shopify-managed-code">
              Código temporal de Shopify
              <input id="shopify-managed-code" value={claimCode}
                onChange={(event) => setClaimCode(event.target.value)}
                autoComplete="off" maxLength={100} />
            </label>
            <button type="button" className="shopify-install-primary"
              disabled={!canWrite || !claimCode.trim() || managedVerifying}
              onClick={() => { void verifyManagedCode(); }}>
              {managedVerifying ? "Comprobando…" : "Validar instalación de Shopify"}
            </button>
            {error && <p role="alert" className="shopify-install-error">{error}</p>}
          </div>
        )}
        {managedInstall && !managedVerified ? null : checkingGrant ? (
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
            ) : eligibleStores.length === 0 && authorizedGrant ? (
              <section className="shopify-install-bootstrap" aria-labelledby="shopify-new-store-title">
                <h2 id="shopify-new-store-title">Crear una tienda para esta instalación</h2>
                <p>La autorización de Shopify está confirmada, pero aún no hay una tienda local compatible. Elige el mercado donde operará y asígnale un nombre.</p>
                <label className="shopify-install-label" htmlFor="shopify-new-store-name">
                  Nombre de la tienda
                  <input
                    id="shopify-new-store-name"
                    value={newStoreName}
                    maxLength={150}
                    onChange={(event) => setNewStoreName(event.target.value)}
                    disabled={connecting}
                  />
                </label>
                <label className="shopify-install-label" htmlFor="shopify-new-store-market">
                  País / mercado
                  <select
                    id="shopify-new-store-market"
                    value={newCountry}
                    onChange={(event) => setNewCountry(event.target.value)}
                    disabled={connecting || marketsLoading || marketsError}
                  >
                    <option value="">Seleccionar mercado…</option>
                    {markets.map((market) => (
                      <option key={market.country_code} value={market.country_code}>
                        {market.country_name}
                      </option>
                    ))}
                  </select>
                </label>
                {marketsLoading && <p role="status">Cargando mercados…</p>}
                {marketsError && (
                  <p role="alert" className="shopify-install-error">
                    No pudimos cargar los mercados. Regresa a Tiendas y vuelve a intentar.
                  </p>
                )}
                {error && <p role="alert" className="shopify-install-error">{error}</p>}
                <button
                  className="shopify-install-primary"
                  type="button"
                  disabled={connecting || !newStoreName.trim() || !newCountry || marketsLoading || marketsError}
                  onClick={() => { void handleCreateAndConnect(); }}
                >
                  {connecting ? "Creando y conectando…" : "Crear tienda y finalizar conexión"}
                  {!connecting && <ArrowRight size={18} aria-hidden="true" />}
                </button>
                <p className="shopify-install-hint">No se inicia una suscripción ni se crean pedidos. Las funciones de pago requieren la autorización de Shopify.</p>
              </section>
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
            {eligibleStores.length > 0 && (
              <button
                className="shopify-install-primary"
                type="button"
                disabled={!canWrite || !selected || !shop || connecting || loading}
                onClick={() => { void handleConnect(); }}
              >
                {connecting ? "Conectando…" : authorizedGrant ? "Finalizar conexión" : "Continuar a Shopify"}
                {!connecting && <ArrowRight size={18} aria-hidden="true" />}
              </button>
            )}
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
