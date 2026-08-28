import { useEffect, useMemo, useState } from "react";
import {
  Bot,
  BrainCircuit,
  LoaderCircle,
  Search,
  Send,
  UserRound,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  getConversation,
  getConversations,
  sendConversationMessage,
  setConversationMode,
} from "../services/conversations";

import type {
  ConversationDetail,
  ConversationMode,
  ConversationSummary,
} from "../types/conversation";

export default function ConversationsPage({
  canWrite,
}: {
  canWrite: boolean;
}) {
  const { t } = useTranslation();

  const [conversations, setConversations] = useState<
    ConversationSummary[]
  >([]);

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [conversation, setConversation] =
    useState<ConversationDetail | null>(null);

  const [loadingList, setLoadingList] = useState(true);
  const [loadingConversation, setLoadingConversation] =
    useState(false);

  const [changingMode, setChangingMode] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState("");
  const [sendingMessage, setSendingMessage] = useState(false);

  useEffect(() => {
    loadConversations();
  }, []);

  useEffect(() => {
    if (selectedId === null) {
      return;
    }

    loadConversation(selectedId);
  }, [selectedId]);

  async function loadConversations() {
    try {
      setLoadingList(true);
      setError("");

      const data = await getConversations();

      setConversations(data.items);

      if (data.items.length > 0) {
        setSelectedId((current) => current ?? data.items[0].id);
      }
    } catch (err) {
      console.error(err);
      setError(
        t("conversationsLoadError"),
      );
    } finally {
      setLoadingList(false);
    }
  }

  async function loadConversation(id: number) {
    try {
      setLoadingConversation(true);
      setError("");

      const data = await getConversation(id);

      setConversation(data);
    } catch (err) {
      console.error(err);
      setError(t("conversationLoadError"));
    } finally {
      setLoadingConversation(false);
    }
  }

  async function toggleMode() {
    if (
      !conversation ||
      !canWrite
    ) {
      return;
    }

    const nextMode: ConversationMode =
      conversation.mode === "ai" ? "human" : "ai";

    try {
      setChangingMode(true);

      await setConversationMode(
        conversation.id,
        nextMode,
      );

      setConversation((current) =>
        current
          ? {
              ...current,
              mode: nextMode,
            }
          : current,
      );

      setConversations((current) =>
        current.map((item) =>
          item.id === conversation.id
            ? {
                ...item,
                mode: nextMode,
              }
            : item,
        ),
      );
    } catch (err) {
      console.error(err);
      setError(t("conversationModeError"));
    } finally {
      setChangingMode(false);
    }
  }

  async function handleSendMessage() {
    if (!conversation) {
      return;
    }

    const text = message.trim();

    if (!text) {
      return;
    }

    try {
      setSendingMessage(true);
      setError("");

      const newMessage = await sendConversationMessage(
        conversation.id,
        text,
      );

      setConversation((current) =>
        current
          ? {
              ...current,
              preview: text,
              messages: [
                ...current.messages,
                newMessage,
              ],
            }
          : current,
      );

      setConversations((current) =>
        current.map((item) =>
          item.id === conversation.id
            ? {
                ...item,
                preview: text,
                unread: 0,
              }
            : item,
        ),
      );

      setMessage("");
    } catch (err) {
      console.error(err);
      setError(t("conversationSendError"));
    } finally {
      setSendingMessage(false);
    }
  }

  const filteredConversations = useMemo(() => {
    const normalized = search.trim().toLowerCase();

    if (!normalized) {
      return conversations;
    }

    return conversations.filter((item) =>
      `${item.name} ${item.preview} ${item.phone}`
        .toLowerCase()
        .includes(normalized),
    );
  }, [conversations, search]);

  return (
    <div className="content conversations-content">
      <section className="page-heading conversations-heading">
        <div>
          <span className="eyebrow">DIAGLOB INBOX</span>
          <h1>{t("conversationsTitle")}</h1>
          <p>{t("conversationsSubtitle")}</p>
        </div>
      </section>

      {error && (
        <div className="api-error">
          {error}
        </div>
      )}

      <div className="inbox-layout">
        <section className="conversation-list-panel">
          <div className="conversation-search">
            <Search size={16} />

            <input
              value={search}
              onChange={(event) =>
                setSearch(event.target.value)
              }
              placeholder={t("searchConversation")}
            />
          </div>

          <div className="conversation-filters">
            <button className="active">
              {t("all")}
            </button>

            <button>
              {t("unread")}
            </button>

            <button>
              {t("aiManaged")}
            </button>
          </div>

          <div className="conversation-list">
            {loadingList ? (
              <div className="conversation-loading">
                <LoaderCircle
                  className="spin"
                  size={20}
                />
              </div>
            ) : (
              filteredConversations.map((item) => (
                <button
                  key={item.id}
                  className={`conversation-row ${
                    selectedId === item.id
                      ? "active"
                      : ""
                  }`}
                  onClick={() =>
                    setSelectedId(item.id)
                  }
                >
                  <div className="conversation-avatar">
                    {initials(item.name)}
                  </div>

                  <div className="conversation-row-copy">
                    <div className="conversation-row-top">
                      <strong>{item.name}</strong>
                      <span>{item.time}</span>
                    </div>

                    <div className="conversation-row-bottom">
                      <span>{item.preview}</span>

                      {item.unread > 0 && (
                        <b>{item.unread}</b>
                      )}
                    </div>
                  </div>
                </button>
              ))
            )}
          </div>
        </section>

        <section className="chat-panel">
          {loadingConversation ? (
            <div className="conversation-loading chat-loader">
              <LoaderCircle
                className="spin"
                size={28}
              />
            </div>
          ) : conversation ? (
            <>
              <header className="chat-header">
                <div className="chat-user">
                  <div className="conversation-avatar large">
                    {initials(conversation.name)}
                  </div>

                  <div>
                    <strong>
                      {conversation.name}
                    </strong>

                    <span>
                      {conversation.channel} ·{" "}
                      {conversation.phone}
                    </span>
                  </div>
                </div>

                <button
                  className={
                    conversation.mode === "human"
                      ? "secondary-button"
                      : "primary-button"
                  }
                  onClick={toggleMode}
                  disabled={changingMode}
                >
                  {changingMode ? (
                    <LoaderCircle
                      className="spin"
                      size={16}
                    />
                  ) : conversation.mode === "ai" ? (
                    <UserRound size={16} />
                  ) : (
                    <Bot size={16} />
                  )}

                  {conversation.mode === "ai"
                    ? t("takeConversation")
                    : t("returnToAI")}
                </button>
              </header>

              <div className="chat-body">
                <div className="chat-day">
                  {t("chatToday")}
                </div>

                {conversation.messages.map(
                  (item) => (
                    <div
                      key={item.id}
                      className={`message ${
                        item.sender === "customer"
                          ? "received"
                          : "sent"
                      }`}
                    >
                      {item.sender === "ai" && (
                        <div className="message-agent-label">
                          <Bot size={13} />
                          {agentLabel(
                            item.agent,
                            t,
                          )}
                        </div>
                      )}

                      {item.sender === "human" && (
                        <div className="message-agent-label">
                          <UserRound size={13} />
                          {t("humanManaged")}
                        </div>
                      )}

                      <p>{item.text}</p>
                      <span>{item.time}</span>
                    </div>
                  ),
                )}
              </div>

              {conversation.mode === "ai" && (
                <div className="ai-conversation-status">
                  <span className="status-dot" />
                  {t("aiThinking")}
                </div>
              )}

              <div className="chat-composer">
                <input
                  value={message}
                  onChange={(event) =>
                    setMessage(event.target.value)
                  }
                  onKeyDown={(event) => {
                    if (
                      event.key === "Enter" &&
                      !event.shiftKey
                    ) {
                      event.preventDefault();
                      handleSendMessage();
                    }
                  }}
                  placeholder={t("typeMessage")}
                  disabled={sendingMessage}
                />

                <button
                  className="send-button"
                  onClick={handleSendMessage}
                  disabled={
                    sendingMessage ||
                    !message.trim()
                  }
                >
                  {sendingMessage ? (
                    <LoaderCircle
                      className="spin"
                      size={18}
                    />
                  ) : (
                    <Send size={18} />
                  )}
                </button>
              </div>
            </>
          ) : (
            <div className="conversation-loading">
              <BrainCircuit size={26} />
            </div>
          )}
        </section>

        {conversation && (
          <aside className="customer-panel">
            <div className="customer-card-header">
              <div className="customer-avatar-large">
                {initials(conversation.name)}
              </div>

              <strong>
                {conversation.name}
              </strong>

              <span>
                {conversation.tags.includes(
                  "returning_customer",
                )
                  ? t("returningCustomer")
                  : t("customer")}
              </span>
            </div>

            <InfoSection
              title={t("customerInformation")}
            >
              <InfoRow
                label={t("phone")}
                value={conversation.phone}
              />

              <InfoRow
                label={t("email")}
                value={conversation.email}
              />

              <InfoRow
                label={t("country")}
                value={conversation.country_code}
              />
            </InfoSection>

            <InfoSection title={t("shopify")}>
              <div className="integration-status">
                <span className="status-dot" />
                {t("connected")}
              </div>

              <InfoRow
                label={t("orders")}
                value={String(conversation.orders)}
              />

              <InfoRow
                label={t("totalSpent")}
                value={formatMoney(
                  conversation.total_spent,
                  conversation.currency,
                )}
              />

              <InfoRow
                label={t("lastOrder")}
                value={conversation.last_order}
              />
            </InfoSection>

            <InfoSection
              title={t("currentAgent")}
            >
              <div className="current-agent-card">
                <div className="agent-icon">
                  {conversation.mode === "human" ? (
                    <UserRound size={18} />
                  ) : (
                    <Bot size={18} />
                  )}
                </div>

                <div>
                  <strong>
                    {conversation.mode === "human"
                      ? t("humanManaged")
                      : agentLabel(
                          conversation.agent,
                          t,
                        )}
                  </strong>

                  <span>
                    <span className="mini-status" />

                    {conversation.mode === "human"
                      ? t("humanActive")
                      : t("aiActive")}
                  </span>
                </div>
              </div>
            </InfoSection>

            <InfoSection title={t("tags")}>
              <div className="tag-list">
                {conversation.tags.map((tag) => (
                  <span key={tag}>
                    {tagLabel(tag, t)}
                  </span>
                ))}
              </div>
            </InfoSection>
          </aside>
        )}
      </div>
    </div>
  );
}

function initials(name: string) {
  return name
    .split(" ")
    .filter(Boolean)
    .map((part) => part[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

function formatMoney(
  value: number,
  currency: string,
) {
  return new Intl.NumberFormat(
    undefined,
    {
      style: "currency",
      currency: currency || "USD",
      maximumFractionDigits: 2,
    },
  ).format(value);
}

function agentLabel(
  agent:
    | string
    | {
        id: number;
        name: string;
        role: string;
      }
    | null
    | undefined,
  t: (key: string) => string,
) {
  if (!agent) {
    return t("salesAgent");
  }

  if (typeof agent === "object") {
    return agent.name;
  }

  switch (agent) {
    case "support":
      return t("supportAgent");

    case "orders":
      return t("ordersAgent");

    default:
      return agent || t("salesAgent");
  }
}

function tagLabel(
  tag: string,
  t: (key: string) => string,
) {
  switch (tag) {
    case "high_intent":
      return t("highIntent");

    case "returning_customer":
      return t("returningCustomer");

    case "shopify":
      return "Shopify";

    default:
      return tag;
  }
}

function InfoSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="customer-info-section">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function InfoRow({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="customer-info-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
