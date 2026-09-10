import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  BrainCircuit,
  Check,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  HelpCircle,
  MessageSquare,
  ShoppingBag,
  Store as StoreIcon,
  Workflow,
} from "lucide-react";

import { type Store } from "../services/stores";
import {
  getCommerceStatus,
  getWhatsAppStatus,
  type CommerceConnectionStatus,
  type WhatsAppConnectionStatus,
} from "../services/integrations";

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
  onNavigateToWhatsApp,
  onNavigateToKnowledge,
  onNavigateToAutomations,
}: GettingStartedProps) {
  const { t } = useTranslation();
  const [commerceStatus, setCommerceStatus] = useState<CommerceConnectionStatus | null>(null);
  const [whatsappStatus, setWhatsAppStatus] = useState<WhatsAppConnectionStatus | null>(null);
  const [hasKnowledge, setHasKnowledge] = useState(false);
  const [hasAutomations, setHasAutomations] = useState(false);
  const [connectionsLoading, setConnectionsLoading] = useState(true);
  const [workspaceLoading, setWorkspaceLoading] = useState(true);
  const [dismissed, setDismissed] = useState(
    localStorage.getItem("diaglob-onboarding-dismissed") === "true",
  );

  const hasStores = stores.length > 0;
  const onNavigateToIntegrations = onNavigateToWhatsApp;

  useEffect(() => {
    if (!selectedStoreId) {
      setCommerceStatus(null);
      setWhatsappStatus(null);
      setConnectionsLoading(false);
      return;
    }

    let mounted = true;
    setConnectionsLoading(true);

    Promise.all([
      getCommerceStatus(selectedStoreId).catch(() => null),
      getWhatsAppStatus(selectedStoreId).catch(() => null),
    ]).then(([commerce, whatsapp]) => {
      if (!mounted) return;
      setCommerceStatus(commerce);
      setWhatsappStatus(whatsapp);
      setConnectionsLoading(false);
    });

    return () => {
      mounted = false;
    };
  }, [selectedStoreId]);

  useEffect(() => {
    if (!selectedStoreId) {
      setHasKnowledge(false);
      setHasAutomations(false);
      setWorkspaceLoading(false);
      return;
    }

    let mounted = true;
    setWorkspaceLoading(true);

    Promise.all([
      import("../services/knowledgeBases")
        .then(({ getKnowledgeBases }) => getKnowledgeBases())
        .then((data: { items: unknown[] }) => Boolean(data.items?.length))
        .catch(() => false),
      import("../services/automations")
        .then(({ listAutomations }) => listAutomations(selectedStoreId))
        .then((data: { items: unknown[] }) => Boolean(data.items?.length))
        .catch(() => false),
    ]).then(([knowledgeReady, automationsReady]) => {
      if (!mounted) return;
      setHasKnowledge(knowledgeReady);
      setHasAutomations(automationsReady);
      setWorkspaceLoading(false);
    });

    return () => {
      mounted = false;
    };
  }, [selectedStoreId]);

  const commerceConnected = commerceStatus?.connected ?? false;
  const whatsappConnected = whatsappStatus?.connected ?? false;

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
      key: "commerce",
      icon: ShoppingBag,
      titleKey: "onboardingStepShopify",
      helpKey: "onboardingStepShopifyHelp",
      actionKey: "onboardingStepShopifyAction",
      action: onNavigateToIntegrations,
      isComplete: commerceConnected,
      isCore: true,
      isLoading: connectionsLoading,
    },
    {
      key: "whatsapp",
      icon: MessageSquare,
      titleKey: "onboardingStepWhatsApp",
      helpKey: "onboardingStepWhatsAppHelp",
      actionKey: "onboardingStepWhatsAppAction",
      action: onNavigateToIntegrations,
      isComplete: whatsappConnected,
      isCore: true,
      isLoading: connectionsLoading,
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
      isLoading: workspaceLoading,
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
      isLoading: workspaceLoading,
    },
  ];

  const coreSteps = steps.filter((step) => step.isCore);
  const advancedSteps = steps.filter((step) => !step.isCore);
  const completedCount = steps.filter((step) => step.isComplete).length;
  const coreCompletedCount = coreSteps.filter((step) => step.isComplete).length;
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

  if (dismissed) {
    return (
      <button
        className="onboarding-show-button"
        onClick={handleShow}
        aria-label={t("onboardingShowGuide")}
      >
        {allComplete ? <Check size={14} /> : <HelpCircle size={14} />}
        <span>{t("onboardingShowGuide")}</span>
      </button>
    );
  }

  if (allComplete) {
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
        <div className="getting-started-step-title">{t(step.titleKey)}</div>
        <div className="getting-started-step-help">{t(step.helpKey)}</div>
        {!step.isComplete && !step.isLoading && (
          <button className="getting-started-step-action" onClick={step.action}>
            {t(step.actionKey)}
            <ChevronRight size={14} />
          </button>
        )}
        {step.key === "commerce" && !step.isComplete && (
          <div className="getting-started-step-hint">
            {t("onboardingStepShopifyHint")}
          </div>
        )}
      </div>
    </div>
  );
}
