import { useTranslation } from "react-i18next";
import { useState } from "react";
import {
  LayoutDashboard,
  Package,
  ShoppingBag,
} from "lucide-react";
import CommerceSummary from "../components/CommerceSummary";
import CommerceProducts from "../components/CommerceProducts";
import CommerceOrders from "../components/CommerceOrders";


interface CommercePageProps {
  canWrite: boolean;
  storeId: number;
}


type CommerceTab =
  | "summary"
  | "products"
  | "orders";


const TABS: {
  key: CommerceTab;
  labelKey: string;
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


export default function CommercePage({
  canWrite,
  storeId,
}: CommercePageProps) {
  const { t } = useTranslation();

  const [activeTab, setActiveTab] =
    useState<CommerceTab>("summary");

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
        {TABS.map((tab) => {
          const Icon = tab.icon;

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
              {t(tab.labelKey)}
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
          />
        )}

        {activeTab === "orders" && (
          <CommerceOrders
            storeId={storeId}
            canWrite={canWrite}
          />
        )}
      </div>
    </div>
  );
}
