import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  BarChart3,
  CalendarDays,
  ChevronRight,
  CircleDollarSign,
  MessageSquareText,
  ShieldCheck,
  ShoppingBag,
  Sparkles,
  TrendingUp,
  Users,
  Workflow,
} from "lucide-react";

import AnalyticsOverview from "../components/AnalyticsOverview";
import AnalyticsConversations from "../components/AnalyticsConversations";
import AnalyticsCommerce from "../components/AnalyticsCommerce";
import AnalyticsAutomations from "../components/AnalyticsAutomations";
import AnalyticsCustomerClassifications from "../components/AnalyticsCustomerClassifications";
import DropshippingOverview from "../components/DropshippingOverview";
import AdminAnalytics from "../components/AdminAnalytics";
import { getAdminStatus } from "../services/adminAnalytics";
import {
  getAnalyticsRangeDates,
  type AnalyticsQuickRange,
} from "../utils/analyticsDateRange";
import "../analytics-v2.css";

interface AnalyticsPageProps {
  canWrite: boolean;
  storeId: number;
  currency: string;
  onNavigateToStores?: () => void;
  onNavigateToIntegrations?: () => void;
}

type AnalyticsTab =
  | "overview"
  | "dropshipping"
  | "customers"
  | "conversations"
  | "commerce"
  | "automations"
  | "admin";

type LocaleKey = "es" | "en" | "pt-BR";

const BASE_TABS: {
  key: AnalyticsTab;
  labelKey: string;
  icon: typeof BarChart3;
}[] = [
  {
    key: "overview",
    labelKey: "analyticsTabOverview",
    icon: BarChart3,
  },
  {
    key: "dropshipping",
    labelKey: "analyticsTabDropshipping",
    icon: TrendingUp,
  },
  {
    key: "customers",
    labelKey: "customers",
    icon: Users,
  },
  {
    key: "conversations",
    labelKey: "analyticsTabConversations",
    icon: MessageSquareText,
  },
  {
    key: "commerce",
    labelKey: "analyticsTabCommerce",
    icon: ShoppingBag,
  },
  {
    key: "automations",
    labelKey: "analyticsTabAutomations",
    icon: Workflow,
  },
];

const COPY: Record<
  LocaleKey,
  {
    eyebrow: string;
    title: string;
    subtitle: string;
    period: string;
    customPeriod: string;
    currency: string;
    customDates: string;
    from: string;
    to: string;
    sectionDescriptions: Record<AnalyticsTab, string>;
    sectionKickers: Record<AnalyticsTab, string>;
  }
> = {
  es: {
    eyebrow: "INTELIGENCIA DE NEGOCIO",
    title: "Analytics",
    subtitle:
      "Convierte la operación diaria en decisiones: rendimiento, rentabilidad, conversaciones y automatizaciones en un solo lugar.",
    period: "Período",
    customPeriod: "Personalizado",
    currency: "Moneda",
    customDates: "Rango personalizado",
    from: "Desde",
    to: "Hasta",
    sectionDescriptions: {
      overview: "Vista ejecutiva del volumen, actividad comercial y rendimiento operativo de la tienda.",
      dropshipping: "Unit economics, tasa de entrega, utilidad y productos que realmente generan margen.",
      customers: "Valor, recompra y recencia para entender qué clientes sostienen el negocio y cuáles necesitan reactivación.",
      conversations: "Actividad conversacional y señales para entender cómo responde tu operación comercial.",
      commerce: "Comportamiento de productos y pedidos para identificar movimiento y oportunidades de venta.",
      automations: "Ejecuciones, confiabilidad y desempeño de los flujos que mantienen la operación en movimiento.",
      admin: "Métricas globales de plataforma disponibles exclusivamente para administración de Diaglob.",
    },
    sectionKickers: {
      overview: "PULSO DEL NEGOCIO",
      dropshipping: "RENTABILIDAD & ENTREGA",
      customers: "VALOR & RETENCIÓN",
      conversations: "RELACIÓN CON CLIENTES",
      commerce: "COMERCIO",
      automations: "EFICIENCIA OPERATIVA",
      admin: "PLATAFORMA",
    },
  },
  en: {
    eyebrow: "BUSINESS INTELLIGENCE",
    title: "Analytics",
    subtitle:
      "Turn daily operations into decisions: performance, profitability, conversations and automation in one place.",
    period: "Period",
    customPeriod: "Custom",
    currency: "Currency",
    customDates: "Custom range",
    from: "From",
    to: "To",
    sectionDescriptions: {
      overview: "Executive view of volume, commercial activity and operational performance for the active store.",
      dropshipping: "Unit economics, delivery rate, profit and the products that actually generate margin.",
      customers: "Value, repeat purchase and recency to understand which customers sustain the business and which need reactivation.",
      conversations: "Conversation activity and signals to understand how your commercial operation responds.",
      commerce: "Product and order behavior to identify movement and selling opportunities.",
      automations: "Executions, reliability and performance of the workflows keeping your operation moving.",
      admin: "Platform-wide metrics available exclusively to Diaglob administrators.",
    },
    sectionKickers: {
      overview: "BUSINESS PULSE",
      dropshipping: "PROFITABILITY & DELIVERY",
      customers: "VALUE & RETENTION",
      conversations: "CUSTOMER RELATIONSHIPS",
      commerce: "COMMERCE",
      automations: "OPERATIONAL EFFICIENCY",
      admin: "PLATFORM",
    },
  },
  "pt-BR": {
    eyebrow: "INTELIGÊNCIA DE NEGÓCIO",
    title: "Analytics",
    subtitle:
      "Transforme a operação diária em decisões: desempenho, rentabilidade, conversas e automações em um só lugar.",
    period: "Período",
    customPeriod: "Personalizado",
    currency: "Moeda",
    customDates: "Intervalo personalizado",
    from: "De",
    to: "Até",
    sectionDescriptions: {
      overview: "Visão executiva do volume, atividade comercial e desempenho operacional da loja ativa.",
      dropshipping: "Unit economics, taxa de entrega, lucro e os produtos que realmente geram margem.",
      customers: "Valor, recompra e recência para entender quais clientes sustentam o negócio e quais precisam de reativação.",
      conversations: "Atividade das conversas e sinais para entender a resposta da sua operação comercial.",
      commerce: "Comportamento de produtos e pedidos para identificar movimento e oportunidades de venda.",
      automations: "Execuções, confiabilidade e desempenho dos fluxos que mantêm a operação em movimento.",
      admin: "Métricas globais da plataforma disponíveis exclusivamente para administradores da Diaglob.",
    },
    sectionKickers: {
      overview: "PULSO DO NEGÓCIO",
      dropshipping: "RENTABILIDADE & ENTREGA",
      customers: "VALOR & RETENÇÃO",
      conversations: "RELACIONAMENTO COM CLIENTES",
      commerce: "COMÉRCIO",
      automations: "EFICIÊNCIA OPERACIONAL",
      admin: "PLATAFORMA",
    },
  },
};

