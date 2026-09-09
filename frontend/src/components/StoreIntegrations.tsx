import { useTranslation } from "react-i18next";
import {
  useEffect,
  useState,
} from "react";

import {
  Check,
  Copy,
  CreditCard,
  Loader2,
  MessageCircle,
  Phone,
  Plug,
  ShoppingBag,
  Trash2,
  Truck,
  Store,
} from "lucide-react";

import {
  connectNuvemshop,
  connectPayment,
  connectShopify,
  connectWhatsApp,
  disconnectNuvemshop,
  disconnectPayment,
  disconnectShopify,
  disconnectWhatsApp,
  getCommerceStatus,
  getNuvemshopStatus,
  getPaymentProviders,
  getPaymentStatus,
  getWhatsAppStatus,
  syncNuvemshopOrders,
  syncNuvemshopProducts,
  testShopifyConnection,
  syncShopifyProducts,
  type CommerceConnectionStatus,
  type NuvemshopConnectionStatus,
  type PaymentConnectionStatus,
  type PaymentProviderInfo,
  type WhatsAppConnectionStatus,
  type ShopifyTestResult,
  type ShopifySyncResult,
} from "../services/integrations";

import ShopifyOrders from "./ShopifyOrders";


interface StoreIntegrationsProps {
  storeId: number;
  shopDomain: string | null;
  canWrite: boolean;
}


