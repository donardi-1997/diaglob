import {
  AlertTriangle,
  CheckCircle2,
  CircleDollarSign,
  PackageCheck,
  ShieldAlert,
  UserRound,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import type { CustomerRiskSummary } from "../services/customerRisk";
import type {
  ConversationMode,
  ConversationalCheckoutSummary,
} from "../types/conversation";
import "../checkout-operational-card.css";


type LocaleKey = "es" | "en" | "pt-BR";

interface Props {
  checkout?: ConversationalCheckoutSummary | null;
  risk?: CustomerRiskSummary | null;
  conversationMode: ConversationMode;
  canTakeOver: boolean;
  takingOver?: boolean;
  onTakeOver?: () => void;
}

const COPY = {
  es: {
    title: "Checkout contraentrega",
    product: "Producto",
    quantity: "Cantidad",
    total: "Total",
    address: "Dirección",
    confirmed: "Dirección confirmada",
    pendingAddress: "Dirección pendiente de confirmación",
    riskTitle: "Revisión operativa recomendada",
    riskUnavailable: "La verificación de señales compartidas no está disponible en este momento.",
    riskBody: "Hay señales preventivas asociadas a este cliente. No prueban fraude ni culpabilidad y no bloquean el pedido automáticamente.",
    organizations: "organizaciones con señales activas",
    oneOrganization: "organización con una señal activa",
    privacy: "No comuniques esta señal al cliente ni compartas identidad, notas o evidencia de otros reportantes.",
    takeOver: "Revisar manualmente",
    humanReview: "La conversación está bajo revisión humana.",
    clear: "Sin señales compartidas activas para este cliente.",
    orderCreated: "Pedido creado",
    checkoutFinished: "Checkout finalizado",
  },
  en: {
    title: "Cash-on-delivery checkout",
    product: "Product",
    quantity: "Quantity",
    total: "Total",
    address: "Address",
    confirmed: "Address confirmed",
    pendingAddress: "Address awaiting confirmation",
    riskTitle: "Operational review recommended",
    riskUnavailable: "Shared-risk verification is currently unavailable.",
    riskBody: "Preventive signals are associated with this customer. They do not establish fraud or guilt and do not automatically block the order.",
    organizations: "organizations with active signals",
    oneOrganization: "organization with an active signal",
    privacy: "Do not disclose this signal to the customer or share reporter identity, notes, or evidence from other organizations.",
    takeOver: "Review manually",
    humanReview: "The conversation is under human review.",
    clear: "No active shared signals for this customer.",
    orderCreated: "Order created",
    checkoutFinished: "Checkout finished",
  },
  "pt-BR": {
    title: "Checkout contra entrega",
    product: "Produto",
    quantity: "Quantidade",
    total: "Total",
    address: "Endereço",
    confirmed: "Endereço confirmado",
    pendingAddress: "Endereço aguardando confirmação",
    riskTitle: "Revisão operacional recomendada",
    riskUnavailable: "A verificação de sinais compartilhados não está disponível no momento.",
    riskBody: "Há sinais preventivos associados a este cliente. Eles não comprovam fraude ou culpa e não bloqueiam o pedido automaticamente.",
    organizations: "organizações com sinais ativos",
    oneOrganization: "organização com um sinal ativo",
    privacy: "Não comunique este sinal ao cliente nem compartilhe identidade, notas ou evidências de outros relatores.",
    takeOver: "Revisar manualmente",
    humanReview: "A conversa está sob revisão humana.",
    clear: "Sem sinais compartilhados ativos para este cliente.",
    orderCreated: "Pedido criado",
    checkoutFinished: "Checkout finalizado",
  },
} as const;

const STATUS_COPY: Record<LocaleKey, Record<string, string>> = {
  es: {
    collecting_variant: "Seleccionando variante",
    collecting_quantity: "Confirmando cantidad",
    collecting_name: "Recopilando nombre",
    collecting_phone: "Recopilando teléfono",
    collecting_region: "Recopilando departamento/estado",
    collecting_city: "Recopilando ciudad",
    collecting_address: "Recopilando dirección",
    collecting_neighborhood: "Recopilando barrio",
    collecting_address_complement: "Recopilando complemento",
    awaiting_address_confirmation: "Esperando confirmación de dirección",
    collecting_delivery_reference: "Recopilando referencia de entrega",
    awaiting_order_confirmation: "Esperando CONFIRMO",
    creating_order: "Creando pedido",
    order_created: "Pedido creado",
    cancelled: "Cancelado",
    failed: "Fallido",
    expired: "Expirado",
  },
  en: {
    collecting_variant: "Selecting variant",
    collecting_quantity: "Confirming quantity",
    collecting_name: "Collecting name",
    collecting_phone: "Collecting phone",
    collecting_region: "Collecting state/region",
    collecting_city: "Collecting city",
    collecting_address: "Collecting address",
    collecting_neighborhood: "Collecting neighborhood",
    collecting_address_complement: "Collecting address complement",
    awaiting_address_confirmation: "Awaiting address confirmation",
    collecting_delivery_reference: "Collecting delivery reference",
    awaiting_order_confirmation: "Awaiting CONFIRM",
    creating_order: "Creating order",
    order_created: "Order created",
    cancelled: "Cancelled",
    failed: "Failed",
    expired: "Expired",
  },
  "pt-BR": {
    collecting_variant: "Selecionando variante",
    collecting_quantity: "Confirmando quantidade",
    collecting_name: "Coletando nome",
    collecting_phone: "Coletando telefone",
    collecting_region: "Coletando estado/região",
    collecting_city: "Coletando cidade",
    collecting_address: "Coletando endereço",
    collecting_neighborhood: "Coletando bairro",
    collecting_address_complement: "Coletando complemento",
    awaiting_address_confirmation: "Aguardando confirmação do endereço",
    collecting_delivery_reference: "Coletando referência de entrega",
    awaiting_order_confirmation: "Aguardando CONFIRMO",
    creating_order: "Criando pedido",
    order_created: "Pedido criado",
    cancelled: "Cancelado",
    failed: "Falhou",
    expired: "Expirado",
  },
};

const TERMINAL_STATUSES = new Set([
  "order_created",
  "cancelled",
  "failed",
  "expired",
]);

function resolveLocale(language?: string): LocaleKey {
  const normalized = (language || "es").toLowerCase();
  if (normalized.startsWith("en")) return "en";
  if (normalized.startsWith("pt")) return "pt-BR";
  return "es";
}

function formatMoney(value: number | null, currency: string) {
  if (value == null) return "—";
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: currency || "USD",
      maximumFractionDigits: 2,
    }).format(value);
  } catch {
    return `${currency || ""} ${value.toFixed(2)}`.trim();
  }
}

