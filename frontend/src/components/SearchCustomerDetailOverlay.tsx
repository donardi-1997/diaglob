import { useEffect, useState } from "react";
import {
  LoaderCircle,
  Mail,
  Phone,
  ShoppingBag,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  getCustomerDetail,
  type CustomerDetail,
} from "../services/customers";


interface SearchCustomerDetailOverlayProps {
  customerId?: number;
  storeId: number;
  requestKey?: number;
}


export default function SearchCustomerDetailOverlay({
  customerId,
  storeId,
  requestKey,
}: SearchCustomerDetailOverlayProps) {
  const { t } = useTranslation();
  const [detail, setDetail] = useState<CustomerDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!customerId) {
      setOpen(false);
      setDetail(null);
      return;
    }

    let cancelled = false;
    setOpen(true);
    setLoading(true);
    setDetail(null);

    void getCustomerDetail(customerId, storeId || undefined)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch(() => {
        if (!cancelled) setOpen(false);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [customerId, storeId, requestKey]);

  if (!open || !customerId) return null;

  return (
    <div
      className="ci-detail-overlay"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) setOpen(false);
      }}
    >
      <div
        className="ci-detail-panel"
        role="dialog"
        aria-modal="true"
        aria-label={detail?.name || t("customers")}
      >
        {loading && (
          <div className="ci-loading">
            <LoaderCircle className="spin" size={24} />
          </div>
        )}

        {!loading && detail && (
          <>
            <div className="ci-detail-header">
              <div>
                <div className="ci-detail-name">{detail.name}</div>
                <div className="ci-detail-contact">
                  {detail.phone && (
                    <span><Phone size={12} />{detail.phone}</span>
                  )}
                  {detail.email && (
                    <span><Mail size={12} />{detail.email}</span>
                  )}
                </div>
              </div>
              <button
                type="button"
                className="ci-detail-close"
                onClick={() => setOpen(false)}
                aria-label="Cerrar"
              >
                <X size={18} />
              </button>
            </div>

            <div className="ci-detail-tags">
              <span className="ci-segment-badge ci-segment-badge-lg">
                {detail.primary_segment.replace(/_/g, " ")}
              </span>
              <span className="ci-priority-badge ci-priority-badge-lg">
                {detail.priority}
              </span>
              <span className="ci-health-badge ci-health-badge-lg">
                {detail.customer_health.replace(/_/g, " ")}
              </span>
              {detail.store_name && <span className="ci-flag">{detail.store_name}</span>}
            </div>

            <div className="ci-detail-stats">
              <div className="ci-detail-stat">
                <div className="ci-detail-stat-val">{detail.customer_score}/100</div>
                <div className="ci-detail-stat-lbl">{t("ciScore")}</div>
              </div>
              <div className="ci-detail-stat">
                <div className="ci-detail-stat-val">{detail.conversation_count}</div>
                <div className="ci-detail-stat-lbl">{t("ciConversations")}</div>
              </div>
              <div className="ci-detail-stat">
                <div className="ci-detail-stat-val">{detail.successful_order_count}</div>
                <div className="ci-detail-stat-lbl">{t("ciOrders")}</div>
              </div>
            </div>

            {detail.recent_orders.length > 0 && (
              <div className="ci-detail-section">
                <h3>{t("ciRecentOrders")}</h3>
                <div className="ci-detail-list">
                  {detail.recent_orders.slice(0, 5).map((order) => (
                    <div key={order.id} className="ci-detail-list-item">
                      <div>
                        <strong><ShoppingBag size={12} /> #{order.order_number}</strong>
                      </div>
                      <div>{order.currency} {order.total_amount.toLocaleString()}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
