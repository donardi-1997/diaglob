import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Check,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  HelpCircle,
  Package,
  ShoppingBag,
  MessageSquare,
  BrainCircuit,
  Workflow,
  Store as StoreIcon,
} from "lucide-react";

import { type Store } from "../services/stores";
import { getCommerceStatus, type CommerceConnectionStatus } from "../services/integrations";
import { getWhatsAppStatus, type WhatsAppConnectionStatus } from "../services/integrations";
import { listCommerceProducts } from "../services/integrations";


interface Step {
  key: string;
  icon: typeof StoreIcon;
  titleKey: string;
  helpKey: string;
  actionKey: string;
  action: () => void;
  isComplete: boolean;
  isCore: boolean;
  isLoading: boolean;
}


interface GettingStartedProps {
  stores: Store[];
  selectedStoreId: number | null;
  onNavigateToStores: () => void;
  onNavigateToCommerce: () => void;
  onNavigateToWhatsApp: () => void;
  onNavigateToKnowledge: () => void;
  onNavigateToAutomations: () => void;
}


export default function GettingStarted({
  stores,
  selectedStoreId,
  onNavigateToStores,
  onNavigateToCommerce,
  onNavigateToWhatsApp,
  onNavigateToKnowledge,
  onNavigateToAutomations,
}: GettingStartedProps) {
  const { t } = useTranslation();

  const [shopifyStatus, setShopifyStatus] = useState<CommerceConnectionStatus | null>(null);
  const [whatsappStatus, setWhatsAppStatus] = useState<WhatsAppConnectionStatus | null>(null);
  const [productCount, setProductCount] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [dismissed, setDismissed] = useState(
    localStorage.getItem("diaglob-onboarding-dismissed") === "true",
  );

  const hasStores = stores.length > 0;

  useEffect(() => {
    if (!selectedStoreId) {
      setShopifyStatus(null);
      setWhatsAppStatus(null);
      setProductCount(0);
      setLoading(false);
      return;
    }

    let mounted = true;
    setLoading(true);

    Promise.all([
      getCommerceStatus(selectedStoreId).catch(() => null),
      getWhatsAppStatus(selectedStoreId).catch(() => null),
      listCommerceProducts(selectedStoreId).catch(() => ({ items: [], total: 0 })),
    ]).then(([commerce, whatsapp, products]) => {
      if (mounted) {
        setShopifyStatus(commerce);
        setWhatsAppStatus(whatsapp);
        setProductCount(products.total);
        setLoading(false);
      }
    });

    return () => {
      mounted = false;
    };
  }, [selectedStoreId]);

  const shopifyConnected = shopifyStatus?.connected ?? false;
  const whatsappConnected = whatsappStatus?.connected ?? false;
  const hasProducts = productCount > 0;

  // Check knowledge and automation state from existing APIs
  const [hasKnowledge, setHasKnowledge] = useState(false);
  const [hasAutomations, setHasAutomations] = useState(false);

  useEffect(() => {
    if (!selectedStoreId) {
      setHasKnowledge(false);
      setHasAutomations(false);
      return;
    }

    let mounted = true;

    // Check knowledge by trying to list knowledge bases
    import("../services/knowledgeBases").then(({ getKnowledgeBases }) => {
      getKnowledgeBases()
        .then((data: { items: unknown[] }) => {
          if (mounted) {
            setHasKnowledge(data.items && data.items.length > 0);
          }
        })
        .catch(() => {
          if (mounted) setHasKnowledge(false);
        });
    });

    // Check automations by trying to list automations
    import("../services/automations").then(({ listAutomations }) => {
      listAutomations(selectedStoreId)
        .then((data: { items: unknown[] }) => {
          if (mounted) {
            setHasAutomations(data.items && data.items.length > 0);
          }
        })
        .catch(() => {
          if (mounted) setHasAutomations(false);
        });
    });

    return () => {
      mounted = false;
    };
  }, [selectedStoreId]);

  const steps: Step[] = [
    {
      key: "store",
      icon: StoreIcon,
      titleKey: "onboardingStepStore",
      helpKey: "onboardingStepStoreHelp",
      actionKey: "onboardingStepStoreAction",
      action: onNavigateToStores,
      isComplete: hasStores,
      isCore: true,
      isLoading: false,
    },
    {
      key: "shopify",
      icon: ShoppingBag,
      titleKey: "onboardingStepShopify",
      helpKey: "onboardingStepShopifyHelp",
      actionKey: "onboardingStepShopifyAction",
      action: onNavigateToCommerce,
      isComplete: shopifyConnected,
      isCore: true,
      isLoading: loading,
    },
    {
      key: "catalog",
      icon: Package,
      titleKey: "onboardingStepCatalog",
      helpKey: "onboardingStepCatalogHelp",
      actionKey: "onboardingStepCatalogAction",
      action: onNavigateToCommerce,
      isComplete: hasProducts,
      isCore: true,
      isLoading: loading,
    },
    {
      key: "whatsapp",
      icon: MessageSquare,
      titleKey: "onboardingStepWhatsApp",
      helpKey: "onboardingStepWhatsAppHelp",
      actionKey: "onboardingStepWhatsAppAction",
      action: onNavigateToWhatsApp,
      isComplete: whatsappConnected,
      isCore: true,
      isLoading: loading,
    },
    {
      key: "knowledge",
      icon: BrainCircuit,
      titleKey: "onboardingStepKnowledge",
      helpKey: "onboardingStepKnowledgeHelp",
      actionKey: "onboardingStepKnowledgeAction",
      action: onNavigateToKnowledge,
      isComplete: hasKnowledge,
      isCore: false,
      isLoading: loading,
    },
    {
      key: "automation",
      icon: Workflow,
      titleKey: "onboardingStepAutomation",
      helpKey: "onboardingStepAutomationHelp",
      actionKey: "onboardingStepAutomationAction",
      action: onNavigateToAutomations,
      isComplete: hasAutomations,
      isCore: false,
      isLoading: loading,
    },
  ];

  const coreSteps = steps.filter((s) => s.isCore);
  const advancedSteps = steps.filter((s) => !s.isCore);
  const completedCount = steps.filter((s) => s.isComplete).length;
  const coreCompletedCount = coreSteps.filter((s) => s.isComplete).length;
  const allCoreComplete = coreCompletedCount === coreSteps.length;
  const allComplete = completedCount === steps.length;

  const handleDismiss = () => {
    setDismissed(true);
    localStorage.setItem("diaglob-onboarding-dismissed", "true");
  };

  const handleShow = () => {
    setDismissed(false);
    localStorage.removeItem("diaglob-onboarding-dismissed");
  };

  // If all complete and dismissed, show minimal re-show button
  if (allComplete && dismissed) {
    return (
      <button
        className="onboarding-show-button"
        onClick={handleShow}
        aria-label={t("onboardingShowGuide")}
      >
        <Check size={14} />
        <span>{t("onboardingShowGuide")}</span>
      </button>
    );
  }

  // If all complete but not dismissed, show success state
  if (allComplete && !dismissed) {
    return (
      <div className="getting-started getting-started--complete">
        <div className="getting-started-header">
          <div className="getting-started-title">
            <Check size={18} className="getting-started-check" />
            <h3>{t("onboardingComplete")}</h3>
          </div>
          <button
            className="getting-started-dismiss"
            onClick={handleDismiss}
            aria-label={t("onboardingDismiss")}
          >
            {t("onboardingDismiss")}
          </button>
        </div>
        <p className="getting-started-subtitle">{t("onboardingCompleteHelp")}</p>
      </div>
    );
  }

  return (
    <div className="getting-started">
      <div className="getting-started-header">
        <div className="getting-started-title">
          <h3>{t("onboardingTitle")}</h3>
          <span className="getting-started-progress">
            {t("onboardingProgress", { done: completedCount, total: steps.length })}
          </span>
        </div>
        <button
          className="getting-started-dismiss"
          onClick={handleDismiss}
          aria-label={t("onboardingDismiss")}
        >
          {t("onboardingDismiss")}
        </button>
      </div>
      <p className="getting-started-subtitle">{t("onboardingSubtitle")}</p>

      {/* Core steps */}
      <div className="getting-started-steps">
        {coreSteps.map((step, index) => (
          <StepItem
            key={step.key}
            step={step}
            isLast={index === coreSteps.length - 1 && advancedSteps.length === 0}
            t={t}
          />
        ))}
      </div>

      {/* Advanced steps */}
      {allCoreComplete && advancedSteps.length > 0 && (
        <div className="getting-started-advanced">
          <div className="getting-started-advanced-label">
            <ChevronDown size={14} />
            <span>{t("onboardingSubtitle")}</span>
          </div>
          <div className="getting-started-steps">
            {advancedSteps.map((step, index) => (
              <StepItem
                key={step.key}
                step={step}
                isLast={index === advancedSteps.length - 1}
                t={t}
              />
            ))}
          </div>
        </div>
      )}

      {/* WhatsApp assisted fallback */}
      {!whatsappConnected && selectedStoreId && (
        <div className="getting-started-support">
          <HelpCircle size={14} />
          <span>{t("onboardingStepWhatsAppAssisted")}</span>
          <a
            href={import.meta.env.VITE_SUPPORT_URL || "#"}
            target="_blank"
            rel="noopener noreferrer"
            className="getting-started-support-link"
          >
            {t("onboardingStepWhatsAppAssistedAction")}
            <ExternalLink size={12} />
          </a>
        </div>
      )}
    </div>
  );
}


