import { useTranslation } from "react-i18next";
import {
  useEffect,
  useState,
} from "react";

import {
  Check,
  Copy,
  Loader2,
  Plug,
  PlugZap,
  ShoppingBag,
  Trash2,
  Truck,
} from "lucide-react";

import {
  connectDropi,
  connectShopify,
  disconnectDropi,
  disconnectShopify,
  getCommerceStatus,
  getDropiStatus,
  type CommerceConnectionStatus,
  type DropiConnectionStatus,
} from "../services/integrations";


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

  const [dropi, setDropi] =
    useState<DropiConnectionStatus | null>(null);

  const [loading, setLoading] =
    useState(true);

  const [dropiToken, setDropiToken] =
    useState("");

  const [connectingShopify, setConnectingShopify] =
    useState(false);

  const [disconnectingShopify, setDisconnectingShopify] =
    useState(false);

  const [connectingDropi, setConnectingDropi] =
    useState(false);

  const [disconnectingDropi, setDisconnectingDropi] =
    useState(false);

  const [copied, setCopied] =
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
        dropiData,
      ] = await Promise.all([
        getCommerceStatus(storeId),
        getDropiStatus(storeId),
      ]);

      setCommerce(commerceData);
      setDropi(dropiData);
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


  async function handleConnectDropi(
    event: React.FormEvent,
  ) {
    event.preventDefault();

    clearMessages();

    const token =
      dropiToken.trim();

    if (!token) {
      setError(
        t("integrationsDropiTokenRequired"),
      );

      return;
    }

    try {
      setConnectingDropi(true);

      const result =
        await connectDropi(
          storeId,
          token,
        );

      // Limpia el token inmediatamente:
      // nunca se guarda ni queda en memoria.
      setDropiToken("");

      setDropi({
        connected: true,
        status: "connected",
        external_store_id: null,
        api_url: null,
        webhook_url:
          result.webhook_url,
        connected_at: null,
        last_sync_at: null,
        last_error: null,
      });

      setSuccess(
        t("integrationsDropiConnected"),
      );

      await load();
    } catch (err: any) {
      console.error(err);

      setError(
        formatError(err)
        || t("integrationsDropiConnectError"),
      );
    } finally {
      setConnectingDropi(false);
    }
  }


  async function handleDisconnectDropi() {
    clearMessages();

    try {
      setDisconnectingDropi(true);

      await disconnectDropi(storeId);

      setDropi(null);
      setSuccess(
        t("integrationsDropiDisconnected"),
      );

      await load();
    } catch (err: any) {
      console.error(err);

      setError(
        formatError(err)
        || t("integrationsDisconnectError"),
      );
    } finally {
      setDisconnectingDropi(false);
    }
  }


  async function copyWebhook() {
    const url =
      dropi?.webhook_url;

    if (!url) {
      return;
    }

    try {
      await navigator.clipboard.writeText(url);

      setCopied(true);

      setTimeout(
        () => setCopied(false),
        1800,
      );
    } catch {
      setError(
        t("integrationsCopyError"),
      );
    }
  }


  if (loading && !commerce && !dropi) {
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


      <div className="store-integration-block dropi">
        <div className="store-integration-header">
          <div className="store-integration-title">
            <Truck size={17} />

            <strong>
              Dropi
            </strong>

            <span
              className={
                dropi?.connected
                  ? "integration-status connected"
                  : "integration-status disconnected"
              }
            >
              {dropi?.connected
                ? t("integrationsConnected")
                : t("integrationsDisconnected")}
            </span>
          </div>
        </div>

        {dropi?.connected && dropi.webhook_url ? (
          <>
            <div className="store-integration-webhook">
              <code>
                {dropi.webhook_url}
              </code>

              {canWrite && (
                <button
                  type="button"
                  className="store-integration-copy"
                  onClick={copyWebhook}
                  title={t("integrationsCopyWebhook")}
                >
                  {copied
                    ? <Check size={15} />
                    : <Copy size={15} />}
                </button>
              )}
            </div>

            {canWrite && (
              <div className="store-integration-actions">
                <button
                  type="button"
                  className="store-integration-button danger"
                  onClick={handleDisconnectDropi}
                  disabled={disconnectingDropi}
                >
                  {disconnectingDropi
                    ? <Loader2 className="spin" size={15} />
                    : <PlugZap size={15} />}

                  {t("integrationsDisconnect")}
                </button>
              </div>
            )}
          </>
        ) : null}


        {canWrite && !dropi?.connected && (
          <form
            className="store-integration-dropi-form"
            onSubmit={handleConnectDropi}
          >
            <input
              type="password"
              value={dropiToken}
              onChange={(event) =>
                setDropiToken(
                  event.target.value,
                )
              }
              placeholder={t("integrationsDropiTokenPlaceholder")}
              autoComplete="off"
            />

            <button
              type="submit"
              className="store-integration-button primary"
              disabled={connectingDropi}
            >
              {connectingDropi
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
