import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import {
  Check,
  ChevronDown,
  ChevronUp,
  Loader2,
  Link2,
  Package,
  Plug,
  RefreshCw,
  Search,
  Trash2,
  Truck,
  Warehouse,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  configureCJAutoFulfillment,
  connectCJ,
  deleteCJVariantMapping,
  disconnectCJ,
  enableCJTrackingWebhook,
  getCJStatus,
  getCJStock,
  getCJVariantMappings,
  getCJVariants,
  quoteCJFreight,
  retryCJAutoFulfillment,
  saveCJVariantMapping,
  searchCJProducts,
  testCJConnection,
  type CJConnectionStatus,
  type CJFreightQuote,
  type CJProduct,
  type CJStockResult,
  type CJVariant,
  type CJVariantMapping,
} from "../services/suppliers";
import { reauthorizeShopify } from "../services/integrations";
import "../cj-integration.css";

interface CJIntegrationCardProps {
  storeId: number;
  storeCountryCode?: string | null;
  canWrite: boolean;
}

type LocaleKey = "es" | "en" | "pt-BR";

const COPY = {
  es: {
    description: "Conecta CJ Dropshipping para consultar catálogo, stock, fletes y preparar pedidos del proveedor.",
    connected: "Conectado",
    disconnected: "Sin conectar",
    apiKey: "API Key de CJ",
    connect: "Conectar",
    disconnect: "Desconectar",
    test: "Probar conexión",
    catalog: "Catálogo CJ",
    hideCatalog: "Ocultar catálogo",
    tracking: "Activar tracking",
    trackingOk: "Webhook logístico configurado.",
    testOk: "Conexión CJ verificada.",
    connectedOk: "CJ Dropshipping conectado.",
    disconnectedOk: "CJ Dropshipping desconectado.",
    searchPlaceholder: "Buscar producto en CJ...",
    search: "Buscar",
    noProducts: "No se encontraron productos.",
    variants: "Variantes",
    stock: "Stock",
    quote: "Cotizar flete",
    origin: "Origen",
    destination: "Destino",
    quantity: "Cantidad",
    quoteAction: "Calcular flete",
    selectVariant: "Selecciona una variante para consultar stock o flete.",
    account: "Cuenta",
    expires: "Token expira",
    error: "No se pudo completar la operación con CJ.",
    stockTotal: "Inventario total",
    warehouses: "almacenes",
    freightEmpty: "CJ no devolvió opciones de envío para esta combinación.",
    mappingTitle: "Vincular productos",
    mappingDescription: "Elige una variante de Shopify y asígnale la variante CJ que la abastece.",
    shopifyVariant: "Variante Shopify",
    selectStoreVariant: "Selecciona una variante de Shopify",
    mapSelected: "Vincular variante CJ seleccionada",
    unmap: "Quitar vínculo",
    mappingSaved: "Vínculo Shopify ↔ CJ guardado.",
    mappingRemoved: "Vínculo eliminado.",
    mapped: "vinculadas",
    unmapped: "sin vincular",
    noStoreVariants: "Sin variantes Shopify sincronizadas. Sincroniza primero el catálogo de la tienda.",
    autoTitle: "Fulfillment automático",
    autoDescription: "Cuando un pedido Shopify esté pagado y completamente vinculado, Diaglob cotizará el envío y creará la orden en CJ automáticamente.",
    autoOn: "Automático activo",
    autoOff: "Automático apagado",
    enableAuto: "Activar automático",
    disableAuto: "Desactivar automático",
    retryAuto: "Reintentar pendientes",
    reauthorizeShopify: "Actualizar permisos Shopify",
    autoSaved: "Configuración de fulfillment automático actualizada.",
    autoRetried: "Pedidos pendientes encolados nuevamente.",
    originCountry: "País origen",
    notifyCustomer: "Notificar al cliente al crear fulfillment",
  },
  en: {
    description: "Connect CJ Dropshipping to browse catalog, stock, freight and prepare supplier orders.",
    connected: "Connected",
    disconnected: "Not connected",
    apiKey: "CJ API Key",
    connect: "Connect",
    disconnect: "Disconnect",
    test: "Test connection",
    catalog: "CJ catalog",
    hideCatalog: "Hide catalog",
    tracking: "Enable tracking",
    trackingOk: "Logistics webhook configured.",
    testOk: "CJ connection verified.",
    connectedOk: "CJ Dropshipping connected.",
    disconnectedOk: "CJ Dropshipping disconnected.",
    searchPlaceholder: "Search CJ products...",
    search: "Search",
    noProducts: "No products found.",
    variants: "Variants",
    stock: "Stock",
    quote: "Quote freight",
    origin: "Origin",
    destination: "Destination",
    quantity: "Quantity",
    quoteAction: "Calculate freight",
    selectVariant: "Select a variant to check stock or freight.",
    account: "Account",
    expires: "Token expires",
    error: "The CJ operation could not be completed.",
    stockTotal: "Total inventory",
    warehouses: "warehouses",
    freightEmpty: "CJ returned no shipping options for this combination.",
    mappingTitle: "Product mapping",
    mappingDescription: "Choose a Shopify variant and assign the CJ variant that supplies it.",
    shopifyVariant: "Shopify variant",
    selectStoreVariant: "Select a Shopify variant",
    mapSelected: "Map selected CJ variant",
    unmap: "Remove mapping",
    mappingSaved: "Shopify ↔ CJ mapping saved.",
    mappingRemoved: "Mapping removed.",
    mapped: "mapped",
    unmapped: "unmapped",
    noStoreVariants: "No synchronized Shopify variants. Sync the store catalog first.",
    autoTitle: "Automatic fulfillment",
    autoDescription: "When a Shopify order is paid and fully mapped, Diaglob will quote shipping and create the CJ order automatically.",
    autoOn: "Automation on",
    autoOff: "Automation off",
    enableAuto: "Enable automation",
    disableAuto: "Disable automation",
    retryAuto: "Retry pending",
    reauthorizeShopify: "Update Shopify permissions",
    autoSaved: "Automatic fulfillment settings updated.",
    autoRetried: "Pending orders queued again.",
    originCountry: "Origin country",
    notifyCustomer: "Notify customer when fulfillment is created",
  },
  "pt-BR": {
    description: "Conecte a CJ Dropshipping para consultar catálogo, estoque, frete e preparar pedidos do fornecedor.",
    connected: "Conectado",
    disconnected: "Não conectado",
    apiKey: "API Key da CJ",
    connect: "Conectar",
    disconnect: "Desconectar",
    test: "Testar conexão",
    catalog: "Catálogo CJ",
    hideCatalog: "Ocultar catálogo",
    tracking: "Ativar tracking",
    trackingOk: "Webhook logístico configurado.",
    testOk: "Conexão CJ verificada.",
    connectedOk: "CJ Dropshipping conectada.",
    disconnectedOk: "CJ Dropshipping desconectada.",
    searchPlaceholder: "Buscar produto na CJ...",
    search: "Buscar",
    noProducts: "Nenhum produto encontrado.",
    variants: "Variantes",
    stock: "Estoque",
    quote: "Calcular frete",
    origin: "Origem",
    destination: "Destino",
    quantity: "Quantidade",
    quoteAction: "Calcular frete",
    selectVariant: "Selecione uma variante para consultar estoque ou frete.",
    account: "Conta",
    expires: "Token expira",
    error: "Não foi possível concluir a operação com a CJ.",
    stockTotal: "Estoque total",
    warehouses: "armazéns",
    freightEmpty: "A CJ não retornou opções de envio para esta combinação.",
    mappingTitle: "Vincular produtos",
    mappingDescription: "Escolha uma variante da Shopify e associe a variante CJ que a abastece.",
    shopifyVariant: "Variante Shopify",
    selectStoreVariant: "Selecione uma variante da Shopify",
    mapSelected: "Vincular variante CJ selecionada",
    unmap: "Remover vínculo",
    mappingSaved: "Vínculo Shopify ↔ CJ salvo.",
    mappingRemoved: "Vínculo removido.",
    mapped: "vinculadas",
    unmapped: "sem vínculo",
    noStoreVariants: "Nenhuma variante Shopify sincronizada. Sincronize primeiro o catálogo da loja.",
    autoTitle: "Fulfillment automático",
    autoDescription: "Quando um pedido Shopify estiver pago e totalmente vinculado, a Diaglob cotará o frete e criará o pedido na CJ automaticamente.",
    autoOn: "Automático ativo",
    autoOff: "Automático desligado",
    enableAuto: "Ativar automático",
    disableAuto: "Desativar automático",
    retryAuto: "Tentar pendentes novamente",
    reauthorizeShopify: "Atualizar permissões Shopify",
    autoSaved: "Configuração de fulfillment automático atualizada.",
    autoRetried: "Pedidos pendentes enfileirados novamente.",
    originCountry: "País de origem",
    notifyCustomer: "Notificar cliente ao criar fulfillment",
  },
} as const;

