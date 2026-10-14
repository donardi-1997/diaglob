import { useEffect, useState } from "react";
import {
  searchDropiCatalog,
  type DropiCatalogPage,
  type DropiCatalogProduct,
} from "../services/integrations";

function ProductRow({ product }: { product: DropiCatalogProduct }) {
  const difference = product.differences_detected;
  return (
    <li style={{ padding: "12px 0", borderBottom: "1px solid var(--border-color, #ddd)" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
        <strong>{product.name || "Producto sin nombre"}</strong>
        <span style={{ fontSize: "0.75rem" }}>#{product.id || "?"}</span>
        <span className={product.mapping_status === "linked" ? "integration-status connected" : "integration-status disconnected"}>
          {product.mapping_status === "linked" ? "Vinculado" : "Sin vincular"}
        </span>
        {difference && <span role="status" style={{ fontSize: "0.78rem" }}>Diferencias detectadas</span>}
      </div>
      <p style={{ marginTop: 4, fontSize: "0.78rem" }}>
        SKU: {product.sku || "No informado"} · Tipo: {product.type || "No informado"} ·
        Stock: {product.stock ?? "Sin dato"}
      </p>
      {product.shopify_mappings.length > 0 && (
        <div style={{ fontSize: "0.78rem" }}>
          {product.shopify_mappings.map(mapping => (
            <p key={mapping.product_variant_id} style={{ marginTop: 4 }}>
              Shopify: {mapping.shopify_product_title} / {mapping.shopify_sku || "Sin SKU"}
              {" → "}Dropi variante #{mapping.dropi_variant_id}
              {mapping.sku_check === "different" && " · SKU diferente"}
              {mapping.stock_check === "different" && " · Stock diferente"}
              {mapping.sku_check === "unknown" && " · SKU sin verificar"}
            </p>
          ))}
        </div>
      )}
      {product.variants_in_page && (
        <p style={{ fontSize: "0.78rem", marginTop: 4 }}>
          Variantes informadas: {product.variants.length}
          {product.variants_truncated ? " (vista limitada a 30)" : ""}
        </p>
      )}
      {!product.variants_in_page && (
        <p style={{ fontSize: "0.75rem", marginTop: 4 }}>
          El listado no incluyó variantes; puedes inspeccionarlas individualmente.
        </p>
      )}
    </li>
  );
}

export default function DropiCatalogExplorer({ storeId }: { storeId: number }) {
  const [expanded, setExpanded] = useState(false);
  const [searchInput, setSearchInput] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [page, setPage] = useState(1);
  const [catalog, setCatalog] = useState<DropiCatalogPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!expanded) return;
    let active = true;
    setLoading(true);
    setError("");
    searchDropiCatalog(storeId, page, appliedQuery)
      .then(response => { if (active) setCatalog(response); })
      .catch(() => {
        if (active) {
          setCatalog(null);
          setError("No se pudo consultar esta página de Dropi. Comprueba la conexión y el token.");
        }
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [storeId, page, appliedQuery, expanded]);

  return (
    <div className="store-integration-detail">
      <details
        open={expanded}
        onToggle={event => setExpanded(event.currentTarget.open)}
      >
        <summary style={{ cursor: "pointer", fontWeight: 600 }}>
          Explorar catálogo Dropi · solo lectura
        </summary>
        <p style={{ fontSize: "0.78rem", marginTop: 8 }}>
          Busca productos, navega páginas y revisa qué variantes están vinculadas a Shopify.
          No importa, publica ni modifica productos. El total de páginas no está disponible.
        </p>
        <form
          onSubmit={event => {
            event.preventDefault();
            const query = searchInput.trim();
            if (query === appliedQuery && page === 1) return;
            setCatalog(null);
            setPage(1);
            setAppliedQuery(query);
          }}
          style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 8 }}
        >
          <input
            aria-label="Buscar productos en Dropi"
            placeholder="Buscar nombre o SKU"
            value={searchInput}
            maxLength={100}
            onChange={event => setSearchInput(event.target.value)}
            style={{ flex: 1, minWidth: 145 }}
          />
          <button
            type="submit"
            className="store-integration-button secondary"
            disabled={loading}
          >
            Buscar
          </button>
        </form>
        {loading && <p role="status">Consultando catálogo…</p>}
        {error && <p role="alert" className="stores-alert error">{error}</p>}
        {catalog && (
          <>
            <p style={{ fontSize: "0.78rem" }}>
              Página {catalog.page} · {catalog.returned} productos en esta página ·
              Sin vincular: {catalog.unmapped_products} · Con diferencias: {catalog.products_with_differences}
            </p>
            {catalog.items.length === 0 && <p>No hay productos en esta página.</p>}
            <ul style={{ listStyle: "none", paddingLeft: 0 }}>
              {catalog.items.map((product, index) => (
                <ProductRow
                  key={product.id ? `${product.id}-${index}` : String(index)}
                  product={product}
                />
              ))}
            </ul>
            <div className="store-integration-actions" style={{ marginTop: 12 }}>
              <button
                type="button"
                className="store-integration-button secondary"
                disabled={loading || page <= 1}
                onClick={() => setPage(current => Math.max(1, current - 1))}
              >
                Anterior
              </button>
              <button
                type="button"
                className="store-integration-button secondary"
                disabled={loading || !catalog.has_more}
                onClick={() => setPage(current => current + 1)}
              >
                Siguiente
              </button>
            </div>
          </>
        )}
      </details>
    </div>
  );
}
