import { useEffect, useState } from "react";
import DropiOperationsPanel from "./DropiOperationsPanel";
import { Check, Loader2, Plug, RefreshCw, Trash2, Truck } from "lucide-react";

import {
  connectDropi,
  disconnectDropi,
  getDropiStatus,
  previewDropiCatalog,
  testDropiConnection,
  type DropiCatalogPreview,
  type DropiConnectionStatus,
} from "../services/integrations";

interface Props {
  storeId: number;
  canWrite: boolean;
  shopifyConnected: boolean;
  detectedFromShopify: boolean;
}

const errorMessages: Record<string, string> = {
  DROPI_PARTNER_APPROVAL_REQUIRED:
    "Conector preparado, pero aún requiere la habilitación de integración directa con Dropi. No se envió ninguna solicitud.",
  DROPI_AUTH_FAILED: "Dropi rechazó este token. Comprueba el país, la tienda y el token.",
  DROPI_AUTH_OR_PROVIDER_ERROR: "Dropi no validó la consulta con ese token.",
  DROPI_COUNTRY_UNSUPPORTED: "Dropi no admite el país configurado para esta tienda.",
  DROPPI_ALREADY_CONNECTED: "Ya existe un token guardado. Desconéctalo antes de reemplazarlo.",
  DROPPI_NOT_VERIFIED: "Primero hay que validar el token de Dropi.",
};

function getSafeError(err: unknown): string {
  const response = err as { response?: { data?: { detail?: { code?: string } } } };
  const code = response?.response?.data?.detail?.code;
  return (code && errorMessages[code]) || "No se pudo completar la operación con Dropi.";
}

export default function DropiNativeIntegrationCard({
  storeId,
  canWrite,
  shopifyConnected,
  detectedFromShopify,
}: Props) {
  const [status, setStatus] = useState<DropiConnectionStatus | null>(null);
  const [token, setToken] = useState("");
  const [catalog, setCatalog] = useState<DropiCatalogPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setStatus(null);
    setCatalog(null);
    setToken("");
    setError("");
    getDropiStatus(storeId)
      .then((result) => { if (alive) setStatus(result); })
      .catch(() => {
        if (alive) setError("No fue posible consultar el estado de Dropi.");
      })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [storeId]);

  async function execute(operation: () => Promise<void>) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await operation();
    } catch (err: unknown) {
      setError(getSafeError(err));
    } finally {
      setBusy(false);
    }
  }

  const saved = Boolean(status && status.status !== "disconnected");
  const verified = Boolean(status?.connected && status.status === "verified");

  return (
    <div className="store-integration-block dropi">
      <div className="store-integration-header">
        <div className="store-integration-title">
          <Truck size={17} />
          <strong>Dropi · Conector Diaglob</strong>
          <span className={verified ? "integration-status connected" : "integration-status disconnected"}>
            {verified ? "Token validado" : saved ? "Pendiente de validación" : "Sin conectar"}
          </span>
        </div>
      </div>

      <div className="store-integration-detail">
        <p>
          Usa tu token de integración de Dropi en Diaglob. No necesitas instalar WooCommerce:
          Diaglob actúa como adaptador entre Dropi y tu tienda Shopify.
        </p>
        <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: 8 }}>
          La compatibilidad del token y la autorización de Dropi deben verificarse antes
          de habilitar la importación de productos, órdenes o logística.
          Guardar el token no significa que Dropi esté conectado.
        </p>
        {detectedFromShopify && (
          <p style={{ fontSize: "0.78rem", marginTop: 8 }}>
            <Check size={13} aria-hidden="true" /> Shopify ya contiene productos detectados como Dropi.
            Esto no prueba una conexión API.
          </p>
        )}
        {!shopifyConnected && (
          <p style={{ fontSize: "0.78rem", marginTop: 8 }}>
            Conecta primero Shopify para configurar la sincronización de la tienda.
          </p>
        )}
      </div>

      {loading ? (
        <div className="store-integration-detail"><Loader2 className="spin" size={16} /> Consultando conexión…</div>
      ) : (
        <>
          {error && <div className="stores-alert error" role="alert">{error}</div>}
          {message && <div className="stores-alert success" role="status">{message}</div>}
          {canWrite && !saved && (
            <form
              className="store-integration-detail"
              onSubmit={(event) => {
                event.preventDefault();
                void execute(async () => {
                  await connectDropi(storeId, token.trim());
                  setToken("");
                  setStatus(await getDropiStatus(storeId));
                  setMessage("Token guardado cifrado. La conexión aún debe validarse.");
                });
              }}
            >
              <label htmlFor={`dropi-integration-token-${storeId}`}>Token de integración de Dropi</label>
              <input
                id={`dropi-integration-token-${storeId}`}
                type="password"
                autoComplete="off"
                required
                value={token}
                onChange={(event) => setToken(event.target.value)}
                placeholder="Introduce tu token de Dropi"
                style={{ width: "100%", marginTop: 8 }}
                disabled={busy || !shopifyConnected}
              />
              <div className="store-integration-actions">
                <button
                  type="submit"
                  className="store-integration-button primary"
                  disabled={busy || !token.trim() || !shopifyConnected}
                >
                  {busy ? <Loader2 className="spin" size={15} /> : <Plug size={15} />}
                  Guardar token
                </button>
              </div>
            </form>
          )}
          {saved && (
            <div className="store-integration-actions">
              {canWrite && (
                <button
                  type="button"
                  className="store-integration-button secondary"
                  onClick={() => void execute(async () => {
                    setStatus(await testDropiConnection(storeId));
                    setMessage("Dropi respondió correctamente a una consulta de catálogo.");
                  })}
                  disabled={busy}
                >
                  {busy ? <Loader2 className="spin" size={15} /> : <RefreshCw size={15} />}
                  Probar token
                </button>
              )}
              {verified && (
                <button
                  type="button"
                  className="store-integration-button secondary"
                  onClick={() => void execute(async () => {
                    setCatalog(await previewDropiCatalog(storeId));
                    setMessage("Catálogo de prueba obtenido en modo solo lectura.");
                  })}
                  disabled={busy}
                >
                  Vista previa de productos
                </button>
              )}
              {canWrite && (
                <button
                  type="button"
                  className="store-integration-button danger"
                  onClick={() => void execute(async () => {
                    await disconnectDropi(storeId);
                    setStatus(await getDropiStatus(storeId));
                    setCatalog(null);
                    setMessage("Token desconectado y eliminado.");
                  })}
                  disabled={busy}
                >
                  <Trash2 size={15} />
                  Desconectar
                </button>
              )}
            </div>
          )}
          {shopifyConnected && (
            <DropiOperationsPanel storeId={storeId} canWrite={canWrite} />
          )}
          {catalog && (
            <div className="store-integration-detail">
              <strong>Productos consultados: {catalog.total_returned}</strong>
              <ul>
                {catalog.items.map((item, index) => (
                  <li key={String(item.id ?? index)}>
                    {String(item.name ?? "Sin nombre")} · SKU: {String(item.sku ?? "—")}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}