export default function StoreIntegrations({
  storeId,
  shopDomain,
  canWrite,
}: StoreIntegrationsProps) {
  const { t } = useTranslation();

  const [commerce, setCommerce] =
    useState<CommerceConnectionStatus | null>(null);

  const [nuvemshop, setNuvemshop] =
    useState<NuvemshopConnectionStatus | null>(null);

  const [whatsapp, setWhatsApp] =
    useState<WhatsAppConnectionStatus | null>(null);

  const [nequiProviders, setNequiProviders] =
    useState<PaymentProviderInfo[]>([]);

  const [nequi, setNequi] =
    useState<PaymentConnectionStatus | null>(null);

  const [nequiClientId, setNequiClientId] =
    useState("");

  const [nequiClientSecret, setNequiClientSecret] =
    useState("");

  const [nequiWebhookSecret, setNequiWebhookSecret] =
    useState("");

  const [nequiEnvironment, setNequiEnvironment] =
    useState<"sandbox" | "production">("sandbox");

  const [connectingNequi, setConnectingNequi] =
    useState(false);

  const [disconnectingNequi, setDisconnectingNequi] =
    useState(false);

  const [showNequiForm, setShowNequiForm] =
    useState(false);

  const [loading, setLoading] =
    useState(true);

  const [whatsappPhoneId, setWhatsAppPhoneId] =
    useState("");

  const [whatsappBizId, setWhatsAppBizId] =
    useState("");

  const [whatsappToken, setWhatsAppToken] =
    useState("");

  const [connectingShopify, setConnectingShopify] =
    useState(false);

  const [disconnectingShopify, setDisconnectingShopify] =
    useState(false);

  const [connectingWhatsApp, setConnectingWhatsApp] =
    useState(false);

  const [disconnectingWhatsApp, setDisconnectingWhatsApp] =
    useState(false);

  const [testingShopify, setTestingShopify] =
    useState(false);

  const [syncingShopify, setSyncingShopify] =
    useState(false);

  const [connectingNuvemshop, setConnectingNuvemshop] =
    useState(false);

  const [disconnectingNuvemshop, setDisconnectingNuvemshop] =
    useState(false);

  const [syncingNuvemshopProducts, setSyncingNuvemshopProducts] =
    useState(false);

  const [syncingNuvemshopOrders, setSyncingNuvemshopOrders] =
    useState(false);

  const [nuvemshopSyncResult, setNuvemshopSyncResult] =
    useState<{ ok: boolean; fetched: number; created: number; updated: number; failed: number } | null>(null);

  const [shopifyTestResult, setShopifyTestResult] =
    useState<ShopifyTestResult | null>(null);

  const [shopifySyncResult, setShopifySyncResult] =
    useState<ShopifySyncResult | null>(null);

  const [whatsappCopied, setWhatsAppCopied] =
    useState(false);

  const [error, setError] =
    useState("");

  const [success, setSuccess] =
    useState("");


  async function load() {
    try {
      setLoading(true);
      setError("");

      const [
        commerceData,
        nuvemshopData,
        whatsappData,
      ] = await Promise.all([
        getCommerceStatus(storeId),
        getNuvemshopStatus(storeId),
        getWhatsAppStatus(storeId),
      ]);

      setCommerce(commerceData);
      setNuvemshop(nuvemshopData);
      setWhatsApp(whatsappData);

      // Load payment providers and Nequi status
      try {
        const providersData = await getPaymentProviders(storeId);
        const nequiProvider = providersData.providers.find(p => p.code === "nequi");
        setNequiProviders(nequiProvider ? [nequiProvider] : []);

        if (nequiProvider) {
          const nequiData = await getPaymentStatus(storeId, "nequi");
          setNequi(nequiData);
        }
      } catch {
        // Payment providers not available for this store
        setNequiProviders([]);
        setNequi(null);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }


  useEffect(() => {
    load();
  }, [storeId]);


  function clearMessages() {
    setError("");
    setSuccess("");
  }


  async function handleConnectShopify() {
    clearMessages();

    try {
      setConnectingShopify(true);

      const result =
        await connectShopify(
          storeId,
          shopDomain || "",
        );

      // Abre la pantalla de autorización de
      // Shopify en una pestaña nueva.
      window.open(
        result.authorization_url,
        "_blank",
        "noopener,noreferrer",
      );
    } catch (err: any) {
      console.error(err);

      setError(
        formatError(err)
        || t("integrationsShopifyConnectError"),
      );
    } finally {
      setConnectingShopify(false);
    }
  }


  async function handleDisconnectShopify() {
    clearMessages();

    try {
      setDisconnectingShopify(true);

      await disconnectShopify(storeId);

      setCommerce(null);
      setSuccess(
        t("integrationsShopifyDisconnected"),
      );

      await load();
    } catch (err: any) {
      console.error(err);

      setError(
        formatError(err)
        || t("integrationsDisconnectError"),
      );
    } finally {
      setDisconnectingShopify(false);
    }
  }


  async function handleTestShopify() {
    clearMessages();
    setShopifyTestResult(null);

    try {
      setTestingShopify(true);

      const result =
        await testShopifyConnection(storeId);

      setShopifyTestResult(result);

      if (result.connected) {
        setSuccess(
          t("integrationsShopifyTestOk"),
        );
      }
    } catch (err: any) {
      console.error(err);

      setShopifyTestResult({
        connected: false,
        shop_name: "",
        shop_domain: "",
        currency: "",
        error:
          formatError(err)
          || t("integrationsShopifyTestError"),
      });

      setError(
        formatError(err)
        || t("integrationsShopifyTestError"),
      );
    } finally {
      setTestingShopify(false);
    }
  }


  async function handleSyncShopify() {
    clearMessages();
    setShopifySyncResult(null);

    try {
      setSyncingShopify(true);

      const result =
        await syncShopifyProducts(storeId);

      setShopifySyncResult(result);

      setSuccess(
        t("integrationsShopifySyncOk"),
      );

      await load();
    } catch (err: any) {
      console.error(err);

      setShopifySyncResult({
        ok: false,
        fetched: 0,
        created: 0,
        updated: 0,
        failed: 0,
        error:
          formatError(err)
          || t("integrationsShopifySyncError"),
      });

      setError(
        formatError(err)
        || t("integrationsShopifySyncError"),
      );
    } finally {
      setSyncingShopify(false);
    }
  }


  async function handleConnectNuvemshop() {
    clearMessages();

    try {
      setConnectingNuvemshop(true);

      const result =
        await connectNuvemshop(storeId);

      window.open(
        result.authorization_url,
        "_blank",
        "noopener,noreferrer",
      );
    } catch (err: any) {
      console.error(err);

      setError(
        formatError(err)
        || t("integrationsNuvemshopConnectError"),
      );
    } finally {
      setConnectingNuvemshop(false);
    }
  }


  async function handleDisconnectNuvemshop() {
    clearMessages();

    try {
      setDisconnectingNuvemshop(true);

      await disconnectNuvemshop(storeId);

      setNuvemshop(null);
      setSuccess(
        t("integrationsNuvemshopDisconnected"),
      );

      await load();
    } catch (err: any) {
      console.error(err);

      setError(
        formatError(err)
        || t("integrationsDisconnectError"),
      );
    } finally {
      setDisconnectingNuvemshop(false);
    }
  }


  async function handleSyncNuvemshopProducts() {
    clearMessages();
    setNuvemshopSyncResult(null);

    try {
      setSyncingNuvemshopProducts(true);

      const result =
        await syncNuvemshopProducts(storeId);

      setNuvemshopSyncResult(result);

      setSuccess(
        t("integrationsNuvemshopSyncOk"),
      );

      await load();
    } catch (err: any) {
      console.error(err);

      setError(
        formatError(err)
        || t("integrationsNuvemshopSyncError"),
      );
    } finally {
      setSyncingNuvemshopProducts(false);
    }
  }


  async function handleSyncNuvemshopOrders() {
    clearMessages();
    setNuvemshopSyncResult(null);

    try {
      setSyncingNuvemshopOrders(true);

      const result =
        await syncNuvemshopOrders(storeId);

      setNuvemshopSyncResult(result);

      setSuccess(
        t("integrationsNuvemshopSyncOrdersOk"),
      );

      await load();
    } catch (err: any) {
      console.error(err);

      setError(
        formatError(err)
        || t("integrationsNuvemshopSyncError"),
      );
    } finally {
      setSyncingNuvemshopOrders(false);
    }
  }


  async function handleConnectNequi(event: React.FormEvent) {
    event.preventDefault();
    clearMessages();

    const clientId = nequiClientId.trim();
    const clientSecret = nequiClientSecret.trim();

    if (!clientId || !clientSecret) {
      setError(t("integrationsNequiFieldsRequired"));
      return;
    }

    try {
      setConnectingNequi(true);

      await connectPayment(storeId, "nequi", {
        environment: nequiEnvironment,
        client_id: clientId,
        client_secret: clientSecret,
        webhook_secret: nequiWebhookSecret.trim() || undefined,
      });

      setNequiClientId("");
      setNequiClientSecret("");
      setNequiWebhookSecret("");
      setShowNequiForm(false);
      setSuccess(t("integrationsNequiConnected"));

      await load();
    } catch (err: any) {
      console.error(err);
      setError(
        formatError(err)
        || t("integrationsNequiConnectError"),
      );
    } finally {
      setConnectingNequi(false);
    }
  }


  async function handleDisconnectNequi() {
    clearMessages();

    try {
      setDisconnectingNequi(true);

      await disconnectPayment(storeId, "nequi");

      setNequi(null);
      setSuccess(t("integrationsNequiDisconnected"));

      await load();
    } catch (err: any) {
      console.error(err);
      setError(
        formatError(err)
        || t("integrationsDisconnectError"),
      );
    } finally {
      setDisconnectingNequi(false);
    }
  }



  const WHATSAPP_WEBHOOK_URL =
    "https://api.diaglob.tech/api/webhooks/whatsapp";


  async function copyWhatsAppWebhook() {
    try {
      await navigator.clipboard.writeText(
        WHATSAPP_WEBHOOK_URL,
      );

      setWhatsAppCopied(true);

      setTimeout(
        () => setWhatsAppCopied(false),
        1800,
      );
    } catch {
      setError(
        t("integrationsCopyError"),
      );
    }
  }


  async function copyWhatsAppVerifyToken() {
    const token =
      whatsapp?.verify_token;

    if (!token) {
      return;
    }

    try {
      await navigator.clipboard.writeText(token);

      setWhatsAppCopied(true);

      setTimeout(
        () => setWhatsAppCopied(false),
        1800,
      );
    } catch {
      setError(
        t("integrationsCopyError"),
      );
    }
  }


  async function handleConnectWhatsApp(
    event: React.FormEvent,
  ) {
    event.preventDefault();

    clearMessages();

    const phoneId =
      whatsappPhoneId.trim();

    const bizId =
      whatsappBizId.trim();

    const token =
      whatsappToken.trim();

    if (!phoneId || !bizId || !token) {
      setError(
        t("integrationsWhatsAppFieldsRequired"),
      );

      return;
    }

    try {
      setConnectingWhatsApp(true);

      const result =
        await connectWhatsApp(
          storeId,
          phoneId,
          bizId,
          token,
        );

      // Limpia el token inmediatamente.
      setWhatsAppToken("");
      setWhatsAppPhoneId("");
      setWhatsAppBizId("");

      setWhatsApp({
        connected: true,
        status: "connected",
        phone_number_id:
          result.phone_number_id,
        business_account_id:
          bizId,
        verify_token:
          result.verify_token,
        connected_at: null,
        last_error: null,
      });

      setSuccess(
        t("integrationsWhatsAppConnected"),
      );

      await load();
    } catch (err: any) {
      console.error(err);

      setError(
        formatError(err)
        || t("integrationsWhatsAppConnectError"),
      );
    } finally {
      setConnectingWhatsApp(false);
    }
  }


  async function handleDisconnectWhatsApp() {
    clearMessages();

    try {
      setDisconnectingWhatsApp(true);

      await disconnectWhatsApp(storeId);

      setWhatsApp(null);
      setSuccess(
        t("integrationsWhatsAppDisconnected"),
      );

      await load();
    } catch (err: any) {
      console.error(err);

      setError(
        formatError(err)
        || t("integrationsDisconnectError"),
      );
    } finally {
      setDisconnectingWhatsApp(false);
    }
  }


  if (loading && !commerce && !whatsapp) {
    return (
      <div className="store-integrations loading">
        <Loader2
          className="spin"
          size={16}
        />
        <span>
          {t("integrationsLoading")}
        </span>
      </div>
    );
  }


  return (
    <div className="store-integrations">
      <div className="store-integrations-heading">
        <span className="eyebrow">
          {t("integrationsTitle")}
        </span>
      </div>


      {error && (
        <div className="stores-alert error">
          {error}
        </div>
      )}

      {success && (
        <div className="stores-alert success">
          <Check size={15} />
          {success}
        </div>
      )}


      <div className="store-integration-block shopify">
        <div className="store-integration-header">
          <div className="store-integration-title">
            <ShoppingBag size={17} />

            <strong>
              Shopify
            </strong>

            <span
              className={
                commerce?.connected
                  ? "integration-status connected"
                  : "integration-status disconnected"
              }
            >
              {commerce?.connected
                ? t("integrationsConnected")
                : t("integrationsDisconnected")}
            </span>
          </div>
        </div>

        <div className="store-integration-domain">
          {
            commerce?.external_store_url
            || shopDomain
            || t("integrationsShopifyNoDomain")
          }
        </div>

        {commerce?.connected && (
          <div className="store-integration-shopify-actions">
            <button
              type="button"
              className="store-integration-button secondary"
              onClick={handleTestShopify}
              disabled={testingShopify}
            >
              {testingShopify
                ? <Loader2 className="spin" size={14} />
                : <Check size={14} />}

              {t("integrationsShopifyTest")}
            </button>

            <button
              type="button"
              className="store-integration-button secondary"
              onClick={handleSyncShopify}
              disabled={syncingShopify}
            >
              {syncingShopify
                ? <Loader2 className="spin" size={14} />
                : <ShoppingBag size={14} />}

              {t("integrationsShopifySync")}
            </button>
          </div>
        )}

        {shopifyTestResult && (
          <div
            className={
              shopifyTestResult.connected
                ? "store-integration-test-result ok"
                : "store-integration-test-result error"
            }
          >
            {shopifyTestResult.connected
              ? `${shopifyTestResult.shop_name} — ${shopifyTestResult.currency}`
              : shopifyTestResult.error}
          </div>
        )}

        {shopifySyncResult && (
          <div
            className={
              shopifySyncResult.ok
                ? "store-integration-sync-result ok"
                : "store-integration-sync-result error"
            }
          >
            {shopifySyncResult.ok
              ? `Fetched: ${shopifySyncResult.fetched} | Created: ${shopifySyncResult.created} | Updated: ${shopifySyncResult.updated} | Failed: ${shopifySyncResult.failed}`
              : shopifySyncResult.error}
          </div>
        )}

        {canWrite && (
          <div className="store-integration-actions">
            {commerce?.connected ? (
              <button
                type="button"
                className="store-integration-button danger"
                onClick={handleDisconnectShopify}
                disabled={disconnectingShopify}
              >
                {disconnectingShopify
                  ? <Loader2 className="spin" size={15} />
                  : <Trash2 size={15} />}

                {t("integrationsDisconnect")}
              </button>
            ) : (
              <button
                type="button"
                className="store-integration-button primary"
                onClick={handleConnectShopify}
                disabled={connectingShopify}
              >
                {connectingShopify
                  ? <Loader2 className="spin" size={15} />
                  : <Plug size={15} />}

                {t("integrationsConnect")}
              </button>
            )}
          </div>
        )}
      </div>


      <ShopifyOrders
        storeId={storeId}
        canWrite={canWrite}
        shopConnected={!!commerce?.connected}
        syncedProducts={[]}
      />


      <div className="store-integration-block nuvemshop">
        <div className="store-integration-header">
          <div className="store-integration-title">
            <Store size={17} />

            <strong>
              Nuvemshop
            </strong>

            <span
              className={
                nuvemshop?.connected
                  ? "integration-status connected"
                  : "integration-status disconnected"
              }
            >
              {nuvemshop?.connected
                ? t("integrationsConnected")
                : t("integrationsDisconnected")}
            </span>
          </div>
        </div>

        {nuvemshop?.connected && nuvemshop.nuvemshop_store_id && (
          <div className="store-integration-domain">
            {t("integrationsNuvemshopStoreId")}: {nuvemshop.nuvemshop_store_id}
          </div>
        )}

        {nuvemshop?.connected && (
          <div className="store-integration-shopify-actions">
            <button
              type="button"
              className="store-integration-button secondary"
              onClick={handleSyncNuvemshopProducts}
              disabled={syncingNuvemshopProducts}
            >
              {syncingNuvemshopProducts
                ? <Loader2 className="spin" size={14} />
                : <ShoppingBag size={14} />}

              {t("integrationsNuvemshopSyncProducts")}
            </button>

            <button
              type="button"
              className="store-integration-button secondary"
              onClick={handleSyncNuvemshopOrders}
              disabled={syncingNuvemshopOrders}
            >
              {syncingNuvemshopOrders
                ? <Loader2 className="spin" size={14} />
                : <ShoppingBag size={14} />}

              {t("integrationsNuvemshopSyncOrders")}
            </button>
          </div>
        )}

        {nuvemshopSyncResult && (
          <div
            className={
              nuvemshopSyncResult.ok
                ? "store-integration-sync-result ok"
                : "store-integration-sync-result error"
            }
          >
            {nuvemshopSyncResult.ok
              ? `Fetched: ${nuvemshopSyncResult.fetched} | Created: ${nuvemshopSyncResult.created} | Updated: ${nuvemshopSyncResult.updated} | Failed: ${nuvemshopSyncResult.failed}`
              : t("integrationsNuvemshopSyncError")}
          </div>
        )}

        {canWrite && (
          <div className="store-integration-actions">
            {nuvemshop?.connected ? (
              <button
                type="button"
                className="store-integration-button danger"
                onClick={handleDisconnectNuvemshop}
                disabled={disconnectingNuvemshop}
              >
                {disconnectingNuvemshop
                  ? <Loader2 className="spin" size={15} />
                  : <Trash2 size={15} />}

                {t("integrationsDisconnect")}
              </button>
            ) : (
              <button
                type="button"
                className="store-integration-button primary"
                onClick={handleConnectNuvemshop}
                disabled={connectingNuvemshop}
              >
                {connectingNuvemshop
                  ? <Loader2 className="spin" size={15} />
                  : <Plug size={15} />}

                {t("integrationsConnect")}
              </button>
            )}
          </div>
        )}
      </div>


      <div className="store-integration-block dropi">
        <div className="store-integration-header">
          <div className="store-integration-title">
            <Truck size={17} />
            <strong>Dropi</strong>
            <span
              className={
                commerce?.dropi_detection?.status === "detected"
                  ? "integration-status connected"
                  : "integration-status disconnected"
              }
            >
              {commerce?.dropi_detection?.status === "detected"
                ? "Detectado vía Shopify"
                : "No detectado"}
            </span>
          </div>
        </div>

        <div className="store-integration-detail">
          {commerce?.dropi_detection?.status === "detected" ? (
            <>
              <p>
                Dropi fue detectado como proveedor de tu tienda Shopify.
                Los productos de Dropi están disponibles en tu catálogo
                y pueden ser recomendados por la IA cuando un cliente pregunta.
              </p>
              <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: 8 }}>
                <strong>Próximamente:</strong> sincronización directa de productos,
                gestión de pedidos, y actualización automática de inventario.
              </p>
            </>
          ) : commerce?.connected ? (
            <>
              <p>
                Shopify está conectado, pero no se detectó Dropi como proveedor.
              </p>
              <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: 8 }}>
                Si usas Dropi, asegúrate de que tu tienda Shopify tenga
                productos importados desde Dropi.
              </p>
            </>
          ) : (
            <p>
              Conecta Shopify primero para evaluar si Dropi está configurado como proveedor.
            </p>
          )}
        </div>

        {commerce?.dropi_detection?.status === "detected" && (
          <div className="store-integration-detail" style={{ marginTop: 8, padding: "8px 12px", background: "var(--control-bg)", borderRadius: 8 }}>
            <div style={{ fontSize: "0.78rem", color: "var(--green)", display: "flex", alignItems: "center", gap: 6 }}>
              <Check size={14} />
              <span>Tus productos de Dropi están disponibles para la IA</span>
            </div>
          </div>
        )}
      </div>


      {/* ============================================================
          NEQUI PAYMENT PROVIDER
          ============================================================ */}

      {nequiProviders.length > 0 && (
        <div className="store-integration-block nequi">
          <div className="store-integration-header">
            <div className="store-integration-title">
              <CreditCard size={17} />

              <strong>
                Nequi
              </strong>

              <span
                className={
                  nequi?.connected
                    ? "integration-status connected"
                    : "integration-status disconnected"
                }
              >
                {nequi?.connected
                  ? t("integrationsConnected")
                  : t("integrationsDisconnected")}
              </span>
            </div>
          </div>

          <div className="store-integration-detail">
            {nequi?.connected ? (
              <span>
                {t("integrationsNequiDescription")}
                {nequi.environment === "sandbox"
                  ? ` (${t("integrationsNequiSandbox")})`
                  : ` (${t("integrationsNequiProduction")})`}
              </span>
            ) : (
              <span>{t("integrationsNequiDescription")}</span>
            )}
          </div>

          {canWrite && (
            <div className="store-integration-actions">
              {nequi?.connected ? (
                <>
                  <button
                    type="button"
                    className="store-integration-button secondary"
                    onClick={() => setShowNequiForm(!showNequiForm)}
                  >
                    {t("integrationsNequiConfigure")}
                  </button>

                  <button
                    type="button"
                    className="store-integration-button danger"
                    onClick={handleDisconnectNequi}
                    disabled={disconnectingNequi}
                  >
                    {disconnectingNequi
                      ? <Loader2 className="spin" size={15} />
                      : <Trash2 size={15} />}

                    {t("integrationsDisconnect")}
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  className="store-integration-button primary"
                  onClick={() => setShowNequiForm(!showNequiForm)}
                >
                  <Plug size={15} />
                  {t("integrationsConnect")}
                </button>
              )}
            </div>
          )}

          {showNequiForm && (
            <form
              className="store-integration-whatsapp-form"
              onSubmit={(e) => void handleConnectNequi(e)}
            >
              <label>
                <span>{t("integrationsNequiEnvironment")}</span>
                <select
                  value={nequiEnvironment}
                  onChange={(e) =>
                    setNequiEnvironment(
                      e.target.value as "sandbox" | "production"
                    )
                  }
                >
                  <option value="sandbox">
                    {t("integrationsNequiSandbox")}
                  </option>
                  <option value="production">
                    {t("integrationsNequiProduction")}
                  </option>
                </select>
              </label>

              <label>
                <span>{t("integrationsNequiClientId")}</span>
                <input
                  type="text"
                  value={nequiClientId}
                  onChange={(e) => setNequiClientId(e.target.value)}
                  placeholder={t("integrationsNequiClientIdPlaceholder")}
                  autoComplete="off"
                />
              </label>

              <label>
                <span>{t("integrationsNequiClientSecret")}</span>
                <input
                  type="password"
                  value={nequiClientSecret}
                  onChange={(e) => setNequiClientSecret(e.target.value)}
                  placeholder={t("integrationsNequiClientSecretPlaceholder")}
                  autoComplete="off"
                />
              </label>

              <label>
                <span>{t("integrationsNequiWebhookSecret")}</span>
                <input
                  type="password"
                  value={nequiWebhookSecret}
                  onChange={(e) => setNequiWebhookSecret(e.target.value)}
                  placeholder={t("integrationsNequiWebhookSecretPlaceholder")}
                  autoComplete="off"
                />
              </label>

              <div style={{ display: "flex", gap: 8 }}>
                <button
                  type="submit"
                  className="store-integration-button primary"
                  disabled={connectingNequi}
                >
                  {connectingNequi
                    ? <Loader2 className="spin" size={15} />
                    : <Check size={15} />}
                  {t("integrationsNequiSave")}
                </button>

                <button
                  type="button"
                  className="store-integration-button secondary"
                  onClick={() => {
                    setShowNequiForm(false);
                    setNequiClientId("");
                    setNequiClientSecret("");
                    setNequiWebhookSecret("");
                  }}
                >
                  {t("integrationsCancel")}
                </button>
              </div>
            </form>
          )}
        </div>
      )}


      <div className="store-integration-block whatsapp">
        <div className="store-integration-header">
          <div className="store-integration-title">
            <MessageCircle size={17} />

            <strong>
              WhatsApp
            </strong>

            <span
              className={
                whatsapp?.connected
                  ? "integration-status connected"
                  : "integration-status disconnected"
              }
            >
              {whatsapp?.connected
                ? t("integrationsConnected")
                : t("integrationsDisconnected")}
            </span>
          </div>
        </div>

        {whatsapp?.connected && whatsapp.phone_number_id ? (
          <>
            <div className="store-integration-detail">
              <Phone size={14} />

              <code>
                {whatsapp.phone_number_id}
              </code>
            </div>

            <div className="store-integration-webhook">
              <code>
                {WHATSAPP_WEBHOOK_URL}
              </code>

              {canWrite && (
                <button
                  type="button"
                  className="store-integration-copy"
                  onClick={copyWhatsAppWebhook}
                  title={t("integrationsCopyWebhook")}
                >
                  {whatsappCopied
                    ? <Check size={15} />
                    : <Copy size={15} />}
                </button>
              )}
            </div>

            {whatsapp.verify_token && (
              <div className="store-integration-detail">
                <span style={{ fontSize: 11, opacity: .6 }}>
                  Verify Token:
                </span>

                <code style={{ fontSize: 11 }}>
                  {whatsapp.verify_token}
                </code>

                {canWrite && (
                  <button
                    type="button"
                    className="store-integration-copy"
                    onClick={copyWhatsAppVerifyToken}
                    title={t("integrationsCopyVerifyToken")}
                  >
                    {whatsappCopied
                      ? <Check size={13} />
                      : <Copy size={13} />}
                  </button>
                )}
              </div>
            )}

            {canWrite && (
              <div className="store-integration-actions">
                <button
                  type="button"
                  className="store-integration-button danger"
                  onClick={handleDisconnectWhatsApp}
                  disabled={disconnectingWhatsApp}
                >
                  {disconnectingWhatsApp
                    ? <Loader2 className="spin" size={15} />
                    : <Trash2 size={15} />}

                  {t("integrationsDisconnect")}
                </button>
              </div>
            )}
          </>
        ) : null}


        {canWrite && !whatsapp?.connected && (
          <form
            className="store-integration-whatsapp-form"
            onSubmit={handleConnectWhatsApp}
          >
            <input
              type="text"
              value={whatsappPhoneId}
              onChange={(event) =>
                setWhatsAppPhoneId(
                  event.target.value,
                )
              }
              placeholder={t("integrationsWhatsAppPhonePlaceholder")}
              autoComplete="off"
            />

            <input
              type="text"
              value={whatsappBizId}
              onChange={(event) =>
                setWhatsAppBizId(
                  event.target.value,
                )
              }
              placeholder={t("integrationsWhatsAppBizPlaceholder")}
              autoComplete="off"
            />

            <input
              type="password"
              value={whatsappToken}
              onChange={(event) =>
                setWhatsAppToken(
                  event.target.value,
                )
              }
              placeholder={t("integrationsWhatsAppTokenPlaceholder")}
              autoComplete="off"
            />

            <button
              type="submit"
              className="store-integration-button primary"
              disabled={connectingWhatsApp}
            >
              {connectingWhatsApp
                ? <Loader2 className="spin" size={15} />
                : <Plug size={15} />}

              {t("integrationsConnect")}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}


function formatError(
  err: any,
): string {
  const detail =
    err?.response?.data?.detail;

  if (typeof detail === "string") {
    return detail;
  }

  if (detail?.message) {
    return detail.message;
  }

  return "";
}