function StepItem({
  step,
  isLast,
  t,
}: {
  step: Step;
  isLast: boolean;
  t: (key: string) => string;
}) {
  const Icon = step.icon;
  const isNext = !step.isComplete;

  return (
    <div
      className={`getting-started-step ${step.isComplete ? "completed" : ""} ${isNext ? "next" : ""}`}
    >
      <div className="getting-started-step-indicator">
        {step.isComplete ? (
          <div className="getting-started-step-check">
            <Check size={14} />
          </div>
        ) : step.isLoading ? (
          <div className="getting-started-step-loading" />
        ) : (
          <Icon size={16} />
        )}
        {!isLast && <div className="getting-started-step-line" />}
      </div>
      <div className="getting-started-step-content">
        <div className="getting-started-step-title">
          {t(step.titleKey)}
        </div>
        <div className="getting-started-step-help">
          {t(step.helpKey)}
        </div>
        {!step.isComplete && !step.isLoading && (
          <button
            className="getting-started-step-action"
            onClick={step.action}
          >
            {t(step.actionKey)}
            <ChevronRight size={14} />
          </button>
        )}
        {step.key === "shopify" && !step.isComplete && (
          <div className="getting-started-step-hint">
            {t("onboardingStepShopifyHint")}
          </div>
        )}
      </div>
    </div>
  );
}
