import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Check,
  ChevronRight,
  ExternalLink,
  HelpCircle,
  Loader2,
  MessageCircle,
  AlertTriangle,
  ShoppingBag,
  BrainCircuit,
  Bot,
} from "lucide-react";

import { getWhatsAppStatus, listCommerceProducts, type WhatsAppConnectionStatus } from "../services/integrations";
import { getConversations } from "../services/conversations";
import type { ConversationSummary } from "../types/conversation";


interface WhatsAppActivationGuideProps {
  storeId: number;
  onViewConversation: (conversationId: number) => void;
  onNavigateToCommerce: () => void;
  onNavigateToKnowledge: () => void;
}


type ActivationStep =
  | "requirements"
  | "connected"
  | "test"
  | "success";


export default function WhatsAppActivationGuide({
  storeId,
  onViewConversation,
  onNavigateToCommerce,
  onNavigateToKnowledge,
}: WhatsAppActivationGuideProps) {
  const { t } = useTranslation();

  const [whatsappStatus, setWhatsAppStatus] = useState<WhatsAppConnectionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [polling, setPolling] = useState(false);
  const [hasProducts, setHasProducts] = useState(false);
  const [hasKnowledge, setHasKnowledge] = useState(false);
  const [foundAiConversation, setFoundAiConversation] = useState<ConversationSummary | null>(null);
  const [dismissed, setDismissed] = useState(
    localStorage.getItem(`diaglob-wa-dismissed-${storeId}`) === "true",
  );

  // Load WhatsApp status and context
  useEffect(() => {
    if (!storeId) {
      setLoading(false);
      return;
    }

    let mounted = true;

    Promise.all([
      getWhatsAppStatus(storeId).catch(() => null),
      listCommerceProducts(storeId).catch(() => ({ items: [], total: 0 })),
    ]).then(([whatsapp, products]) => {
      if (mounted) {
        setWhatsAppStatus(whatsapp);
        setHasProducts(products.total > 0);
        setLoading(false);
      }
    });

    // Check knowledge
    import("../services/knowledgeBases").then(({ getKnowledgeBases }) => {
      getKnowledgeBases()
        .then((data) => {
          if (mounted) setHasKnowledge(data.items && data.items.length > 0);
        })
        .catch(() => {
          if (mounted) setHasKnowledge(false);
        });
    });

    return () => {
      mounted = false;
    };
  }, [storeId]);

  const whatsappConnected = whatsappStatus?.connected ?? false;

  // Poll for conversations when connected and waiting for test
  useEffect(() => {
    if (!whatsappConnected || !storeId || dismissed) return;

    let mounted = true;
    let interval: ReturnType<typeof setInterval> | null = null;

    const checkConversations = async () => {
      try {
        const data = await getConversations();
        if (!mounted) return;

        // Check if any conversation has AI mode and recent activity
        const aiConversation = (data.items || []).find(
          (c) => c.mode === "ai" && c.store?.id === storeId
        );

        if (aiConversation) {
          setFoundAiConversation(aiConversation);
          setPolling(false);
          if (interval) clearInterval(interval);
        }
      } catch {
        // Silently handle polling errors
      }
    };

    // Initial check
    checkConversations();

    // Poll every 5 seconds for up to 5 minutes
    setPolling(true);
    interval = setInterval(checkConversations, 5000);

    // Stop polling after 5 minutes
    const timeout = setTimeout(() => {
      setPolling(false);
      if (interval) clearInterval(interval);
    }, 300000);

    return () => {
      mounted = false;
      if (interval) clearInterval(interval);
      clearTimeout(timeout);
    };
  }, [whatsappConnected, storeId, dismissed]);

  if (loading) {
    return null;
  }

  // Determine current step
  const currentStep: ActivationStep = !whatsappConnected
    ? "requirements"
    : foundAiConversation
      ? "success"
      : polling
        ? "test"
        : "connected";

  const handleDismiss = () => {
    setDismissed(true);
    localStorage.setItem(`diaglob-wa-dismissed-${storeId}`, "true");
  };

  // If dismissed and connected, don't show anything
  if (dismissed && whatsappConnected) {
    return null;
  }

  return (
    <div className="wa-activation-guide">
      {/* Requirements step */}
      {currentStep === "requirements" && (
        <div className="wa-guide-section">
          <div className="wa-guide-header">
            <MessageCircle size={18} />
            <h4>{t("waGuideTitle")}</h4>
          </div>
          <p className="wa-guide-subtitle">{t("waGuideSubtitle")}</p>

          <div className="wa-requirements">
            <h5>{t("waRequirementsTitle")}</h5>
            <ul>
              <li><Check size={14} /> {t("waRequirement1")}</li>
              <li><Check size={14} /> {t("waRequirement2")}</li>
              <li><Check size={14} /> {t("waRequirement3")}</li>
              <li><Check size={14} /> {t("waRequirement4")}</li>
            </ul>
          </div>

          <div className="wa-credentials-guide">
            <h5>{t("waCredentialsTitle")}</h5>
            <div className="wa-credential-items">
              <div className="wa-credential-item">
                <strong>{t("waCredentialPhoneId")}</strong>
                <p>{t("waCredentialPhoneIdHelp")}</p>
              </div>
              <div className="wa-credential-item">
                <strong>{t("waCredentialBizId")}</strong>
                <p>{t("waCredentialBizIdHelp")}</p>
              </div>
              <div className="wa-credential-item">
                <strong>{t("waCredentialToken")}</strong>
                <p>{t("waCredentialTokenHelp")}</p>
              </div>
            </div>
            <a
              href="https://business.facebook.com"
              target="_blank"
              rel="noopener noreferrer"
              className="wa-meta-link"
            >
              {t("waCredentialMetaLink")}
              <ExternalLink size={12} />
            </a>
          </div>

          <p className="wa-connect-hint">{t("waConnectHelp")}</p>

          {/* Support fallback */}
          <div className="wa-support-fallback">
            <HelpCircle size={14} />
            <span>{t("onboardingSupportHelp")}</span>
            <a
              href={import.meta.env.VITE_SUPPORT_URL || "#"}
              target="_blank"
              rel="noopener noreferrer"
            >
              {t("onboardingSupportAction")}
              <ExternalLink size={12} />
            </a>
          </div>
        </div>
      )}

      {/* Connected step */}
      {currentStep === "connected" && (
        <div className="wa-guide-section wa-guide-success">
          <div className="wa-guide-header">
            <Check size={18} className="wa-check-icon" />
            <h4>{t("waConnectedTitle")}</h4>
          </div>
          <p className="wa-guide-subtitle">{t("waConnectedHelp")}</p>

          {whatsappStatus?.phone_number_id && (
            <div className="wa-connected-info">
              <span className="wa-phone-label">Phone Number ID:</span>
              <code>{whatsappStatus.phone_number_id}</code>
            </div>
          )}

          {/* Test prompt */}
          <div className="wa-test-prompt">
            <h5>{t("waTestTitle")}</h5>
            <p>{t("waTestHelp")}</p>
            <div className="wa-test-example">
              <MessageCircle size={14} />
              <span>{t("waTestExample")}</span>
            </div>
          </div>

          {/* Context tips */}
          <div className="wa-context-tips">
            {!hasProducts && (
              <div className="wa-context-tip warning">
                <AlertTriangle size={14} />
                <span>{t("waCatalogWarning")}</span>
                <button onClick={onNavigateToCommerce}>
                  {t("waCatalogAction")}
                </button>
              </div>
            )}
            {hasProducts && (
              <div className="wa-context-tip info">
                <ShoppingBag size={14} />
                <span>AI puede usar tu catálogo de productos para responder.</span>
              </div>
            )}
            {!hasKnowledge && (
              <div className="wa-context-tip info">
                <BrainCircuit size={14} />
                <span>{t("waKnowledgeTip")}</span>
                <button onClick={onNavigateToKnowledge}>
                  {t("waKnowledgeAction")}
                </button>
              </div>
            )}
          </div>

          {/* Support fallback */}
          <div className="wa-support-fallback">
            <HelpCircle size={14} />
            <span>{t("onboardingSupportHelp")}</span>
            <a
              href={import.meta.env.VITE_SUPPORT_URL || "#"}
              target="_blank"
              rel="noopener noreferrer"
            >
              {t("onboardingSupportAction")}
              <ExternalLink size={12} />
            </a>
          </div>
        </div>
      )}

      {/* Test waiting step */}
      {currentStep === "test" && (
        <div className="wa-guide-section">
          <div className="wa-guide-header">
            <Loader2 size={18} className="spin" />
            <h4>{t("waTestWaiting")}</h4>
          </div>
          <p className="wa-guide-subtitle">{t("waTestHelp")}</p>
          <div className="wa-test-example">
            <MessageCircle size={14} />
            <span>{t("waTestExample")}</span>
          </div>

          {/* Context tips */}
          <div className="wa-context-tips">
            {!hasProducts && (
              <div className="wa-context-tip warning">
                <AlertTriangle size={14} />
                <span>{t("waCatalogWarning")}</span>
                <button onClick={onNavigateToCommerce}>
                  {t("waCatalogAction")}
                </button>
              </div>
            )}
            {hasProducts && (
              <div className="wa-context-tip info">
                <ShoppingBag size={14} />
                <span>AI puede usar tu catálogo de productos para responder.</span>
              </div>
            )}
            {!hasKnowledge && (
              <div className="wa-context-tip info">
                <BrainCircuit size={14} />
                <span>{t("waKnowledgeTip")}</span>
                <button onClick={onNavigateToKnowledge}>
                  {t("waKnowledgeAction")}
                </button>
              </div>
            )}
          </div>

          {/* Support fallback */}
          <div className="wa-support-fallback">
            <HelpCircle size={14} />
            <span>{t("onboardingSupportHelp")}</span>
            <a
              href={import.meta.env.VITE_SUPPORT_URL || "#"}
              target="_blank"
              rel="noopener noreferrer"
            >
              {t("onboardingSupportAction")}
              <ExternalLink size={12} />
            </a>
          </div>
        </div>
      )}

      {/* Success step */}
      {currentStep === "success" && foundAiConversation && (
        <div className="wa-guide-section wa-guide-success">
          <div className="wa-guide-header">
            <Bot size={18} className="wa-check-icon" />
            <h4>{t("waTestSuccess")}</h4>
          </div>
          <p className="wa-guide-subtitle">{t("waTestSuccessHelp")}</p>

          <div className="wa-success-details">
            <div className="wa-success-item">
              <MessageCircle size={14} />
              <span>{t("waTestReceived")}</span>
            </div>
            <div className="wa-success-item">
              <Bot size={14} />
              <span>{t("waTestAiReply")}</span>
            </div>
          </div>

          <button
            className="wa-view-conversation"
            onClick={() => onViewConversation(foundAiConversation.id)}
          >
            {t("waTestViewConversation")}
            <ChevronRight size={14} />
          </button>

          {/* Context info */}
          <div className="wa-context-tips">
            {hasProducts && (
              <div className="wa-context-tip info">
                <ShoppingBag size={14} />
                <span>AI usa tu catálogo para responder preguntas de productos.</span>
              </div>
            )}
            {hasKnowledge && (
              <div className="wa-context-tip info">
                <BrainCircuit size={14} />
                <span>AI usa tu base de conocimiento para respuestas más precisas.</span>
              </div>
            )}
          </div>

          <button
            className="getting-started-dismiss"
            onClick={handleDismiss}
          >
            {t("onboardingDismiss")}
          </button>
        </div>
      )}
    </div>
  );
}
