import { useEffect, useState, type FormEvent } from "react";
import { Check, Loader2, Plug, ShoppingBag, Trash2, Truck } from "lucide-react";
import {
  connectWooCommerce,
  disconnectWooCommerce,
  getWooCommerceStatus,
  previewWooCommerce,
  testWooCommerce,
  type WooCommercePreview,
  type WooCommerceStatus,
} from "../services/integrations";

type Props = {
  storeId: number;
  canWrite: boolean;
  otherCommerceProvider?: string | null;
};

function safeError(err: unknown): string {
  const response = err as { response?: { data?: { detail?: { code?: string } } } };
  return response?.response?.data?.detail?.code || "No fue posible completar la operación de WooCommerce.";
}

export default function WooCommerceIntegrationCard({ storeId, canWrite, otherCommerceProvider }: Props) {
  const [status, setStatus] = useState<WooCommerceStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [siteUrl, setSiteUrl] = useState("");
  const [consumerKey, setConsumerKey] = useState("");
  const [consumerSecret, setConsumerSecret] = useState("");
  const [preview, setPreview] = useState<WooCommercePreview | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const blocked = Boolean(otherCommerceProvider && otherCommerceProvider !== "woocommerce");

  useEffect(() => {
    let current = true;
    setLoading(true);
    setPreview(null);
    getWooCommerceStatus(storeId)
      .then((result) => { if (current) setStatus(result); })
      .catch(() => { if (current) setError("No se pudo consultar WooCommerce."); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [storeId]);

  async function onConnect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await connectWooCommerce(storeId, siteUrl, consumerKey, consumerSecret);
      setStatus(result);
      setConsumerKey("");
      setConsumerSecret("");
      setShowForm(false);
      setMessage("WooCommerce verificado. Falta validar el plugin Dropify con Dropi.");
    } catch (err) {
      setError(safeError(err));
    } finally {
      setBusy(false);
    }
  }

  async function onTest() {
    setBusy(true);
    setError("");
    try {
      setStatus(await testWooCommerce(storeId));
      setMessage("Conexión REST confirmada. La comunicación de Dropify con Dropi sigue por verificar.");
    } catch (err) {
      setError(safeError(err));
    } finally {
      setBusy(false);
    }
  }

  async function onPreview(resource: "products" | "orders") {
    setBusy(true);
    setError("");
    setPreview(null);
    try {
      setPreview(await previewWooCommerce(storeId, resource));
    } catch (err) {
      setError(safeError(err));
    } finally {
      setBusy(false);
    }
  }

  async function onDisconnect() {
    if (!window.confirm("¿Desconectar WooCommerce de Diaglob? No afecta el plugin Dropify.")) return;
    setBusy(true);
    setError("");
    try {
      setStatus(await disconnectWooCommerce(storeId));
      setPreview(null);
      setMessage("Credenciales de WooCommerce eliminadas de la conexión.");
    } catch (err) {
      setError(safeError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="store-integration-block woocommerce">
      <div className="store-integration-header">
        <div className="store-integration-title">
          <Truck size={17} />
          <strong>WooCommerce + Dropi</strong>
          <span className={status?.connected ? "integration-status connected" : "integration-status disconnected"}>
            {status?.connected ? "WooCommerce conectado · Dropi sin verificar" : "Sin conectar"}
          </span>
        </div>
      </div>
      <div className="store-integration-detail">
        <p>
          Diaglob consulta WooCommerce mediante su API oficial. El token de Dropi se
          configura en el plugin Dropify de WordPress, no en Diaglob.
        </p>
        {status?.external_store_url && <p><strong>Tienda:</strong> {status.external_store_url}</p>}
        {blocked && <p>Esta tienda de Diaglob ya tiene {otherCommerceProvider} asociado. Desconéctalo antes de cambiar de plataforma.</p>}
        {status?.connected && <p><strong>Validación pendiente:</strong> importar un producto mediante Dropify, crear un pedido de prueba y comprobar su registro en Dropi.</p>}
      </div>
      {loading && <Loader2 className="spin" size={16} />}
      {error && <div className="stores-alert error" role="alert">{error}</div>}
      {message && <div className="stores-alert success" role="status"><Check size={14} /> {message}</div>}
      {canWrite && !status?.connected && !blocked && (
        <div className="store-integration-actions">
          <button type="button" className="store-integration-button primary" onClick={() => setShowForm(!showForm)}>
            <Plug size={14} /> Conectar WooCommerce
          </button>
        </div>
      )}
      {showForm && !status?.connected && !blocked && (
        <form className="store-integration-whatsapp-form" onSubmit={(e) => void onConnect(e)}>
          <label><span>URL HTTPS de WooCommerce</span>
            <input type="url" required placeholder="https://mitienda.com" value={siteUrl}
              onChange={(e) => setSiteUrl(e.target.value)} autoComplete="url" />
          </label>
          <label><span>WooCommerce Consumer Key (ck_...)</span>
            <input required type="password" value={consumerKey} autoComplete="off" onChange={(e) => setConsumerKey(e.target.value)} />
          </label>
          <label><span>WooCommerce Consumer Secret (cs_...)</span>
            <input required type="password" value={consumerSecret} autoComplete="off" onChange={(e) => setConsumerSecret(e.target.value)} />
          </label>
          <p>No pegues aquí el token de Dropi. En WordPress: WooCommerce → Ajustes → Avanzado → API REST.</p>
          <div className="store-integration-actions">
            <button className="store-integration-button primary" type="submit" disabled={busy}>
              {busy ? <Loader2 className="spin" size={14} /> : <Check size={14} />} Verificar y guardar
            </button>
            <button className="store-integration-button secondary" type="button" onClick={() => { setShowForm(false); setConsumerKey(""); setConsumerSecret(""); }}>Cancelar</button>
          </div>
        </form>
      )}
      {status?.connected && (
        <>
          <div className="store-integration-actions" style={{ flexWrap: "wrap" }}>
            {canWrite && <button type="button" className="store-integration-button secondary" disabled={busy} onClick={() => void onTest()}>Probar conexión</button>}
            <button type="button" className="store-integration-button secondary" disabled={busy} onClick={() => void onPreview("products")}><ShoppingBag size={14} /> Ver productos</button>
            <button type="button" className="store-integration-button secondary" disabled={busy} onClick={() => void onPreview("orders")}>Ver pedidos</button>
            {canWrite && <button type="button" className="store-integration-button danger" disabled={busy} onClick={() => void onDisconnect()}><Trash2 size={14} /> Desconectar</button>}
          </div>
          {preview && (
            <div className="store-integration-detail" aria-live="polite">
              <strong>{preview.resource === "products" ? "Productos" : "Pedidos"} · {preview.total_returned} resultados (solo lectura)</strong>
              {preview.items.length === 0 ? <p>No hay registros.</p> : (
                <ul>
                  {preview.items.map((item, index) => (
                    <li key={String(item.id ?? index)}>
                      {preview.resource === "products"
                        ? `${item.name ?? "Producto"} · SKU ${item.sku ?? "—"} · ${item.stock_status ?? "Sin stock verificado"}`
                        : `#${item.number ?? item.id} · ${item.status ?? "—"} · ${item.total ?? "—"} ${item.currency ?? ""}`}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
