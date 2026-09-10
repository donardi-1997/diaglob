import { useTranslation } from "react-i18next";
import { useEffect, useMemo, useState } from "react";
import {
  CreditCard,
  LayoutDashboard,
  Package,
  ShoppingBag,
} from "lucide-react";
import CommerceSummary from "../components/CommerceSummary";
import CommerceProducts from "../components/CommerceProducts";
import CommerceOrders from "../components/CommerceOrders";
import PixPaymentsPanel from "../components/PixPaymentsPanel";
import { getPaymentProviders } from "../services/payments";


interface CommercePageProps {
  canWrite: boolean;
  storeId: number;
  searchKind?: "product" | "order";
  searchEntityId?: number;
  searchQuery?: string;
  searchRequestKey?: number;
}


type CommerceTab =
  | "summary"
  | "products"
  | "orders"
  | "payments";


const BASE_TABS: {
  key: CommerceTab;
  labelKey: string;
  fallbackLabel?: string;
  icon: typeof LayoutDashboard;
}[] = [
  {
    key: "summary",
    labelKey: "commerceTabSummary",
    icon: LayoutDashboard,
  },
  {
    key: "products",
    labelKey: "commerceTabProducts",
    icon: Package,
  },
  {
    key: "orders",
    labelKey: "commerceTabOrders",
    icon: ShoppingBag,
  },
];


const PIX_TAB = {
  key: "payments" as const,
  labelKey: "commerceTabPayments",
  fallbackLabel: "Pagos",
  icon: CreditCard,
};


export default function CommercePage({
  canWrite,
  storeId,
  searchKind,
  searchEntityId,
  searchQuery,
  searchRequestKey,
}: CommercePageProps) {
  const { t } = useTranslation();

  const [activeTab, setActiveTab] =
    useState<CommerceTab>("summary");

  const [pixAvailable, setPixAvailable] =
    useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadPaymentAvailability() {
      try {
        const result = await getPaymentProviders(storeId);
        const available = result.providers.some(
          (provider) =>
            provider.code === "mercado_pago"
            && provider.payment_methods.includes("pix"),
        );

        if (!cancelled) {
          setPixAvailable(available);
          if (!available) {
            setActiveTab((current) =>
              current === "payments" ? "summary" : current
            );
          }
        }
      } catch {
        if (!cancelled) {
          setPixAvailable(false);
          setActiveTab((current) =>
            current === "payments" ? "summary" : current
          );
        }
      }
    }

    void loadPaymentAvailability();

    return () => {
      cancelled = true;
    };
  }, [storeId]);

  useEffect(() => {
    if (searchKind === "product") {
      setActiveTab("products");
    } else if (searchKind === "order") {
      setActiveTab("orders");
    }
  }, [searchKind, searchEntityId, searchRequestKey]);

  const tabs = useMemo(
    () => pixAvailable
      ? [...BASE_TABS, PIX_TAB]
      : BASE_TABS,
    [pixAvailable],
  );

  return (
    <div className="content">
      <section className="page-heading">
        <div>
          <span className="eyebrow">
            DIAGLOB TECH
          </span>
          <h1>{t("commerce")}</h1>
        </div>
      </section>

      <div className="commerce-tabs">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const translated = t(tab.labelKey);
          const label = translated === tab.labelKey
            ? (tab.fallbackLabel || translated)
            : translated;

          return (
            <button
              key={tab.key}
              className={
                "commerce-tab"
                + (activeTab === tab.key
                  ? " active"
                  : "")
              }
              onClick={() =>
                setActiveTab(tab.key)
              }
            >
              <Icon size={16} />
              {label}
            </button>
          );
        })}
      </div>

      <div className="commerce-content">
        {activeTab === "summary" && (
          <CommerceSummary
            storeId={storeId}
            canWrite={canWrite}
          />
        )}

        {activeTab === "products" && (
          <CommerceProducts
            storeId={storeId}
            canWrite={canWrite}
            initialSearchQuery={searchKind === "product" ? searchQuery : undefined}
            searchRequestKey={searchKind === "product" ? searchRequestKey : undefined}
          />
        )}

        {activeTab === "orders" && (
          <CommerceOrders
            storeId={storeId}
            canWrite={canWrite}
            initialOrderId={searchKind === "order" ? searchEntityId : undefined}
            searchRequestKey={searchKind === "order" ? searchRequestKey : undefined}
          />
        )}

        {activeTab === "payments" && pixAvailable && (
          <PixPaymentsPanel
            storeId={storeId}
            canWrite={canWrite}
          />
        )}
      </div>
    </div>
  );
}
