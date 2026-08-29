import { useTranslation } from "react-i18next";
import { useEffect, useState } from "react";
import {
  ExternalLink,
  LoaderCircle,
} from "lucide-react";
import {
  listCommerceOrders,
  type CommerceOrder,
} from "../services/integrations";


interface CommerceOrdersProps {
  storeId: number;
  canWrite: boolean;
}


function getStatusBadgeClass(
  order: CommerceOrder,
): string {
  if (
    order.external_creation_status === "failed"
  ) {
    return "failed";
  }

  if (
    order.external_creation_status
    === "pending"
  ) {
    return "pending";
  }

  if (
    order.external_creation_status === "created"
  ) {
    return "created";
  }

  return "unknown";
}


function getStatusLabel(
  order: CommerceOrder,
  t: any,
): string {
  if (
    order.external_creation_status === "failed"
  ) {
    return t("commerceOrderStatusFailed");
  }

  if (
    order.external_creation_status
    === "pending"
  ) {
    return t("commerceOrderStatusPending");
  }

  if (
    order.external_creation_status === "created"
  ) {
    return t("commerceOrderStatusCreated");
  }

  if (
    order.external_creation_status
    === "unknown"
  ) {
    return t("commerceOrderStatusUnknown");
  }

  return t("commerceOrderStatusHistorical");
}


export default function CommerceOrders({
  storeId,
  canWrite: _canWrite,
}: CommerceOrdersProps) {
  const { t } = useTranslation();

  const [orders, setOrders] =
    useState<CommerceOrder[]>([]);

  const [loading, setLoading] =
    useState(true);

  const [error, setError] =
    useState("");


  useEffect(() => {
    loadOrders();
  }, [storeId]);


  async function loadOrders() {
    try {
      setLoading(true);
      setError("");

      const data =
        await listCommerceOrders(storeId);

      setOrders(data.items);
    } catch {
      setError(
        t("commerceOrdersError"),
      );
    } finally {
      setLoading(false);
    }
  }


  if (loading) {
    return (
      <div className="commerce-loading">
        <LoaderCircle
          className="spin"
          size={24}
        />
      </div>
    );
  }


  if (error) {
    return (
      <div className="commerce-empty">
        <p>{error}</p>
      </div>
    );
  }


  if (orders.length === 0) {
    return (
      <div className="commerce-empty">
        <p>{t("commerceNoOrders")}</p>
      </div>
    );
  }


  return (
    <div className="commerce-orders">
      <div className="commerce-count">
        {t("commerceOrdersCount", {
          count: orders.length,
        })}
      </div>

      <div className="commerce-orders-table-wrapper">
        <table className="commerce-orders-table">
          <thead>
            <tr>
              <th>
                {t(
                  "commerceOrderNumber",
                )}
              </th>
              <th>
                {t(
                  "commerceOrderTotal",
                )}
              </th>
              <th>
                {t(
                  "commerceOrderStatus",
                )}
              </th>
              <th>
                {t(
                  "commerceOrderSource",
                )}
              </th>
              <th>
                {t(
                  "commerceOrderDate",
                )}
              </th>
              <th />
            </tr>
          </thead>
          <tbody>
            {orders.map((order) => (
              <tr key={order.id}>
                <td className="commerce-order-number">
                  #{order.order_number}
                </td>

                <td>
                  {order.currency}{" "}
                  {order.total_amount.toFixed(
                    2,
                  )}
                </td>

                <td>
                  <span
                    className={
                      "commerce-badge"
                      + " "
                      + getStatusBadgeClass(
                          order,
                        )
                    }
                  >
                    {getStatusLabel(
                      order,
                      t,
                    )}
                  </span>
                </td>

                <td className="commerce-order-source">
                  {order.source
                    ?? "—"}
                </td>

                <td className="commerce-order-date">
                  {order.created_at
                    ? new Date(
                        order.created_at,
                      ).toLocaleDateString()
                    : "—"}
                </td>

                <td>
                  {order.invoice_url && (
                    <a
                      href={
                        order.invoice_url
                      }
                      target="_blank"
                      rel="noopener noreferrer"
                      className="commerce-link"
                    >
                      <ExternalLink
                        size={14}
                      />
                    </a>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
