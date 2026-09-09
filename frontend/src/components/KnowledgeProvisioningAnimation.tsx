import { useTranslation } from "react-i18next";
import { useEffect, useState, useRef } from "react";
import {
  BrainCircuit,
  Check,
  LoaderCircle,
  AlertCircle,
  Database,
  HardDrive,
  BookOpen,
  Link2,
  Sparkles,
} from "lucide-react";

import type {
  KnowledgeBase,
  KnowledgeBaseProvisioningStage,
} from "../services/knowledgeBases";

interface KnowledgeProvisioningAnimationProps {
  knowledgeBase: KnowledgeBase;
  onComplete: () => void;
  onRetry: () => void;
  onClose: () => void;
}

const PROVISIONING_STEPS: {
  stage: KnowledgeBaseProvisioningStage;
  icon: typeof Database;
  i18nKey: string;
}[] = [
  {
    stage: "queued",
    icon: HardDrive,
    i18nKey: "knowledgeI18nProvisioningAnimationStepPreparing",
  },
  {
    stage: "creating_vector_index",
    icon: Database,
    i18nKey: "knowledgeI18nProvisioningAnimationStepStorage",
  },
  {
    stage: "creating_knowledge_base",
    icon: BookOpen,
    i18nKey: "knowledgeI18nProvisioningAnimationStepKnowledge",
  },
  {
    stage: "creating_data_source",
    icon: Link2,
    i18nKey: "knowledgeI18nProvisioningAnimationStepSources",
  },
  {
    stage: "finalizing",
    icon: Sparkles,
    i18nKey: "knowledgeI18nProvisioningAnimationStepFinalizing",
  },
];

function getStepIndex(
  stage: KnowledgeBaseProvisioningStage | null,
): number {
  if (!stage) return 0;
  const index = PROVISIONING_STEPS.findIndex(
    (step) => step.stage === stage,
  );
  return index >= 0 ? index : 0;
}

export default function KnowledgeProvisioningAnimation({
  knowledgeBase,
  onComplete,
  onRetry,
  onClose,
}: KnowledgeProvisioningAnimationProps) {
  const { t } = useTranslation();
  const [showSuccess, setShowSuccess] = useState(false);
  const hasCalledComplete = useRef(false);

  const currentStepIndex = getStepIndex(
    knowledgeBase.provisioning_stage,
  );

  const isReady =
    knowledgeBase.external_status === "ready";
  const isFailed =
    knowledgeBase.external_status === "failed";
  const isRetrying =
    knowledgeBase.external_status === "retrying";
  const isProvisioning =
    knowledgeBase.external_status === "pending" ||
    knowledgeBase.external_status === "provisioning" ||
    isRetrying;

  useEffect(() => {
    if (isReady && !hasCalledComplete.current) {
      hasCalledComplete.current = true;
      setShowSuccess(true);
      const timer = setTimeout(() => {
        onComplete();
      }, 1500);
      return () => clearTimeout(timer);
    }
  }, [isReady, onComplete]);

  return (
    <div
      className="knowledge-provisioning-animation"
      role="dialog"
      aria-modal="true"
      aria-labelledby="knowledge-provisioning-title"
    >
      <div className="knowledge-provisioning-animation-content">
        {/* Animated Brain Icon */}
        <div className="knowledge-provisioning-animation-icon">
          <div className="knowledge-provisioning-animation-icon-ring" />
          <div className="knowledge-provisioning-animation-icon-ring knowledge-provisioning-animation-icon-ring-delay" />
          <BrainCircuit size={32} />
        </div>

        {/* Title */}
        <h2 id="knowledge-provisioning-title">
          {showSuccess
            ? t("knowledgeI18nProvisioningAnimationSuccess")
            : isFailed
              ? t("knowledgeI18nProvisioningAnimationFailed")
              : t("knowledgeI18nProvisioningAnimationTitle")}
        </h2>

        {/* Knowledge Base Name */}
        <p className="knowledge-provisioning-animation-name">
          "{knowledgeBase.name}"
        </p>

        {/* Steps */}
        <div
          className="knowledge-provisioning-animation-steps"
          role="list"
          aria-label={t(
            "knowledgeI18nProvisioningAnimationTitle",
          )}
        >
          {PROVISIONING_STEPS.map((step, index) => {
            const StepIcon = step.icon;
            const isCompleted = index < currentStepIndex;
            const isCurrent =
              index === currentStepIndex &&
              isProvisioning;

            return (
              <div
                key={step.stage}
                className={`knowledge-provisioning-animation-step ${
                  isCompleted
                    ? "completed"
                    : isCurrent
                      ? "current"
                      : "pending"
                }`}
                role="listitem"
                aria-current={
                  isCurrent ? "step" : undefined
                }
              >
                <div className="knowledge-provisioning-animation-step-indicator">
                  {isCompleted ? (
                    <Check size={14} />
                  ) : isCurrent ? (
                    <LoaderCircle
                      className="spin"
                      size={14}
                    />
                  ) : (
                    <StepIcon size={14} />
                  )}
                </div>

                <span>
                  {t(step.i18nKey)}
                </span>
              </div>
            );
          })}
        </div>

        {/* Status Messages */}
        {showSuccess && (
          <p className="knowledge-provisioning-animation-success-message">
            {t(
              "knowledgeI18nProvisioningAnimationSuccessBody",
              { name: knowledgeBase.name },
            )}
          </p>
        )}

        {isFailed && (
          <div className="knowledge-provisioning-animation-failure">
            <AlertCircle size={16} />
            <p>
              {t(
                "knowledgeI18nProvisioningAnimationFailedBody",
              )}
            </p>
            <button
              className="primary-button"
              onClick={onRetry}
            >
              {t("knowledgeI18nRetryProvisioning")}
            </button>
          </div>
        )}

        {isProvisioning && !showSuccess && (
          <p className="knowledge-provisioning-animation-subtitle">
            {isRetrying
              ? t(
                  "knowledgeI18nProvisioningAnimationStepRetrying",
                )
              : t(
                  "knowledgeI18nProvisioningAnimationSubtitle",
                )}
          </p>
        )}

        {/* Close button for failed state */}
        {isFailed && (
          <button
            className="secondary-button knowledge-provisioning-animation-close"
            onClick={onClose}
          >
            {t("knowledgeI18nCancel")}
          </button>
        )}
      </div>
    </div>
  );
}
