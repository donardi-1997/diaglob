import { useTranslation } from "react-i18next";
import { useEffect, useState, useRef, useCallback } from "react";
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
  knowledgeBase: KnowledgeBase | null;
  creatingName: string | null;
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

const LOCAL_STAGE_TIMINGS = [0, 1200, 2500, 3800, 5100];

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
  creatingName,
  onComplete,
  onRetry,
  onClose,
}: KnowledgeProvisioningAnimationProps) {
  const { t } = useTranslation();
  const [showSuccess, setShowSuccess] = useState(false);
  const hasCalledComplete = useRef(false);
  const [localStepIndex, setLocalStepIndex] = useState(0);
  const timerRefs = useRef<number[]>([]);
  const creationStartTime = useRef(Date.now());
  const hasReconciled = useRef(false);

  const isCreating = creatingName !== null && knowledgeBase === null;
  const displayName = knowledgeBase?.name ?? creatingName ?? "";

  const currentStepIndex = isCreating
    ? localStepIndex
    : getStepIndex(knowledgeBase?.provisioning_stage ?? null);

  const isReady =
    knowledgeBase?.external_status === "ready" || showSuccess;
  const isFailed =
    knowledgeBase?.external_status === "failed";
  const isRetrying =
    knowledgeBase?.external_status === "retrying";
  const isProvisioning =
    isCreating ||
    knowledgeBase?.external_status === "pending" ||
    knowledgeBase?.external_status === "provisioning" ||
    isRetrying;

  const clearAllTimers = useCallback(() => {
    timerRefs.current.forEach((id) => clearTimeout(id));
    timerRefs.current = [];
  }, []);

  useEffect(() => {
    if (!isCreating) {
      clearAllTimers();
      return;
    }

    creationStartTime.current = Date.now();
    setLocalStepIndex(0);

    const timers: number[] = [];

    for (let i = 1; i < LOCAL_STAGE_TIMINGS.length; i++) {
      const timer = window.setTimeout(() => {
        setLocalStepIndex(i);
      }, LOCAL_STAGE_TIMINGS[i]);
      timers.push(timer);
    }

    timerRefs.current = timers;

    return () => {
      timers.forEach((id) => clearTimeout(id));
    };
  }, [isCreating, clearAllTimers]);

  useEffect(() => {
    if (!knowledgeBase || hasReconciled.current) return;

    hasReconciled.current = true;
    clearAllTimers();

    const backendIndex = getStepIndex(
      knowledgeBase.provisioning_stage,
    );

    const elapsed = Date.now() - creationStartTime.current;
    const fastResponse = elapsed < 3000;

    if (
      knowledgeBase.external_status === "ready" ||
      knowledgeBase.external_status === "failed"
    ) {
      setLocalStepIndex(PROVISIONING_STEPS.length - 1);
      return;
    }

    if (fastResponse) {
      let step = localStepIndex;
      const advanceStep = () => {
        step++;
        if (step <= backendIndex) {
          setLocalStepIndex(step);
          const timer = window.setTimeout(advanceStep, 150);
          timerRefs.current.push(timer);
        }
      };
      if (step < backendIndex) {
        const timer = window.setTimeout(advanceStep, 150);
        timerRefs.current.push(timer);
      }
    } else {
      setLocalStepIndex((prev) => Math.max(prev, backendIndex));
    }
  }, [knowledgeBase, clearAllTimers, localStepIndex]);

  useEffect(() => {
    if (isReady && !hasCalledComplete.current) {
      hasCalledComplete.current = true;
      setLocalStepIndex(PROVISIONING_STEPS.length - 1);
      setShowSuccess(true);
      const timer = setTimeout(() => {
        onComplete();
      }, 1200);
      return () => clearTimeout(timer);
    }
  }, [isReady, onComplete]);

  useEffect(() => {
    return () => {
      clearAllTimers();
    };
  }, [clearAllTimers]);

  const displayStepIndex = isReady
    ? PROVISIONING_STEPS.length
    : currentStepIndex;

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
          &ldquo;{displayName}&rdquo;
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
            const isCompleted = index < displayStepIndex;
            const isCurrent =
              index === displayStepIndex &&
              isProvisioning &&
              !isReady;

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

                <span aria-live={isCurrent ? "polite" : undefined}>
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
              { name: displayName },
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

        {isProvisioning && !showSuccess && !isFailed && (
          <p className="knowledge-provisioning-animation-subtitle">
            {isRetrying
              ? t(
                  "knowledgeI18nProvisioningAnimationStepRetrying",
                )
              : displayStepIndex >= PROVISIONING_STEPS.length - 1
                ? t("knowledgeI18nProvisioningAnimationSlowMessage")
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