function localeKey(language: string): LocaleKey {
  if (language.toLowerCase().startsWith("pt")) return "pt-BR";
  if (language.toLowerCase().startsWith("en")) return "en";
  return "es";
}

function errorMessage(error: unknown, fallback: string) {
  const value = error as {
    response?: { data?: { detail?: string | { message?: string } } };
    message?: string;
  };
  const detail = value.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && detail.message) return detail.message;
  return value.message || fallback;
}

function money(value: string | number | null) {
  if (value === null || value === "") return "—";
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `USD ${numeric.toFixed(2)}` : `USD ${value}`;
}

export default function CJIntegrationCard({
  storeId,
  storeCountryCode,
  canWrite,
}: CJIntegrationCardProps) {
  const { i18n } = useTranslation();
  const copy = COPY[localeKey(i18n.resolvedLanguage || i18n.language || "es")];

  const [status, setStatus] = useState<CJConnectionStatus | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [products, setProducts] = useState<CJProduct[]>([]);
  const [selectedProduct, setSelectedProduct] = useState<CJProduct | null>(null);
  const [variants, setVariants] = useState<CJVariant[]>([]);
  const [selectedVariant, setSelectedVariant] = useState<CJVariant | null>(null);
  const [stock, setStock] = useState<CJStockResult | null>(null);
  const [freight, setFreight] = useState<CJFreightQuote | null>(null);
  const [origin, setOrigin] = useState("CN");
  const [destination, setDestination] = useState((storeCountryCode || "US").toUpperCase());
  const [quantity, setQuantity] = useState(1);
  const [mappings, setMappings] = useState<CJVariantMapping[]>([]);
  const [mappingVariantId, setMappingVariantId] = useState<number | "">("");
  const [autoOrigin, setAutoOrigin] = useState("CN");
  const [autoNotifyCustomer, setAutoNotifyCustomer] = useState(true);

  useEffect(() => {
    setDestination((storeCountryCode || "US").toUpperCase());
  }, [storeCountryCode]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const result = await getCJStatus(storeId);
        if (!cancelled) setStatus(result);
      } catch (err) {
        if (!cancelled) setError(errorMessage(err, copy.error));
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [storeId, copy.error]);

  const connected = status?.connected === true;
  const autoEnabled = status?.auto_fulfillment_enabled === true;

  useEffect(() => {
    if (!status) return;
    setAutoOrigin((status.auto_origin_country_code || "CN").toUpperCase());
    setAutoNotifyCustomer(status.auto_notify_customer !== false);
  }, [status]);

  useEffect(() => {
    if (!connected) {
      setMappings([]);
      setMappingVariantId("");
      return;
    }

    let cancelled = false;
    getCJVariantMappings(storeId)
      .then((result) => {
        if (cancelled) return;
        setMappings(result.items);
        setMappingVariantId((current) => {
          if (current && result.items.some((item) => item.product_variant_id === current)) {
            return current;
          }
          return (
            result.items.find((item) => !item.mapped)?.product_variant_id
            || result.items[0]?.product_variant_id
            || ""
          );
        });
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err, copy.error));
      });

    return () => { cancelled = true; };
  }, [connected, storeId, copy.error]);

  const accountLabel = useMemo(
    () => status?.external_account_name || status?.external_account_id || "CJ Dropshipping",
    [status],
  );

  const selectedMapping = useMemo(
    () => mappings.find((item) => item.product_variant_id === mappingVariantId) || null,
    [mappings, mappingVariantId],
  );

  const mappedCount = useMemo(
    () => mappings.filter((item) => item.mapped).length,
    [mappings],
  );

  async function reloadMappings() {
    const result = await getCJVariantMappings(storeId);
    setMappings(result.items);
    return result;
  }

  async function reloadStatus() {
    const result = await getCJStatus(storeId);
    setStatus(result);
  }

  async function handleConnect(event: FormEvent) {
    event.preventDefault();
    if (!apiKey.trim()) return;
    setBusy("connect");
    setError("");
    setMessage("");
    try {
      await connectCJ(storeId, apiKey.trim());
      setApiKey("");
      await reloadStatus();
      setMessage(copy.connectedOk);
    } catch (err) {
      setError(errorMessage(err, copy.error));
    } finally {
      setBusy("");
    }
  }

  async function handleTest() {
    setBusy("test");
    setError("");
    setMessage("");
    try {
      await testCJConnection(storeId);
      await reloadStatus();
      setMessage(copy.testOk);
    } catch (err) {
      setError(errorMessage(err, copy.error));
    } finally {
      setBusy("");
    }
  }

  async function handleDisconnect() {
    setBusy("disconnect");
    setError("");
    setMessage("");
    try {
      await disconnectCJ(storeId);
      setProducts([]);
      setVariants([]);
      setSelectedProduct(null);
      setSelectedVariant(null);
      setStock(null);
      setFreight(null);
      setMappings([]);
      setMappingVariantId("");
      setCatalogOpen(false);
      await reloadStatus();
      setMessage(copy.disconnectedOk);
    } catch (err) {
      setError(errorMessage(err, copy.error));
    } finally {
      setBusy("");
    }
  }

  async function handleAutoToggle() {
    setBusy("auto");
    setError("");
    setMessage("");
    try {
      await configureCJAutoFulfillment(storeId, {
        enabled: !autoEnabled,
        origin_country_code: autoOrigin.trim().toUpperCase(),
        notify_customer: autoNotifyCustomer,
      });
      await reloadStatus();
      setMessage(copy.autoSaved);
    } catch (err) {
      setError(errorMessage(err, copy.error));
    } finally {
      setBusy("");
    }
  }

  async function handleAutoRetry() {
    setBusy("auto-retry");
    setError("");
    setMessage("");
    try {
      await retryCJAutoFulfillment(storeId);
      setMessage(copy.autoRetried);
    } catch (err) {
      setError(errorMessage(err, copy.error));
    } finally {
      setBusy("");
    }
  }

  async function handleShopifyReauthorize() {
    setBusy("shopify-reauth");
    setError("");
    setMessage("");
    try {
      const result = await reauthorizeShopify(storeId);
      window.location.href = result.authorization_url;
    } catch (err) {
      setError(errorMessage(err, copy.error));
      setBusy("");
    }
  }

  async function handleTracking() {
    setBusy("tracking");
    setError("");
    setMessage("");
    try {
      await enableCJTrackingWebhook(storeId);
      setMessage(copy.trackingOk);
    } catch (err) {
      setError(errorMessage(err, copy.error));
    } finally {
      setBusy("");
    }
  }

  async function handleSearch(event: FormEvent) {
    event.preventDefault();
    setBusy("search");
    setError("");
    try {
      const result = await searchCJProducts(storeId, query);
      setProducts(result.items);
      setSelectedProduct(null);
      setSelectedVariant(null);
      setVariants([]);
      setStock(null);
      setFreight(null);
    } catch (err) {
      setError(errorMessage(err, copy.error));
    } finally {
      setBusy("");
    }
  }

  async function selectProduct(product: CJProduct) {
    setSelectedProduct(product);
    setSelectedVariant(null);
    setStock(null);
    setFreight(null);
    setBusy("variants");
    setError("");
    try {
      const result = await getCJVariants(
        storeId,
        product.external_product_id,
        destination,
      );
      setVariants(result.items);
    } catch (err) {
      setError(errorMessage(err, copy.error));
      setVariants([]);
    } finally {
      setBusy("");
    }
  }

  async function handleStock(variant: CJVariant) {
    setSelectedVariant(variant);
    setFreight(null);
    setBusy("stock");
    setError("");
    try {
      setStock(await getCJStock(storeId, variant.external_variant_id));
    } catch (err) {
      setError(errorMessage(err, copy.error));
      setStock(null);
    } finally {
      setBusy("");
    }
  }

  async function handleFreight(event: FormEvent) {
    event.preventDefault();
    if (!selectedVariant) return;
    setBusy("freight");
    setError("");
    try {
      const result = await quoteCJFreight(storeId, {
        start_country_code: origin.trim().toUpperCase(),
        end_country_code: destination.trim().toUpperCase(),
        items: [{
          variant_id: selectedVariant.external_variant_id,
          quantity,
        }],
      });
      setFreight(result);
    } catch (err) {
      setError(errorMessage(err, copy.error));
      setFreight(null);
    } finally {
      setBusy("");
    }
  }

  async function handleSaveMapping() {
    if (!canWrite || !mappingVariantId || !selectedProduct || !selectedVariant) return;
    setBusy("mapping-save");
    setError("");
    setMessage("");
    try {
      await saveCJVariantMapping(storeId, Number(mappingVariantId), {
        external_product_id: selectedProduct.external_product_id,
        external_variant_id: selectedVariant.external_variant_id,
        external_sku: selectedVariant.sku,
        active: true,
      });
      await reloadMappings();
      setMessage(copy.mappingSaved);
    } catch (err) {
      setError(errorMessage(err, copy.error));
    } finally {
      setBusy("");
    }
  }

  async function handleDeleteMapping() {
    if (!canWrite || !mappingVariantId || !selectedMapping?.mapped) return;
    setBusy("mapping-delete");
    setError("");
    setMessage("");
    try {
      await deleteCJVariantMapping(storeId, Number(mappingVariantId));
      const result = await reloadMappings();
      const next = result.items.find((item) => !item.mapped) || result.items[0];
      setMappingVariantId(next?.product_variant_id || "");
      setMessage(copy.mappingRemoved);
    } catch (err) {
      setError(errorMessage(err, copy.error));
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="store-integration-block cj-integration">
      <div className="store-integration-header">
        <div className="store-integration-title">
          <Package size={17} />
          <strong>CJ Dropshipping</strong>
          <span className={connected ? "integration-status connected" : "integration-status disconnected"}>
            {connected ? copy.connected : copy.disconnected}
          </span>
        </div>
      </div>

      <div className="store-integration-detail cj-description">{copy.description}</div>

      {connected && (
        <div className="cj-account-meta">
          <span><strong>{copy.account}:</strong> {accountLabel}</span>
          {status?.access_token_expires_at && (
            <span>
              <strong>{copy.expires}:</strong>{" "}
              {new Date(status.access_token_expires_at).toLocaleString()}
            </span>
          )}
        </div>
      )}

      {connected && (
        <section className="cj-auto-panel">
          <div className="cj-section-heading">
            <div><Truck size={15} /><strong>{copy.autoTitle}</strong></div>
            <span className={autoEnabled ? "cj-auto-state on" : "cj-auto-state"}>
              {autoEnabled ? copy.autoOn : copy.autoOff}
            </span>
          </div>
          <p>{copy.autoDescription}</p>
          <div className="cj-auto-controls">
            <label>
              <span>{copy.originCountry}</span>
              <input
                value={autoOrigin}
                maxLength={2}
                disabled={autoEnabled}
                onChange={(event) => setAutoOrigin(event.target.value.toUpperCase())}
              />
            </label>
            <label className="cj-auto-checkbox">
              <input
                type="checkbox"
                checked={autoNotifyCustomer}
                disabled={autoEnabled}
                onChange={(event) => setAutoNotifyCustomer(event.target.checked)}
              />
              <span>{copy.notifyCustomer}</span>
            </label>
            {canWrite && (
              <button
                type="button"
                className={autoEnabled ? "store-integration-button danger" : "store-integration-button primary"}
                onClick={() => void handleAutoToggle()}
                disabled={busy === "auto" || autoOrigin.trim().length !== 2}
              >
                {busy === "auto" ? <Loader2 className="spin" size={14} /> : <Truck size={14} />}
                {autoEnabled ? copy.disableAuto : copy.enableAuto}
              </button>
            )}
            {canWrite && (
              <button
                type="button"
                className="store-integration-button secondary"
                onClick={() => void handleAutoRetry()}
                disabled={busy === "auto-retry" || !autoEnabled}
              >
                {busy === "auto-retry" ? <Loader2 className="spin" size={14} /> : <RefreshCw size={14} />}
                {copy.retryAuto}
              </button>
            )}
            {canWrite && (
              <button
                type="button"
                className="store-integration-button secondary"
                onClick={() => void handleShopifyReauthorize()}
                disabled={busy === "shopify-reauth"}
              >
                {busy === "shopify-reauth" ? <Loader2 className="spin" size={14} /> : <RefreshCw size={14} />}
                {copy.reauthorizeShopify}
              </button>
            )}
          </div>
        </section>
      )}

      {error && <div className="store-integration-test-result error">{error}</div>}
      {message && <div className="store-integration-test-result ok"><Check size={14} /> {message}</div>}

      {!connected && canWrite && (
        <form className="cj-connect-form" onSubmit={handleConnect}>
          <input
            type="password"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder={copy.apiKey}
            autoComplete="off"
          />
          <button
            type="submit"
            className="store-integration-button primary"
            disabled={!apiKey.trim() || busy === "connect"}
          >
            {busy === "connect" ? <Loader2 className="spin" size={15} /> : <Plug size={15} />}
            {copy.connect}
          </button>
        </form>
      )}

      {connected && (
        <>
          <div className="store-integration-actions cj-actions">
            <button
              type="button"
              className="store-integration-button secondary"
              onClick={handleTest}
              disabled={busy === "test"}
            >
              {busy === "test" ? <Loader2 className="spin" size={14} /> : <RefreshCw size={14} />}
              {copy.test}
            </button>
            <button
              type="button"
              className="store-integration-button secondary"
              onClick={() => setCatalogOpen((value) => !value)}
            >
              <Package size={14} />
              {catalogOpen ? copy.hideCatalog : copy.catalog}
              {catalogOpen ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
            </button>
            {canWrite && (
              <button
                type="button"
                className="store-integration-button secondary"
                onClick={handleTracking}
                disabled={busy === "tracking"}
              >
                {busy === "tracking" ? <Loader2 className="spin" size={14} /> : <Truck size={14} />}
                {copy.tracking}
              </button>
            )}
            {canWrite && (
              <button
                type="button"
                className="store-integration-button danger"
                onClick={handleDisconnect}
                disabled={busy === "disconnect"}
              >
                {busy === "disconnect" ? <Loader2 className="spin" size={14} /> : <Trash2 size={14} />}
                {copy.disconnect}
              </button>
            )}
          </div>

          {catalogOpen && (
            <div className="cj-catalog">
              <section className="cj-mapping-panel">
                <div className="cj-section-heading">
                  <div><Link2 size={15} /><strong>{copy.mappingTitle}</strong></div>
                  <span>{mappedCount}/{mappings.length} {copy.mapped}</span>
                </div>
                <p>{copy.mappingDescription}</p>

                {mappings.length === 0 ? (
                  <div className="cj-empty">{copy.noStoreVariants}</div>
                ) : (
                  <div className="cj-mapping-controls">
                    <label>
                      <span>{copy.shopifyVariant}</span>
                      <select
                        value={mappingVariantId}
                        onChange={(event) => setMappingVariantId(Number(event.target.value))}
                      >
                        <option value="" disabled>{copy.selectStoreVariant}</option>
                        {mappings.map((mapping) => (
                          <option key={mapping.product_variant_id} value={mapping.product_variant_id}>
                            {mapping.product_title} · {mapping.variant_title}
                            {mapping.sku ? ` · ${mapping.sku}` : ""}
                            {mapping.mapped ? " ✓" : ""}
                          </option>
                        ))}
                      </select>
                    </label>

                    <div className="cj-mapping-current">
                      {selectedMapping?.mapped ? (
                        <>
                          <span>
                            <strong>{selectedMapping.external_sku || selectedMapping.external_variant_id}</strong>
                            <small>CJ · {selectedMapping.external_variant_id}</small>
                          </span>
                          {canWrite && (
                            <button
                              type="button"
                              className="cj-unmap-button"
                              onClick={() => void handleDeleteMapping()}
                              disabled={busy === "mapping-delete"}
                            >
                              {busy === "mapping-delete" ? <Loader2 className="spin" size={13} /> : <Trash2 size={13} />}
                              {copy.unmap}
                            </button>
                          )}
                        </>
                      ) : (
                        <span><small>{copy.unmapped}</small></span>
                      )}
                    </div>

                    {canWrite && (
                      <button
                        type="button"
                        className="cj-map-button"
                        onClick={() => void handleSaveMapping()}
                        disabled={
                          !mappingVariantId
                          || !selectedProduct
                          || !selectedVariant
                          || busy === "mapping-save"
                        }
                      >
                        {busy === "mapping-save" ? <Loader2 className="spin" size={14} /> : <Link2 size={14} />}
                        {copy.mapSelected}
                      </button>
                    )}
                  </div>
                )}
              </section>

              <form className="cj-search" onSubmit={handleSearch}>
                <Search size={15} />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder={copy.searchPlaceholder}
                />
                <button type="submit" disabled={busy === "search"}>
                  {busy === "search" ? <Loader2 className="spin" size={14} /> : copy.search}
                </button>
              </form>

              {products.length === 0 && query && busy !== "search" && (
                <div className="cj-empty">{copy.noProducts}</div>
              )}

              {products.length > 0 && (
                <div className="cj-products-grid">
                  {products.map((product) => (
                    <button
                      type="button"
                      key={product.external_product_id}
                      className={selectedProduct?.external_product_id === product.external_product_id ? "cj-product active" : "cj-product"}
                      onClick={() => void selectProduct(product)}
                    >
                      {product.image_url ? <img src={product.image_url} alt="" /> : <div className="cj-product-placeholder"><Package size={18} /></div>}
                      <span>
                        <strong>{product.title || product.sku || product.external_product_id}</strong>
                        <small>{money(product.supplier_cost_usd)}</small>
                      </span>
                    </button>
                  ))}
                </div>
              )}

              {selectedProduct && (
                <div className="cj-variants">
                  <div className="cj-section-heading">
                    <div>
                      <span>CJ</span>
                      <strong>{copy.variants}</strong>
                    </div>
                    {busy === "variants" && <Loader2 className="spin" size={15} />}
                  </div>
                  {variants.map((variant) => (
                    <button
                      type="button"
                      key={variant.external_variant_id}
                      className={selectedVariant?.external_variant_id === variant.external_variant_id ? "cj-variant active" : "cj-variant"}
                      onClick={() => void handleStock(variant)}
                    >
                      <span>
                        <strong>{variant.title || variant.option || variant.sku || variant.external_variant_id}</strong>
                        <small>{variant.sku || variant.external_variant_id}</small>
                      </span>
                      <span className="cj-variant-price">{money(variant.supplier_cost_usd)}</span>
                    </button>
                  ))}
                </div>
              )}

              {selectedVariant && (
                <div className="cj-operational-grid">
                  <section className="cj-operation-card">
                    <div className="cj-section-heading">
                      <div><Warehouse size={15} /><strong>{copy.stock}</strong></div>
                      {busy === "stock" && <Loader2 className="spin" size={14} />}
                    </div>
                    {stock ? (
                      <>
                        <strong className="cj-stock-total">{stock.total_inventory}</strong>
                        <span>{copy.stockTotal} · {stock.warehouses.length} {copy.warehouses}</span>
                        <div className="cj-warehouses">
                          {stock.warehouses.slice(0, 5).map((warehouse) => (
                            <div key={warehouse.warehouse_id || warehouse.warehouse_name || String(warehouse.total_inventory)}>
                              <span>{warehouse.warehouse_name || warehouse.country_code || "CJ"}</span>
                              <strong>{warehouse.total_inventory}</strong>
                            </div>
                          ))}
                        </div>
                      </>
                    ) : (
                      <p>{copy.selectVariant}</p>
                    )}
                  </section>

                  <section className="cj-operation-card">
                    <div className="cj-section-heading">
                      <div><Truck size={15} /><strong>{copy.quote}</strong></div>
                    </div>
                    <form className="cj-freight-form" onSubmit={handleFreight}>
                      <label>
                        <span>{copy.origin}</span>
                        <input value={origin} maxLength={2} onChange={(e) => setOrigin(e.target.value.toUpperCase())} />
                      </label>
                      <label>
                        <span>{copy.destination}</span>
                        <input value={destination} maxLength={2} onChange={(e) => setDestination(e.target.value.toUpperCase())} />
                      </label>
                      <label>
                        <span>{copy.quantity}</span>
                        <input type="number" min={1} max={1000} value={quantity} onChange={(e) => setQuantity(Math.max(1, Number(e.target.value) || 1))} />
                      </label>
                      <button type="submit" disabled={busy === "freight" || origin.length !== 2 || destination.length !== 2}>
                        {busy === "freight" ? <Loader2 className="spin" size={14} /> : copy.quoteAction}
                      </button>
                    </form>

                    {freight && (
                      <div className="cj-freight-options">
                        {freight.options.length === 0 ? (
                          <p>{copy.freightEmpty}</p>
                        ) : (
                          freight.options.slice(0, 8).map((option, index) => (
                            <div key={`${option.logistics_name || "option"}-${index}`}>
                              <span>
                                <strong>{option.logistics_name || "CJ Logistics"}</strong>
                                <small>{option.transit_time || "—"}</small>
                              </span>
                              <strong>{money(option.price_usd)}</strong>
                            </div>
                          ))
                        )}
                      </div>
                    )}
                  </section>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