export default function CheckoutOperationalCard({
  checkout,
  risk,
  conversationMode,
  canTakeOver,
  takingOver = false,
  onTakeOver,
}: Props) {
  const { i18n } = useTranslation();
  const locale = resolveLocale(i18n.resolvedLanguage || i18n.language);
  const copy = COPY[locale];

  if (!checkout) return null;

  const statusLabel = STATUS_COPY[locale][checkout.status] || checkout.status;
  const terminal = TERMINAL_STATUSES.has(checkout.status);
  const riskUnavailable = !risk || risk.available === false;
  const hasRisk = Boolean(risk?.available && risk.alert);
  const reportingOrganizations = risk?.reporting_organizations ?? 0;
  const address = [
    checkout.address_line,
    checkout.neighborhood,
    checkout.city,
    checkout.region,
  ].filter(Boolean).join(", ");

  return (
    <section
      className={`checkout-operational-card ${
        hasRisk ? "has-risk" : ""
      } ${terminal ? "is-terminal" : ""}`}
      aria-label={copy.title}
    >
      <div className="checkout-operational-header">
        <div className="checkout-operational-title">
          <PackageCheck size={17} />
          <div>
            <strong>{copy.title}</strong>
            <span>{statusLabel}</span>
          </div>
        </div>

        {checkout.status === "order_created" && (
          <span className="checkout-operational-success">
            <CheckCircle2 size={14} />
            {copy.orderCreated}
          </span>
        )}
      </div>

      {!terminal && (riskUnavailable || hasRisk) && (
        <div
          className={`checkout-risk-review ${
            riskUnavailable ? "unavailable" : ""
          }`}
          role="status"
        >
          <div className="checkout-risk-review-heading">
            {riskUnavailable ? (
              <AlertTriangle size={17} />
            ) : (
              <ShieldAlert size={17} />
            )}
            <strong>{copy.riskTitle}</strong>
          </div>

          <p>{riskUnavailable ? copy.riskUnavailable : copy.riskBody}</p>

          {hasRisk && (
            <>
              <span className="checkout-risk-count">
                {reportingOrganizations} {reportingOrganizations === 1
                  ? copy.oneOrganization
                  : copy.organizations}
              </span>
              <small>{copy.privacy}</small>
            </>
          )}

          {hasRisk && conversationMode === "ai" && canTakeOver && onTakeOver && (
            <button
              type="button"
              className="checkout-risk-takeover"
              onClick={onTakeOver}
              disabled={takingOver}
            >
              <UserRound size={15} />
              {copy.takeOver}
            </button>
          )}

          {hasRisk && conversationMode === "human" && (
            <span className="checkout-human-review">
              <UserRound size={14} />
              {copy.humanReview}
            </span>
          )}
        </div>
      )}

      {!terminal && !riskUnavailable && !hasRisk && (
        <div className="checkout-risk-clear">
          <CheckCircle2 size={15} />
          {copy.clear}
        </div>
      )}

      <div className="checkout-operational-grid">
        <div>
          <span>{copy.product}</span>
          <strong>
            {checkout.product_title || "—"}
            {checkout.variant_title ? ` · ${checkout.variant_title}` : ""}
          </strong>
        </div>
        <div>
          <span>{copy.quantity}</span>
          <strong>{checkout.quantity}</strong>
        </div>
        <div>
          <span>{copy.total}</span>
          <strong className="checkout-total">
            <CircleDollarSign size={14} />
            {formatMoney(checkout.total, checkout.currency)}
          </strong>
        </div>
      </div>

      <div className="checkout-address-state">
        <span>{copy.address}</span>
        <strong>
          {checkout.address_confirmed ? copy.confirmed : copy.pendingAddress}
        </strong>
        {address && <small>{address}</small>}
      </div>

      {terminal && checkout.status !== "order_created" && (
        <small className="checkout-terminal-note">{copy.checkoutFinished}</small>
      )}
    </section>
  );
}
