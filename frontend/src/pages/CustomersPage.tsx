import { useTranslation } from "react-i18next";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Clock,
  Mail,
  Phone,
  Search,
  ShoppingBag,
  Target,
  TrendingUp,
  Users,
  X,
} from "lucide-react";
import CustomerRiskAlert from "../components/CustomerRiskAlert";
import {
  getCustomerSummary,
  getCustomerList,
  getCustomerDetail,
  type CustomerSummary,
  type CustomerListResponse,
  type CustomerDetail,
  type TimelineEvent,
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


const PRIORITY_COLORS: Record<string, string> = {
  high: "#ef4444",
  medium: "#f59e0b",
  low: "#6b7280",
};


const PRIORITY_KEYS: Record<string, string> = {
  high: "ciPriorityHigh",
  medium: "ciPriorityMedium",
  low: "ciPriorityLow",
};


const HEALTH_COLORS: Record<string, string> = {
  active: "#10b981",
  at_risk: "#f59e0b",
  inactive: "#6b7280",
};


const HEALTH_KEYS: Record<string, string> = {
  active: "ciHealthActive",
  at_risk: "ciHealthAtRisk",
  inactive: "ciHealthInactive",
};


const ACTION_KEYS: Record<string, string> = {
  follow_up_conversation: "ciActionFollowUp",
  recover_failed_order: "ciActionRecoverFailed",
  reengage_customer: "ciActionReengage",
  review_vip: "ciActionReviewVip",
  no_action_needed: "ciActionNoAction",
};


const TIMELINE_ICONS: Record<string, string> = {
  customer_created: "ciTimelineCreated",
  conversation: "ciTimelineConversation",
  order_created: "ciTimelineOrderCreated",
  order_status_failed: "ciTimelineOrderFailed",
  order_status_unknown: "ciTimelineOrderUnknown",
  order_pending: "ciTimelineOrderPending",
};


const CODE_TRANSLATIONS: Record<string, string> = {
  recent_interaction: "ciCodeRecentInteraction",
  moderate_interaction: "ciCodeModerateInteraction",
  stale_interaction: "ciCodeStaleInteraction",
  multiple_conversations: "ciCodeMultipleConversations",
  has_conversations: "ciCodeHasConversations",
  high_message_volume: "ciCodeHighMessageVolume",
  moderate_message_volume: "ciCodeModerateMessageVolume",
  vip_customer: "ciCodeVipCustomer",
  repeat_customer: "ciCodeRepeatCustomer",
  has_orders: "ciCodeHasOrders",
  recent_purchase: "ciCodeRecentPurchase",
  moderate_purchase_recency: "ciCodeModeratePurchaseRecency",
  recent_purchase_recency: "ciCodeRecentPurchaseRecency",
  long_term_customer: "ciCodeLongTermCustomer",
  established_customer: "ciCodeEstablishedCustomer",
  high_order_frequency: "ciCodeHighOrderFrequency",
  repeat_buyer_loyalty: "ciCodeRepeatBuyerLoyalty",
  at_risk: "ciCodeAtRisk",
  recent_failed_order: "ciCodeRecentFailedOrder",
  recent_unknown_order: "ciCodeRecentUnknownOrder",
  vip_at_risk: "ciCodeVipAtRisk",
  high_intent_strong_signal: "ciCodeHighIntentStrongSignal",
  buyer_failed_order_recent: "ciCodeBuyerFailedOrderRecent",
  recent_high_intent: "ciCodeRecentHighIntent",
  active_buyer: "ciCodeActiveBuyer",
  high_engagement_score: "ciCodeHighEngagementScore",
  inactive_customer: "ciCodeInactiveCustomer",
  low_engagement_score: "ciCodeLowEngagementScore",
  no_priority_signal: "ciCodeNoPrioritySignal",
  high_intent_no_order: "ciCodeHighIntentNoOrder",
  repeat_customer_opp: "ciCodeRepeatCustomerOppo",
  vip_customer_opp: "ciCodeVipCustomerOppo",
  recent_failed_order_recovery: "ciCodeRecentFailedOrderRecovery",
  recent_reengagement: "ciCodeRecentReengagement",
  recent_conversation_no_order: "ciCodeRecentConversationNoOrder",
  inactive: "ciCodeInactive",
  failed_order: "ciCodeFailedOrder",
  unknown_order: "ciCodeUnknownOrder",
  long_time_since_purchase: "ciCodeLongTimeSincePurchase",
  long_time_since_interaction: "ciCodeLongTimeSinceInteraction",
  no_engagement_history: "ciCodeNoEngagementHistory",
  order_failed_recently: "ciCodeOrderFailedRecently",
  vip_customer_at_risk: "ciCodeVipCustomerAtRisk",
  customer_at_risk: "ciCodeCustomerAtRisk",
  recent_high_intent_conversation: "ciCodeRecentHighIntentConversation",
  buyer_becoming_inactive: "ciCodeBuyerBecomingInactive",
  customer_inactive: "ciCodeCustomerInactive",
  new_customer_no_engagement: "ciCodeNewCustomerNoEngagement",
  moderately_recent_interaction: "ciCodeModeratelyRecentInteraction",
  stale_interaction_recency: "ciCodeStaleInteractionRecency",
};


function formatIntelligenceCode(
  code: string,
  t: (key: string) => string,
): string {
  const key = CODE_TRANSLATIONS[code];
  if (key) {
    const translated = t(key);
    if (translated !== key) return translated;
  }
  return code
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}


function formatTimeAgo(
  iso: string | null,
  t: (key: string) => string,
): string {
  if (!iso) return "\u2014";

  const date = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(
    diffMs / (1000 * 60 * 60 * 24),
  );

  if (diffDays === 0) return t("ciToday");
  if (diffDays === 1) return t("ciYesterday");
  if (diffDays < 7) return `${diffDays}d`;
  if (diffDays < 30) {
    const weeks = Math.floor(diffDays / 7);
    return `${weeks}wk`;
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

  if (currencies.length === 0) return "\u2014";

  const parts = currencies.map((c) => {
    const val = spend[c].total;
    return `${c} ${val.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
  });

  return parts.join(" / ");
}


function ScoreBar({ score }: { score: number }) {
  const color = "#7c6cff";

  return (
    <div className="ci-score-cell">
      <div className="ci-score-value">{score}</div>
      <div className="ci-score-bar">
        <div
          className="ci-score-fill"
          style={{
            width: `${score}%`,
            background: color,
          }}
        />
      </div>
    </div>
  );
}


function TimelineSection({
  timeline,
  t,
}: {
  timeline: TimelineEvent[];
  t: (key: string) => string;
}) {
  if (!timeline || timeline.length === 0) return null;

  return (
    <div className="ci-detail-section">
      <h3>{t("ciTimeline")}</h3>
      <div className="ci-timeline">
        {timeline.slice(0, 15).map((ev, idx) => {
          const iconClass =
            ev.type.includes("status_failed")
              ? "ci-tl-icon ci-tl-failed"
              : ev.type.includes("status_unknown")
                ? "ci-tl-icon ci-tl-unknown"
                : ev.type === "conversation"
                  ? "ci-tl-icon ci-tl-conv"
                  : "ci-tl-icon ci-tl-default";

          return (
            <div key={idx} className="ci-tl-item">
              <div className={iconClass}>
                {ev.type === "conversation" && (
                  <Mail size={10} />
                )}
                {ev.type === "customer_created" && (
                  <Users size={10} />
                )}
                {ev.type.includes("order") && (
                  <ShoppingBag size={10} />
                )}
              </div>
              <div className="ci-tl-content">
                <div className="ci-tl-type">
                  {t(
                    TIMELINE_ICONS[ev.type] ||
                      ev.type,
                  )}
                </div>
                <div className="ci-tl-meta">
                  {ev.channel && (
                    <span>{ev.channel}</span>
                  )}
                  {ev.order_number && (
                    <span>{ev.order_number}</span>
                  )}
                  {ev.total_amount !== undefined &&
                    ev.currency && (
                      <span>
                        {ev.currency}{" "}
                        {ev.total_amount.toLocaleString()}
                      </span>
                    )}
                </div>
              </div>
              <div className="ci-tl-time">
                {formatTimeAgo(ev.timestamp, t)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}


export default function CustomersPage({
  canWrite,
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
  const [activePriority, setActivePriority] =
    useState<string>("");
  const [activeHealth, setActiveHealth] =
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
        priority: activePriority || undefined,
        health: activeHealth || undefined,
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
  }, [
    storeId,
    activeSegment,
    activePriority,
    activeHealth,
    search,
    page,
    pageSize,
    t,
  ]);

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  useEffect(() => {
    loadList();
  }, [loadList]);

  useEffect(() => {
    setPage(1);
  }, [activeSegment, activePriority, activeHealth, search]);

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
            <div className="ci-stat-value ci-color-at-risk">
              {summary.high_priority.toLocaleString()}
            </div>
            <div className="ci-stat-label">
              {t("ciHighPriority")}
            </div>
          </div>
          <div className="ci-stat">
            <div className="ci-stat-value ci-color-at-risk">
              {summary.needs_followup.toLocaleString()}
            </div>
            <div className="ci-stat-label">
              {t("ciNeedsFollowup")}
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
                : t(
                    SEGMENT_KEYS[tab.key] ||
                      tab.key,
                  );

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

        <div className="ci-filters-row">
          <select
            className="ci-filter-select"
            value={activePriority}
            onChange={(e) => {
              setActivePriority(e.target.value);
            }}
          >
            <option value="">
              {t("ciFilterAllPriority")}
            </option>
            <option value="high">
              {t("ciPriorityHigh")}
            </option>
            <option value="medium">
              {t("ciPriorityMedium")}
            </option>
            <option value="low">
              {t("ciPriorityLow")}
            </option>
          </select>

          <select
            className="ci-filter-select"
            value={activeHealth}
            onChange={(e) => {
              setActiveHealth(e.target.value);
            }}
          >
            <option value="">
              {t("ciFilterAllHealth")}
            </option>
            <option value="active">
              {t("ciHealthActive")}
            </option>
            <option value="at_risk">
              {t("ciHealthAtRisk")}
            </option>
            <option value="inactive">
              {t("ciHealthInactive")}
            </option>
          </select>

          <div className="ci-search">
            <Search size={14} />
            <input
              type="text"
              placeholder={t(
                "ciSearchPlaceholder",
              )}
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
      </div>

      <div className="ci-table-wrap">
        <table className="ci-table">
          <thead>
            <tr>
              <th>{t("ciTableCustomer")}</th>
              <th>{t("ciTableSegment")}</th>
              <th>{t("ciTablePriority")}</th>
              <th>{t("ciTableScore")}</th>
              <th>{t("ciTableHealth")}</th>
              <th>{t("ciTableLastInteraction")}</th>
              <th>{t("ciTableOrders")}</th>
              <th>{t("ciTableSpend")}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td
                  colSpan={9}
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
                        <CustomerRiskAlert
                          customerId={customer.id}
                          risk={customer.customer_risk}
                          compact
                        />
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
                          ]
                            + "20",
                        color:
                          SEGMENT_COLORS[
                            customer.primary_segment
                          ],
                      }}
                    >
                      {t(
                        SEGMENT_KEYS[
                          customer.primary_segment
                        ] ||
                          customer.primary_segment,
                      )}
                    </span>
                  </td>
                  <td>
                    <span
                      className="ci-priority-badge"
                      style={{
                        background:
                          PRIORITY_COLORS[
                            customer.priority
                          ]
                            + "20",
                        color:
                          PRIORITY_COLORS[
                            customer.priority
                          ],
                      }}
                    >
                      {t(
                        PRIORITY_KEYS[
                          customer.priority
                        ] || customer.priority,
                      )}
                    </span>
                    {customer.priority_reasons
                      .length > 0 && (
                      <div className="ci-reason-codes">
                        {customer.priority_reasons
                          .slice(0, 2)
                          .map((r) => (
                            <span
                              key={r}
                              className="ci-reason-code"
                            >
                              {formatIntelligenceCode(r, t)}
                            </span>
                          ))}
                      </div>
                    )}
                  </td>
                  <td>
                    <ScoreBar
                      score={customer.customer_score}
                    />
                  </td>
                  <td>
                    <span
                      className="ci-health-badge"
                      style={{
                        background:
                          HEALTH_COLORS[
                            customer.customer_health
                          ]
                            + "20",
                        color:
                          HEALTH_COLORS[
                            customer.customer_health
                          ],
                      }}
                    >
                      {t(
                        HEALTH_KEYS[
                          customer.customer_health
                        ] ||
                          customer.customer_health,
                      )}
                    </span>
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
                    colSpan={9}
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
              <span
                className="ci-priority-badge ci-priority-badge-lg"
                style={{
                  background:
                    PRIORITY_COLORS[
                      detail.priority
                    ] + "20",
                  color:
                    PRIORITY_COLORS[
                      detail.priority
                    ],
                }}
              >
                {t(
                  PRIORITY_KEYS[detail.priority] ||
                    detail.priority,
                )}
              </span>
              <span
                className="ci-health-badge ci-health-badge-lg"
                style={{
                  background:
                    HEALTH_COLORS[
                      detail.customer_health
                    ] + "20",
                  color:
                    HEALTH_COLORS[
                      detail.customer_health
                    ],
                }}
              >
                {t(
                  HEALTH_KEYS[
                    detail.customer_health
                  ] || detail.customer_health,
                )}
              </span>
              {detail.country_code && (
                <span className="ci-flag">
                  {detail.country_code}
                </span>
              )}
              {detail.store_name && (
                <span className="ci-flag">
                  {detail.store_name}
                </span>
              )}
            </div>

            <CustomerRiskAlert
              key={detail.id}
              customerId={detail.id}
              risk={detail.customer_risk}
              storeId={storeId || undefined}
              canReport={canWrite}
              onChanged={(customerRisk) => {
                setDetail((current) =>
                  current && current.id === detail.id
                    ? { ...current, customer_risk: customerRisk }
                    : current,
                );
                setList((current) =>
                  current
                    ? {
                        ...current,
                        items: current.items.map((item) =>
                          item.id === detail.id
                            ? { ...item, customer_risk: customerRisk }
                            : item,
                        ),
                      }
                    : current,
                );
              }}
            />

            {/* Customer Score */}
            <div className="ci-detail-section">
              <h3>{t("ciScore")}</h3>
              <div className="ci-score-detail">
                <div className="ci-score-number">
                  {detail.customer_score}
                  <span className="ci-score-total">
                    {" "}/ 100
                  </span>
                </div>
                <div className="ci-score-bar ci-score-bar-lg">
                  <div
                    className="ci-score-fill"
                    style={{
                      width: `${detail.customer_score}%`,
                      background: "#7c6cff",
                    }}
                  />
                </div>
              </div>
              {detail.score_factors.length > 0 && (
                <div className="ci-score-factors">
                  {detail.score_factors.map(
                    (f, idx) => (
                      <span
                        key={idx}
                        className={
                          "ci-factor"
                          + (f.impact < 0
                            ? " ci-factor-negative"
                            : "")
                        }
                      >
                        {formatIntelligenceCode(f.code, t)}:{" "}
                        {f.impact > 0 ? "+" : ""}
                        {f.impact}
                      </span>
                    ),
                  )}
                </div>
              )}
            </div>

            {/* Opportunities */}
            {detail.opportunities.length > 0 && (
              <div className="ci-detail-section">
                <h3>{t("ciOpportunities")}</h3>
                <div className="ci-detail-list">
                  {detail.opportunities.map(
                    (opp, idx) => (
                      <div
                        key={idx}
                        className="ci-detail-list-item ci-opp"
                      >
                        <TrendingUp
                          size={12}
                        />
                        <span>{formatIntelligenceCode(opp, t)}</span>
                      </div>
                    ),
                  )}
                </div>
              </div>
            )}

            {/* Risks */}
            {detail.risks.length > 0 && (
              <div className="ci-detail-section">
                <h3>{t("ciRisks")}</h3>
                <div className="ci-detail-list">
                  {detail.risks.map(
                    (risk, idx) => (
                      <div
                        key={idx}
                        className="ci-detail-list-item ci-risk"
                      >
                        <AlertTriangle
                          size={12}
                        />
                        <span>{formatIntelligenceCode(risk, t)}</span>
                      </div>
                    ),
                  )}
                </div>
              </div>
            )}

            {/* Next Best Action */}
            <div className="ci-detail-section">
              <h3>{t("ciNextBestAction")}</h3>
              <div className="ci-action-box">
                <Target size={14} />
                <span className="ci-action-text">
                  {t(
                    ACTION_KEYS[
                      detail.next_best_action
                    ] ||
                      detail.next_best_action,
                  )
                }</span>
              </div>
              {detail.next_best_action_reasons
                .length > 0 && (
                <div className="ci-action-reasons">
                  {detail.next_best_action_reasons.map(
                    (r, idx) => (
                      <span
                        key={idx}
                        className="ci-reason-code"
                      >
                        {formatIntelligenceCode(r, t)}
                      </span>
                    ),
                  )}
                </div>
              )}
            </div>

            {/* Stats */}
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
              {detail.failed_order_count > 0 && (
                <div className="ci-detail-stat">
                  <div className="ci-detail-stat-val ci-color-at-risk">
                    {detail.failed_order_count}
                  </div>
                  <div className="ci-detail-stat-lbl">
                    {t("ciFailedOrders")}
                  </div>
                </div>
              )}
            </div>

            {/* Timeline */}
            <TimelineSection
              timeline={detail.timeline}
              t={t}
            />

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
                            {
                              order.external_creation_status
                            }
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
                <h3>
                  {t("ciRecentConversations")}
                </h3>
                <div className="ci-detail-list">
                  {detail.recent_conversations.map(
                    (conv) => (
                      <div
                        key={conv.id}
                        className="ci-detail-list-item"
                      >
                        <div>
                          <strong>
                            {conv.channel}
                          </strong>
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
