import { useEffect, useMemo, useState } from "react";
import { Check, Copy, Loader2, Truck, Unplug } from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  connectCarrier,
  disconnectCarrier,
  getStoreCarriers,
  type CarrierConnectResult,
  type StoreCarrierItem,
} from "../services/carriers";

interface CarrierIntegrationsCardProps {
  storeId: number;
  storeCountryCode?: string | null;
  canWrite: boolean;
}

export default function CarrierIntegrationsCard({
  storeId,
  storeCountryCode,
  canWrite,
}: CarrierIntegrationsCardProps) {
  const { t } = useTranslation();
  const [items, setItems] = useState<StoreCarrierItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [lastConnect, setLastConnect] =
    useState<Record<string, CarrierConnectResult>>({});
  const [copied, setCopied] = useState<string | null>(null);

  const isColombia = (storeCountryCode || "").toUpperCase() === "CO";

  async function load() {
    if (!storeId) return;
    try {
      setLoading(true);
      setError("");
      const data = await getStoreCarriers(storeId);
      setItems(data.items || []);
    } catch (err) {
      console.error(err);
      setError(t("carrierIntegrationsLoadError"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [storeId]);

  const connectedCount = useMemo(
    () => items.filter((item) => item.connection?.status === "connected").length,
    [items],
  );

  async function handleConnect(carrierKey: string) {
    try {
      setBusyKey(carrierKey);
      setError("");
      const result = await connectCarrier(storeId, carrierKey);
      setLastConnect((current) => ({
        ...current,
        [carrierKey]: result,
      }));
      await load();
    } catch (err) {
      console.error(err);
      setError(t("carrierIntegrationsConnectError"));
    } finally {
      setBusyKey(null);
    }
  }

  async function handleDisconnect(carrierKey: string) {
    try {
      setBusyKey(carrierKey);
      setError("");
      await disconnectCarrier(storeId, carrierKey);
      setLastConnect((current) => {
        const next = { ...current };
        delete next[carrierKey];
        return next;
      });
      await load();
    } catch (err) {
      console.error(err);
      setError(t("carrierIntegrationsDisconnectError"));
    } finally {
      setBusyKey(null);
    }
  }

  async function copyValue(key: string, value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(key);
      window.setTimeout(() => setCopied(null), 1600);
    } catch {
      setError(t("integrationsCopyError"));
    }
  }

  if (!isColombia) {
    return (
      <div className="store-integration-block">
        <div className="store-integration-header">
          <div className="store-integration-title">
            <Truck size={17} />
            <strong>{t("carrierIntegrationsTitle")}</strong>
            <span className="integration-status disconnected">
              {t("carrierIntegrationsColombiaFirst")}
            </span>
          </div>
        </div>
        <div className="store-integration-domain">
          {t("carrierIntegrationsOtherCountry")}
        </div>
      </div>
    );
  }

  return (
    <div className="store-integration-block">
      <div className="store-integration-header">
        <div className="store-integration-title">
          <Truck size={17} />
          <strong>{t("carrierIntegrationsTitle")}</strong>
          <span
            className={
              connectedCount > 0
                ? "integration-status connected"
                : "integration-status disconnected"
            }
          >
            {connectedCount > 0
              ? t("carrierIntegrationsConnectedCount", { count: connectedCount })
              : t("integrationsDisconnected")}
          </span>
        </div>
      </div>

      <div className="store-integration-domain">
        {t("carrierIntegrationsSubtitle")}
      </div>

      {error && <div className="stores-alert error">{error}</div>}

      {loading ? (
        <div className="store-integration-detail">
          <Loader2 className="spin" size={14} />
          <span>{t("integrationsLoading")}</span>
        </div>
      ) : (
        <div style={{ display: "grid", gap: 10, marginTop: 12 }}>
          {items.map((item) => {
            const connected = item.connection?.status === "connected";
            const result = lastConnect[item.key];

            return (
              <div
                key={item.key}
                style={{
                  border: "1px solid var(--border)",
                  borderRadius: 10,
                  padding: 12,
                  display: "grid",
                  gap: 9,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    gap: 10,
                    alignItems: "center",
                    justifyContent: "space-between",
                    flexWrap: "wrap",
                  }}
                >
                  <div style={{ display: "grid", gap: 3 }}>
                    <strong>{item.name}</strong>
                    <small style={{ opacity: 0.7 }}>
                      {item.documented_api
                        ? t("carrierIntegrationsOfficialApi")
                        : t("carrierIntegrationsTrackingBridge")}
                    </small>
                  </div>

                  <span
                    className={
                      connected
                        ? "integration-status connected"
                        : "integration-status disconnected"
                    }
                  >
                    {connected
                      ? t("integrationsConnected")
                      : t("integrationsDisconnected")}
                  </span>
                </div>

                {result && (
                  <>
                    <div className="store-integration-detail">
                      <span style={{ fontSize: 11, opacity: 0.65 }}>
                        {t("carrierIntegrationsUpdatesUrl")}
                      </span>
                    </div>
                    <div className="store-integration-webhook">
                      <code>{result.callback_url}</code>
                      <button
                        type="button"
                        className="store-integration-copy"
                        onClick={() =>
                          copyValue(
                            `${item.key}:callback`,
                            result.callback_url,
                          )}
                        title={t("integrationsCopyWebhook")}
                      >
                        {copied === `${item.key}:callback`
                          ? <Check size={14} />
                          : <Copy size={14} />}
                      </button>
                    </div>

                    <div className="store-integration-detail">
                      <span style={{ fontSize: 11, opacity: 0.65 }}>
                        {t("carrierIntegrationsTokenOnce")}
                      </span>
                      <code style={{ fontSize: 11 }}>
                        {result.webhook_token}
                      </code>
                      <button
                        type="button"
                        className="store-integration-copy"
                        onClick={() =>
                          copyValue(
                            `${item.key}:token`,
                            result.webhook_token,
                          )}
                        title={t("integrationsCopyVerifyToken")}
                      >
                        {copied === `${item.key}:token`
                          ? <Check size={13} />
                          : <Copy size={13} />}
                      </button>
                    </div>
                  </>
                )}

                {canWrite && (
                  <div className="store-integration-actions">
                    {connected ? (
                      <button
                        type="button"
                        className="store-integration-button danger"
                        disabled={busyKey === item.key}
                        onClick={() => handleDisconnect(item.key)}
                      >
                        {busyKey === item.key
                          ? <Loader2 className="spin" size={14} />
                          : <Unplug size={14} />}
                        {t("integrationsDisconnect")}
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="store-integration-button primary"
                        disabled={busyKey === item.key}
                        onClick={() => handleConnect(item.key)}
                      >
                        {busyKey === item.key
                          ? <Loader2 className="spin" size={14} />
                          : <Truck size={14} />}
                        {t("carrierIntegrationsConnect")}
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
