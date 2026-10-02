import { useEffect, useMemo, useState } from "react";
import {
  ExternalLink,
  LoaderCircle,
  RefreshCw,
  Truck,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  listShipments,
  syncShipment,
  type Shipment,
} from "../services/carriers";

interface CommerceShipmentsProps {
  storeId: number;
  canWrite: boolean;
}

function statusClass(status: string): string {
  if (status === "DELIVERED") return "created";
  if (["FAILED", "EXCEPTION", "RETURNED"].includes(status)) return "failed";
  return "pending";
}

export default function CommerceShipments({
  storeId,
  canWrite,
}: CommerceShipmentsProps) {
  const { t } = useTranslation();
  const [shipments, setShipments] = useState<Shipment[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncingId, setSyncingId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function load() {
    try {
      setLoading(true);
      setError("");
      const result = await listShipments(storeId, { limit: 200 });
      setShipments(result.items || []);
    } catch (err) {
      console.error(err);
      setError(t("commerceShipmentsError"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [storeId]);

  const activeCount = useMemo(
    () =>
      shipments.filter(
        (shipment) =>
          !["DELIVERED", "RETURNED", "FAILED"].includes(shipment.status),
      ).length,
    [shipments],
  );

  async function handleSync(shipment: Shipment) {
    try {
      setSyncingId(shipment.id);
      setError("");
      setNotice("");
      const result = await syncShipment(storeId, shipment.id);
      if (result?.direct_sync === false) {
        setNotice(t("commerceShipmentsPushUpdates"));
      }
      await load();
    } catch (err) {
      console.error(err);
      setError(t("commerceShipmentsSyncError"));
    } finally {
      setSyncingId(null);
    }
  }

  if (loading) {
    return (
      <div className="commerce-loading">
        <LoaderCircle className="spin" size={24} />
      </div>
    );
  }

  return (
    <div className="commerce-orders">
      <div className="commerce-orders-meta">
        <div className="commerce-count">
          {t("commerceShipmentsCount", { count: shipments.length })}
        </div>
        <p className="order-attribution-info">
          {t("commerceShipmentsActive", { count: activeCount })}
        </p>
      </div>

      {error && <div className="order-attribution-notice warning">{error}</div>}
      {notice && <div className="order-attribution-notice success">{notice}</div>}

      {shipments.length === 0 ? (
        <div className="commerce-empty">
          <Truck size={24} />
          <p>{t("commerceNoShipments")}</p>
          <small>{t("commerceNoShipmentsHelp")}</small>
        </div>
      ) : (
        <div className="commerce-orders-table-wrapper">
          <table className="commerce-orders-table">
            <thead>
              <tr>
                <th>{t("commerceShipmentTracking")}</th>
                <th>{t("commerceShipmentCarrier")}</th>
                <th>{t("commerceOrderStatus")}</th>
                <th>{t("commerceShipmentOrder")}</th>
                <th>{t("commerceShipmentLastUpdate")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {shipments.map((shipment) => {
                const latestEvent = shipment.events.at(-1);
                return (
                  <tr key={shipment.id}>
                    <td className="commerce-order-number">
                      <div>{shipment.tracking_number}</div>
                      {shipment.last_mile_tracking_number
                        && shipment.last_mile_tracking_number
                          !== shipment.tracking_number && (
                          <small>
                            {t("commerceShipmentLastMile")}:{" "}
                            {shipment.last_mile_tracking_number}
                          </small>
                        )}
                    </td>
                    <td>
                      {shipment.last_mile_carrier
                        || shipment.tracking_provider
                        || shipment.provider}
                    </td>
                    <td>
                      <span
                        className={`commerce-badge ${statusClass(
                          shipment.status,
                        )}`}
                      >
                        {shipment.status.replaceAll("_", " ")}
                      </span>
                      {latestEvent?.description && (
                        <div style={{ marginTop: 5, fontSize: 11, opacity: 0.7 }}>
                          {latestEvent.description}
                        </div>
                      )}
                    </td>
                    <td>
                      {shipment.order_id ? `#${shipment.order_id}` : "—"}
                    </td>
                    <td className="commerce-order-date">
                      {shipment.last_event_at || shipment.last_synced_at
                        ? new Date(
                            shipment.last_event_at || shipment.last_synced_at || "",
                          ).toLocaleString()
                        : "—"}
                    </td>
                    <td className="order-attribution-actions">
                      {canWrite && (
                        <button
                          type="button"
                          className="order-attribution-history-button"
                          onClick={() => void handleSync(shipment)}
                          disabled={syncingId === shipment.id}
                          title={t("commerceShipmentSync")}
                        >
                          {syncingId === shipment.id
                            ? <LoaderCircle className="spin" size={14} />
                            : <RefreshCw size={14} />}
                        </button>
                      )}
                      {shipment.tracking_url && (
                        <a
                          href={shipment.tracking_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="commerce-link"
                          title={t("commerceShipmentOpenTracking")}
                        >
                          <ExternalLink size={14} />
                        </a>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
