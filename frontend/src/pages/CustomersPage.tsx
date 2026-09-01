import { useTranslation } from "react-i18next";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  ChevronLeft,
  ChevronRight,
  Clock,
  Mail,
  Phone,
  Search,
  ShoppingBag,
  Tag,
  Users,
  X,
} from "lucide-react";
import {
  getCustomerSummary,
  getCustomerList,
  getCustomerDetail,
  type CustomerSummary,
  type CustomerListResponse,
  type CustomerDetail,
} from "../services/customers";


interface CustomersPageProps {
  canWrite: boolean;
  storeId: number;
}


const SEGMENT_KEYS: Record<string, string> = {
  new: "ciSegmentNew",
  interested: "ciSegmentInterested",
  high_intent: "ciSegmentHighIntent",
  buyer: "ciSegmentBuyer",
  repeat_buyer: "ciSegmentRepeatBuyer",
  vip: "ciSegmentVip",
  at_risk: "ciSegmentAtRisk",
  inactive: "ciSegmentInactive",
};


const SEGMENT_COLORS: Record<string, string> = {
  new: "#7c6cff",
  interested: "#3b82f6",
  high_intent: "#f59e0b",
  buyer: "#3ddc97",
  repeat_buyer: "#10b981",
  vip: "#a855f7",
  at_risk: "#ef4444",
  inactive: "#6b7280",
};


function formatTimeAgo(
  iso: string | null,
  t: (key: string) => string,
): string {
  if (!iso) return "—";

  const date = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(
    diffMs / (1000 * 60 * 60 * 24),
  );

  if (diffDays === 0) return t("ciToday");
  if (diffDays === 1) return t("ciYesterday");
  if (diffDays < 7)
    return `${diffDays}d`;
  if (diffDays < 30) {
    const weeks = Math.floor(diffDays / 7);
    return `${weeks}w`;
  }
  if (diffDays < 365) {
    const months = Math.floor(diffDays / 30);
    return `${months}mo`;
  }

  return date.toLocaleDateString();
}


