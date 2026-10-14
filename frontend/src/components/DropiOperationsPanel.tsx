import { useEffect, useState } from "react";
import {
  deleteDropiMapping,
  getDropiOrderReadiness,
  listDropiMappings,
  listShopifyOrders,
  saveDropiMapping,
  type DropiMappings,
  type DropiOrderReadiness,
  type Order,
} from "../services/integrations";

type Draft = { product: string; variant: string };

export default function DropiOperationsPanel({
  storeId,
  canWrite,
}: {
  storeId: number;
  canWrite: boolean;
}) {
  const [mappings, setMappings] = useState<DropiMappings | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [drafts, setDrafts] = useState<Record<number, Draft>>({});
  const [readiness, setReadiness] = useState<DropiOrderReadiness | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function reloadMappings() {
    const next = await listDropiMappings(storeId);
    setMappings(next);
    setDrafts(Object.fromEntries(next.items.map(item => [
      item.product_variant_id,
      { product: item.external_product_id ?? "", variant: item.external_variant_id ?? "" },
    ])));
  }

  useEffect(() => {
    let active = true;
    setMappings(null);
    setReadiness(null);
    setError("");
    setLoading(true);
    Promise.all([listDropiMappings(storeId), listShopifyOrders(storeId)])
      .then(([mappingData, orderData]) => {
        if (!active) return;
        setMappings(mappingData);
        setDrafts(Object.fromEntries(mappingData.items.map(item => [
          item.product_variant_id,
          { product: item.external_product_id ?? "", variant: item.external_variant_id ?? "" },
        ])));
        setOrders(orderData.items.slice(0, 10));
      })
      .catch(() => { if (active) setError("No se pudo cargar la información de Shopify."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [storeId]);

  async function run(action: () => Promise<void>) {
    setError("");
    setBusy(true);
    try {
      await action();
    } catch {
      setError("No se pudo completar la operación. Comprueba permisos y datos.");
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <p className="store-integration-detail">Cargando correspondencias y pedidos…</p>;

  return (
    <div className="store-integration-detail">
      <details>
        <summary style={{ cursor: "pointer", fontWeight: 600 }}>
          Productos Shopify ↔ Dropi ({mappings?.mapped ?? 0}/{mappings?.total ?? 0})
        </summary>
        <p style={{ fontSize: "0.78rem", marginTop: 8 }}>
          Asocia manualmente variantes a los IDs que devuelve Dropi.
          No inferimos IDs por SKU ni publicamos productos automáticamente.
        </p>
        {mappings?.items.slice(0, 30).map(item => {
          const draft = drafts[item.product_variant_id] ?? { product: "", variant: "" };
          const update = (field: keyof Draft, value: string) =>
            setDrafts(prev => ({
              ...prev,
              [item.product_variant_id]: { ...draft, [field]: value },
            }));
          return (
            <div className="store-integration-detail" key={item.product_variant_id} style={{ marginBottom: 8 }}>
              <div style={{ fontSize: "0.82rem" }}>
                <strong>{item.product_title}</strong> · {item.variant_title} · SKU: {item.sku || "—"}
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 6 }}>
                <input
                  aria-label={`ID de producto Dropi para ${item.product_variant_id}`}
                  placeholder="ID producto Dropi"
                  value={draft.product}
                  onChange={event => update("product", event.target.value)}
                  disabled={!canWrite || busy}
                  style={{ flex: 1, minWidth: 120 }}
                />
                <input
                  aria-label={`ID de variante Dropi para ${item.product_variant_id}`}
                  placeholder="ID variante Dropi"
                  value={draft.variant}
                  onChange={event => update("variant", event.target.value)}
                  disabled={!canWrite || busy}
                  style={{ flex: 1, minWidth: 120 }}
                />
                {canWrite && (
                  <>
                    <button
                      type="button"
                      className="store-integration-button secondary"
                      disabled={busy || !draft.product.trim() || !draft.variant.trim()}
                      onClick={() => void run(async () => {
                        await saveDropiMapping(storeId, item.product_variant_id, {
                          external_product_id: draft.product.trim(),
                          external_variant_id: draft.variant.trim(),
                        });
                        await reloadMappings();
                      })}
                    >
                      {item.mapped ? "Actualizar" : "Mapear"}
                    </button>
                    {item.mapped && (
                      <button
                        type="button"
                        className="store-integration-button danger"
                        disabled={busy}
                        onClick={() => void run(async () => {
                          await deleteDropiMapping(storeId, item.product_variant_id);
                          await reloadMappings();
                        })}
                      >
                        Quitar
                      </button>
                    )}
                  </>
                )}
              </div>
            </div>
          );
        })}
        {!mappings?.total && <p>Sin variantes importadas de Shopify.</p>}
        {(mappings?.total ?? 0) > 30 && <p>Mostrando las primeras 30 variantes.</p>}
      </details>

      <details style={{ marginTop: 12 }}>
        <summary style={{ cursor: "pointer", fontWeight: 600 }}>
          Diagnóstico de pedidos · simulación
        </summary>
        <p style={{ fontSize: "0.78rem", marginTop: 8 }}>
          Comprueba pagos, envío y mapeo sin enviar pedidos ni datos personales a Dropi.
        </p>
        {!orders.length && <p>No hay pedidos sincronizados de Shopify.</p>}
        {orders.map(order => (
          <button
            key={order.id}
            type="button"
            className="store-integration-button secondary"
            style={{ margin: 4 }}
            disabled={busy}
            onClick={() => void run(async () => {
              setReadiness(await getDropiOrderReadiness(storeId, order.id));
            })}
          >
            Revisar #{order.order_number}
          </button>
        ))}
        {readiness && (
          <div className="store-integration-detail" role="status">
            <strong>Pedido #{readiness.order_number}</strong>
            <p>{readiness.ready_for_provider_contract_test
              ? "Validaciones locales completas; aún falta la prueba real de Dropi."
              : `Bloqueos: ${readiness.blockers.join(", ")}`}</p>
            <p>Variantes mapeadas: {readiness.items.filter(x => x.mapped).length}/{readiness.items.length}</p>
            {!!readiness.missing_shipping_fields.length && (
              <p>Datos de envío faltantes: {readiness.missing_shipping_fields.join(", ")}</p>
            )}
            <p style={{ fontSize: "0.75rem" }}>
              Clave de deduplicación: {readiness.idempotency_key}
            </p>
            <strong>No se ha enviado ningún pedido.</strong>
          </div>
        )}
      </details>
      {error && <div className="stores-alert error" role="alert">{error}</div>}
    </div>
  );
}