function normalizeLocale(language: string): LocaleKey {
  if (language.toLowerCase().startsWith("pt")) return "pt-BR";
  if (language.toLowerCase().startsWith("en")) return "en";
  return "es";
}

export default function AnalyticsPage({
  canWrite: _canWrite,
  storeId,
  currency,
  onNavigateToStores,
  onNavigateToIntegrations,
}: AnalyticsPageProps) {
  const { t, i18n } = useTranslation();
  const [activeTab, setActiveTab] = useState<AnalyticsTab>("overview");
  const [isPlatformAdmin, setIsPlatformAdmin] = useState(false);
  const [quickRange, setQuickRange] = useState<AnalyticsQuickRange>("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  useEffect(() => {
    let cancelled = false;

    getAdminStatus()
      .then((status) => {
        if (!cancelled) setIsPlatformAdmin(status.platform_admin === true);
      })
      .catch(() => {
        if (!cancelled) setIsPlatformAdmin(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const locale = normalizeLocale(i18n.resolvedLanguage || i18n.language || "es");
  const copy = COPY[locale];
  const dates = getAnalyticsRangeDates(quickRange);
  const effectiveFrom = dates.from || dateFrom || undefined;
  const effectiveTo = dates.to || dateTo || undefined;

  const tabs = useMemo(
    () =>
      isPlatformAdmin
        ? [
            ...BASE_TABS,
            {
              key: "admin" as AnalyticsTab,
              labelKey: "Admin Diaglob",
              icon: ShieldCheck,
            },
          ]
        : BASE_TABS,
    [isPlatformAdmin],
  );

  const activeTabConfig = tabs.find((tab) => tab.key === activeTab) || tabs[0];
  const ActiveIcon = activeTabConfig.icon;
  const activeTabLabel =
    activeTabConfig.key === "admin" ? activeTabConfig.labelKey : t(activeTabConfig.labelKey);

  const periodLabel = (() => {
    if (dateFrom || dateTo) return copy.customPeriod;
    if (quickRange === "today") return t("analyticsRangeToday");
    if (quickRange === "7d") return t("analyticsRange7d");
    if (quickRange === "30d") return t("analyticsRange30d");
    if (quickRange === "month") return t("analyticsRangeMonth");
    return t("analyticsRangeAll");
  })();

  function handleQuickRange(range: AnalyticsQuickRange) {
    setQuickRange(range);
    setDateFrom("");
    setDateTo("");
  }

  const ranges: { key: AnalyticsQuickRange; label: string }[] = [
    { key: "", label: t("analyticsRangeAll") },
    { key: "today", label: t("analyticsRangeToday") },
    { key: "7d", label: t("analyticsRange7d") },
    { key: "30d", label: t("analyticsRange30d") },
    { key: "month", label: t("analyticsRangeMonth") },
  ];

  return (
    <div className="analytics-v2">
      <section className="analytics-v2-hero">
        <div className="analytics-v2-hero-copy">
          <div className="analytics-v2-eyebrow">
            <Sparkles size={14} />
            <span>{copy.eyebrow}</span>
          </div>
          <h1>{copy.title}</h1>
          <p>{copy.subtitle}</p>
        </div>

        <div className="analytics-v2-context">
          <div className="analytics-v2-context-card">
            <CalendarDays size={17} />
            <div>
              <span>{copy.period}</span>
              <strong>{periodLabel}</strong>
            </div>
          </div>
          <div className="analytics-v2-context-card">
            <CircleDollarSign size={17} />
            <div>
              <span>{copy.currency}</span>
              <strong>{currency}</strong>
            </div>
          </div>
        </div>
      </section>

      {activeTab !== "admin" && (
        <section className="analytics-v2-toolbar" aria-label={copy.period}>
          <div className="analytics-v2-ranges">
            {ranges.map((range) => (
              <button
                type="button"
                key={range.key || "all"}
                className={`analytics-v2-range ${quickRange === range.key && !dateFrom && !dateTo ? "is-active" : ""}`}
                onClick={() => handleQuickRange(range.key)}
                aria-pressed={quickRange === range.key && !dateFrom && !dateTo}
              >
                {range.label}
              </button>
            ))}
          </div>

          <div className="analytics-v2-date-range">
            <div className="analytics-v2-date-label">
              <CalendarDays size={15} />
              <span>{copy.customDates}</span>
            </div>
            <label>
              <span>{copy.from}</span>
              <input
                type="date"
                value={dateFrom}
                onChange={(event) => {
                  setDateFrom(event.target.value);
                  setQuickRange("");
                }}
                aria-label={t("analyticsDateFrom")}
              />
            </label>
            <ChevronRight className="analytics-v2-date-separator" size={16} />
            <label>
              <span>{copy.to}</span>
              <input
                type="date"
                value={dateTo}
                onChange={(event) => {
                  setDateTo(event.target.value);
                  setQuickRange("");
                }}
                aria-label={t("analyticsDateTo")}
              />
            </label>
          </div>
        </section>
      )}

      <section className="analytics-v2-tabs-shell">
        <div className="analytics-v2-tabs" role="tablist" aria-label={copy.title}>
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const label = tab.key === "admin" ? tab.labelKey : t(tab.labelKey);

            return (
              <button
                type="button"
                key={tab.key}
                className={`analytics-v2-tab ${activeTab === tab.key ? "is-active" : ""}`}
                onClick={() => setActiveTab(tab.key)}
                role="tab"
                aria-selected={activeTab === tab.key}
              >
                <span className="analytics-v2-tab-icon">
                  <Icon size={17} />
                </span>
                <span>{label}</span>
              </button>
            );
          })}
        </div>
      </section>

      <section className="analytics-v2-section-intro">
        <div className="analytics-v2-section-icon">
          <ActiveIcon size={20} />
        </div>
        <div>
          <span>{copy.sectionKickers[activeTab]}</span>
          <h2>{activeTabLabel}</h2>
          <p>{copy.sectionDescriptions[activeTab]}</p>
        </div>
      </section>

      <div className="analytics-v2-content">
        {activeTab === "overview" && (
          <AnalyticsOverview
            storeId={storeId}
            dateFrom={effectiveFrom}
            dateTo={effectiveTo}
          />
        )}

        {activeTab === "dropshipping" && (
          <DropshippingOverview
            storeId={storeId}
            currency={currency}
            dateFrom={effectiveFrom}
            dateTo={effectiveTo}
            onNavigateToStores={onNavigateToStores}
            onNavigateToIntegrations={onNavigateToIntegrations}
          />
        )}

        {activeTab === "customers" && (
          <AnalyticsCustomerClassifications
            storeId={storeId}
            dateFrom={effectiveFrom}
            dateTo={effectiveTo}
          />
        )}

        {activeTab === "conversations" && (
          <AnalyticsConversations
            storeId={storeId}
            dateFrom={effectiveFrom}
            dateTo={effectiveTo}
          />
        )}

        {activeTab === "commerce" && (
          <AnalyticsCommerce
            storeId={storeId}
            dateFrom={effectiveFrom}
            dateTo={effectiveTo}
          />
        )}

        {activeTab === "automations" && (
          <AnalyticsAutomations
            storeId={storeId}
            dateFrom={effectiveFrom}
            dateTo={effectiveTo}
          />
        )}

        {activeTab === "admin" && isPlatformAdmin && <AdminAnalytics />}
      </div>
    </div>
  );
}