function formatSpend(
  spend: Record<string, { total: number }>,
): string {
  const currencies = Object.keys(spend);

  if (currencies.length === 0) return "—";

  const parts = currencies.map((c) => {
    const val = spend[c].total;
    return `${c} ${val.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
  });

  return parts.join(" / ");
}


export default function CustomersPage({
  canWrite: _canWrite,
  storeId,
}: CustomersPageProps) {
  const { t } = useTranslation();

  const [summary, setSummary] =
    useState<CustomerSummary | null>(null);
  const [list, setList] =
    useState<CustomerListResponse | null>(null);
  const [detail, setDetail] =
    useState<CustomerDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [activeSegment, setActiveSegment] =
    useState<string>("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);

  const [detailCustomerId, setDetailCustomerId] =
    useState<number | null>(null);

  const loadSummary = useCallback(async () => {
    try {
      const data = await getCustomerSummary(
        storeId || undefined,
      );
      setSummary(data);
    } catch {
      setError(t("ciErrorLoading"));
    }
  }, [storeId, t]);

  const loadList = useCallback(async () => {
    try {
      setLoading(true);
      const isFlag =
        activeSegment === "at_risk";
      const data = await getCustomerList({
        storeId: storeId || undefined,
        segment: isFlag
          ? undefined
          : activeSegment || undefined,
        flag: isFlag ? "at_risk" : undefined,
        search: search || undefined,
        page,
        pageSize,
      });
      setList(data);
      setError("");
    } catch {
      setError(t("ciErrorLoading"));
    } finally {
      setLoading(false);
    }
  }, [storeId, activeSegment, search, page, pageSize, t]);

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  useEffect(() => {
    loadList();
  }, [loadList]);

  useEffect(() => {
    setPage(1);
  }, [activeSegment, search]);

  const loadDetail = useCallback(
    async (customerId: number) => {
      try {
        const data = await getCustomerDetail(
          customerId,
          storeId || undefined,
        );
        setDetail(data);
        setDetailCustomerId(customerId);
      } catch {
        // silently fail
      }
    },
    [storeId],
  );

  const closeDetail = useCallback(() => {
    setDetail(null);
    setDetailCustomerId(null);
  }, []);

  const segmentTabs = useMemo(() => {
    if (!summary) return [];

    return [
      { key: "", count: summary.total_customers },
      {
        key: "new",
        count: summary.new_customers,
      },
      {
        key: "interested",
        count: summary.interested,
      },
      {
        key: "high_intent",
        count: summary.high_intent,
      },
      { key: "buyer", count: summary.buyers },
      {
        key: "repeat_buyer",
        count: summary.repeat_buyers,
      },
      { key: "vip", count: summary.vip },
      { key: "at_risk", count: summary.at_risk },
      {
        key: "inactive",
        count: summary.inactive,
      },
    ];
  }, [summary]);

  const totalPages = list?.total_pages || 1;

  return (
    <div className="content">
      <section className="page-heading">
        <div>
          <span className="eyebrow">
            CUSTOMER INTELLIGENCE
          </span>
          <h1>{t("customers")}</h1>
        </div>
      </section>

      {error && !summary && (
        <div className="ci-error">{error}</div>
      )}

      {summary && (
        <div className="ci-summary">
          <div className="ci-stat">
            <div className="ci-stat-value">
              {summary.total_customers.toLocaleString()}
            </div>
            <div className="ci-stat-label">
              {t("ciTotalCustomers")}
            </div>
          </div>
          <div className="ci-stat">
            <div className="ci-stat-value ci-color-new">
              {summary.new_customers.toLocaleString()}
            </div>
            <div className="ci-stat-label">
              {t("ciNew")}
            </div>
          </div>
          <div className="ci-stat">
            <div className="ci-stat-value ci-color-high-intent">
              {summary.high_intent.toLocaleString()}
            </div>
            <div className="ci-stat-label">
              {t("ciHighIntent")}
            </div>
          </div>
          <div className="ci-stat">
            <div className="ci-stat-value ci-color-buyer">
              {summary.buyers.toLocaleString()}
            </div>
            <div className="ci-stat-label">
              {t("ciBuyers")}
            </div>
          </div>
          <div className="ci-stat">
            <div className="ci-stat-value ci-color-repeat">
              {summary.repeat_buyers.toLocaleString()}
            </div>
            <div className="ci-stat-label">
              {t("ciRepeatBuyers")}
            </div>
          </div>
          <div className="ci-stat">
            <div className="ci-stat-value ci-color-vip">
              {summary.vip.toLocaleString()}
            </div>
            <div className="ci-stat-label">
              {t("ciVip")}
            </div>
          </div>
          <div className="ci-stat">
            <div className="ci-stat-value ci-color-at-risk">
              {summary.at_risk.toLocaleString()}
            </div>
            <div className="ci-stat-label">
              {t("ciAtRisk")}
            </div>
          </div>
          <div className="ci-stat">
            <div className="ci-stat-value ci-color-inactive">
              {summary.inactive.toLocaleString()}
            </div>
            <div className="ci-stat-label">
              {t("ciInactive")}
            </div>
          </div>
        </div>
      )}

      <div className="ci-toolbar">
        <div className="ci-tabs">
          {segmentTabs.map((tab) => {
            const label =
              tab.key === ""
                ? t("ciAll")
                : t(SEGMENT_KEYS[tab.key] || tab.key);

            return (
              <button
                key={tab.key}
                className={
                  "ci-tab"
                  + (activeSegment === tab.key
                    ? " active"
                    : "")
                }
                onClick={() => {
                  setActiveSegment(tab.key);
                }}
              >
                {label}
                <span className="ci-tab-count">
                  {tab.count}
                </span>
              </button>
            );
          })}
        </div>

        <div className="ci-search">
          <Search size={14} />
          <input
            type="text"
            placeholder={t("ciSearchPlaceholder")}
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
            }}
          />
          {search && (
            <button
              className="ci-search-clear"
              onClick={() => {
                setSearch("");
              }}
            >
              <X size={12} />
            </button>
          )}
        </div>
      </div>

      <div className="ci-table-wrap">
        <table className="ci-table">
          <thead>
            <tr>
              <th>{t("ciTableCustomer")}</th>
              <th>{t("ciTableSegment")}</th>
              <th>{t("ciTableStore")}</th>
              <th>{t("ciTableLastInteraction")}</th>
              <th>{t("ciTableOrders")}</th>
              <th>{t("ciTableSpend")}</th>
              <th>{t("ciTableLastPurchase")}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td
                  colSpan={8}
                  className="ci-loading"
                >
                  {t("ciLoading")}
                </td>
              </tr>
            )}

            {!loading &&
              list?.items.map((customer) => (
                <tr
                  key={customer.id}
                  className={
                    detailCustomerId === customer.id
                      ? " ci-row-active"
                      : ""
                  }
                >
                  <td>
                    <div className="ci-customer-cell">
                      <div className="ci-avatar">
                        {(customer.name || "?")[0].toUpperCase()}
                      </div>
                      <div>
                        <div className="ci-customer-name">
                          {customer.name}
                        </div>
                        <div className="ci-customer-contact">
                          {customer.phone && (
                            <span>
                              <Phone size={10} />
                              {customer.phone}
                            </span>
                          )}
                          {customer.email && (
                            <span>
                              <Mail size={10} />
                              {customer.email}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td>
                    <span
                      className="ci-segment-badge"
                      style={{
                        background:
                          SEGMENT_COLORS[
                            customer.primary_segment
                          ] + "20",
                        color:
                          SEGMENT_COLORS[
                            customer.primary_segment
                          ],
                      }}
                    >
                      {t(
                        SEGMENT_KEYS[
                          customer.primary_segment
                        ] || customer.primary_segment,
                      )}
                    </span>
                    {customer.flags.includes(
                      "at_risk",
                    ) && (
                      <span className="ci-flag ci-flag-at-risk">
                        {t("ciAtRisk")}
                      </span>
                    )}
                  </td>
                  <td>
                    <div className="ci-store-cell">
                      {customer.store_name || "—"}
                      {customer.country_code && (
                        <span className="ci-country">
                          {customer.country_code}
                        </span>
                      )}
                    </div>
                  </td>
                  <td>
                    <div className="ci-time-cell">
                      <Clock size={12} />
                      {formatTimeAgo(
                        customer.last_interaction_at,
                        t,
                      )}
                    </div>
                  </td>
                  <td className="ci-num">
                    {customer.successful_order_count}
                  </td>
                  <td className="ci-spend">
                    {formatSpend(
                      customer.spend_by_currency,
                    )}
                  </td>
                  <td>
                    <div className="ci-time-cell">
                      <ShoppingBag size={12} />
                      {formatTimeAgo(
                        customer.last_order_at,
                        t,
                      )}
                    </div>
                  </td>
                  <td>
                    <button
                      className="ci-view-btn"
                      onClick={() => {
                        loadDetail(customer.id);
                      }}
                    >
                      {t("ciView")}
                    </button>
                  </td>
                </tr>
              ))}

            {!loading &&
              list &&
              list.items.length === 0 && (
                <tr>
                  <td
                    colSpan={8}
                    className="ci-empty"
                  >
                    <div className="ci-empty-content">
                      <Users size={40} />
                      <p>{t("ciNoCustomers")}</p>
                      <p className="ci-empty-sub">
                        {t("ciNoCustomersSub")}
                      </p>
                    </div>
                  </td>
                </tr>
              )}
          </tbody>
        </table>
      </div>

      {list && list.total_pages > 1 && (
        <div className="ci-pagination">
          <button
            className="ci-page-btn"
            disabled={page <= 1}
            onClick={() => {
              setPage((p) => Math.max(1, p - 1));
            }}
          >
            <ChevronLeft size={14} />
          </button>
          <span className="ci-page-info">
            {t("ciPageInfo", {
              page: list.page,
              total: list.total_pages,
            })}
          </span>
          <button
            className="ci-page-btn"
            disabled={page >= totalPages}
            onClick={() => {
              setPage((p) =>
                Math.min(totalPages, p + 1),
              );
            }}
          >
            <ChevronRight size={14} />
          </button>
        </div>
      )}

      {detail && (
        <div className="ci-detail-overlay">
          <div className="ci-detail-panel">
            <div className="ci-detail-header">
              <div>
                <div className="ci-detail-name">
                  {detail.name}
                </div>
                <div className="ci-detail-contact">
                  {detail.phone && (
                    <span>
                      <Phone size={12} />
                      {detail.phone}
                    </span>
                  )}
                  {detail.email && (
                    <span>
                      <Mail size={12} />
                      {detail.email}
                    </span>
                  )}
                </div>
              </div>
              <button
                className="ci-detail-close"
                onClick={closeDetail}
              >
                <X size={18} />
              </button>
            </div>

            <div className="ci-detail-tags">
              <span
                className="ci-segment-badge ci-segment-badge-lg"
                style={{
                  background:
                    SEGMENT_COLORS[
                      detail.primary_segment
                    ] + "20",
                  color:
                    SEGMENT_COLORS[
                      detail.primary_segment
                    ],
                }}
              >
                {t(
                  SEGMENT_KEYS[
                    detail.primary_segment
                  ] || detail.primary_segment,
                )}
              </span>
              {detail.flags.includes("at_risk") && (
                <span className="ci-flag ci-flag-at-risk">
                  {t("ciAtRisk")}
                </span>
              )}
              {detail.country_code && (
                <span className="ci-flag">
                  <Tag size={10} />
                  {detail.country_code}
                </span>
              )}
              {detail.store_name && (
                <span className="ci-flag">
                  {detail.store_name}
                </span>
              )}
            </div>

            <div className="ci-detail-stats">
              <div className="ci-detail-stat">
                <div className="ci-detail-stat-val">
                  {detail.conversation_count}
                </div>
                <div className="ci-detail-stat-lbl">
                  {t("ciConversations")}
                </div>
              </div>
              <div className="ci-detail-stat">
                <div className="ci-detail-stat-val">
                  {detail.successful_order_count}
                </div>
                <div className="ci-detail-stat-lbl">
                  {t("ciOrders")}
                </div>
              </div>
              <div className="ci-detail-stat">
                <div className="ci-detail-stat-val">
                  {formatSpend(
                    detail.spend_by_currency,
                  )}
                </div>
                <div className="ci-detail-stat-lbl">
                  {t("ciLifetimeSpend")}
                </div>
              </div>
            </div>

            <div className="ci-detail-stats">
              <div className="ci-detail-stat">
                <div className="ci-detail-stat-val">
                  {formatTimeAgo(
                    detail.last_interaction_at,
                    t,
                  )}
                </div>
                <div className="ci-detail-stat-lbl">
                  {t("ciLastInteraction")}
                </div>
              </div>
              <div className="ci-detail-stat">
                <div className="ci-detail-stat-val">
                  {formatTimeAgo(
                    detail.last_order_at,
                    t,
                  )}
                </div>
                <div className="ci-detail-stat-lbl">
                  {t("ciLastPurchase")}
                </div>
              </div>
            </div>

            {detail.recent_orders.length > 0 && (
              <div className="ci-detail-section">
                <h3>{t("ciRecentOrders")}</h3>
                <div className="ci-detail-list">
                  {detail.recent_orders.map(
                    (order) => (
                      <div
                        key={order.id}
                        className="ci-detail-list-item"
                      >
                        <div>
                          <strong>
                            {order.order_number}
                          </strong>
                          <span
                            className={
                              "ci-order-status ci-status-"
                              + order.external_creation_status
                            }
                          >
                            {order.external_creation_status}
                          </span>
                        </div>
                        <div>
                          {order.currency}{" "}
                          {order.total_amount.toLocaleString()}
                        </div>
                        <div className="ci-detail-list-date">
                          {formatTimeAgo(
                            order.created_at,
                            t,
                          )}
                        </div>
                      </div>
                    ),
                  )}
                </div>
              </div>
            )}

            {detail.recent_conversations.length >
              0 && (
              <div className="ci-detail-section">
                <h3>{t("ciRecentConversations")}</h3>
                <div className="ci-detail-list">
                  {detail.recent_conversations.map(
                    (conv) => (
                      <div
                        key={conv.id}
                        className="ci-detail-list-item"
                      >
                        <div>
                          <strong>{conv.channel}</strong>
                          <span className="ci-conv-mode">
                            {conv.mode}
                          </span>
                        </div>
                        <div className="ci-detail-list-date">
                          {formatTimeAgo(
                            conv.updated_at,
                            t,
                          )}
                        </div>
                      </div>
                    ),
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
