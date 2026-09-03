import { useTranslation } from "react-i18next";
import { useState } from "react";
import {
  History,
  Workflow,
} from "lucide-react";
import AutomationsRules from "../components/AutomationsRules";
import AutomationsExecutions from "../components/AutomationsExecutions";
import AutomationCampaigns from "../components/AutomationCampaigns";


interface AutomationsPageProps {
  canWrite: boolean;
  storeId: number;
}


type AutomationTab =
  | "rules"
  | "executions";


const TABS: {
  key: AutomationTab;
  labelKey: string;
  icon: typeof Workflow;
}[] = [
  {
    key: "rules",
    labelKey: "autoTabRules",
    icon: Workflow,
  },
  {
    key: "executions",
    labelKey: "autoTabExecutions",
    icon: History,
  },
];


export default function AutomationsPage({
  canWrite,
  storeId,
}: AutomationsPageProps) {
  const { t } = useTranslation();

  const [activeTab, setActiveTab] =
    useState<AutomationTab>("rules");

  return (
    <div className="content">
      <section className="page-heading">
        <div>
          <span className="eyebrow">
            DIAGLOB TECH
          </span>
          <h1>{t("automations")}</h1>
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
        <AutomationCampaigns canWrite={canWrite} storeId={storeId} />
        {activeTab === "rules" && (
          <AutomationsRules
            canWrite={canWrite}
            storeId={storeId}
          />
        )}

        {activeTab === "executions" && (
          <AutomationsExecutions
            canWrite={canWrite}
            storeId={storeId}
          />
        )}
      </div>
    </div>
  );
}
