import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Check,
  ChevronRight,
  Loader2,
  AlertTriangle,
  ShoppingCart,
  Truck,
  Heart,
  Sparkles,
  AlertCircle,
  Star,
  Workflow,
  Clock,
  ShieldCheck,
} from "lucide-react";

import { api } from "../services/api";
import { templateGraphSteps } from "../utils/automationTemplateFlow";
import type { ModelWhatsAppSetup } from "../utils/automationModelSetup";
import AutomationModelSetupDialog from "./AutomationModelSetupDialog";
import "./automation-template-preview.css";


interface AutomationTemplate {
  id: string;
  name: string;
  description: string;
  category: string;
  recommended_for: string;
  recommended_role?: string;
  graph: Record<string, unknown>;
  required_integrations: string[];
  icon: string;
  estimated_setup_minutes: number;
  trigger_type?: string | null;
  trigger_mode?: "automatic" | "manual";
  whatsapp_setup?: ModelWhatsAppSetup;
  availability: {
    available: boolean;
    missing: string[];
    status: string;
  };
}


interface AutomationTemplatesProps {
  canWrite: boolean;
  storeId: number;
  onFlowCreated: (flowId: number) => void;
}


const ICON_MAP: Record<string, typeof Workflow> = {
  "cart": ShoppingCart,
  "check-circle": Check,
  "heart": Heart,
  "sparkles": Sparkles,
  "user-check": Star,
  "alert-triangle": AlertCircle,
  "truck": Truck,
  "shield": ShieldCheck,
  "workflow": Workflow,
};


const CATEGORY_LABELS: Record<string, string> = {
  "Sales": "autoTemplateCategorySales",
  "Orders": "autoTemplateCategoryOrders",
  "Customer Retention": "autoTemplateCategoryRetention",
  "Retention": "autoTemplateCategoryRetention",
  "Operations": "autoTemplateCategoryOperations",
  "Post-sales": "autoTemplateCategoryPostSales",
  "Intelligence": "autoTemplateCategoryIntelligence",
};


export default function AutomationTemplates({
  canWrite,
  storeId,
  onFlowCreated,
}: AutomationTemplatesProps) {
  const { t } = useTranslation();

  const [templates, setTemplates] = useState<AutomationTemplate[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [setupModel, setSetupModel] = useState<AutomationTemplate | null>(null);
  const mountedStore = useRef({ storeId, active: true });

  useEffect(() => {
    mountedStore.current = { storeId, active: true };
    return () => { mountedStore.current.active = false; };
  }, [storeId]);

  useEffect(() => {
    loadTemplates();
  }, [storeId, selectedCategory]);

  async function loadTemplates() {
    try {
      setLoading(true);
      setError("");

      const params = selectedCategory
        ? `?category=${encodeURIComponent(selectedCategory)}`
        : "";

      const response = await api.get(
        `/api/stores/${storeId}/automation-flow-templates${params}`,
      );

      const data = response.data;
      setTemplates(data.items || []);
      setCategories(data.categories || []);
    } catch {
      setError(t("autoLoadError"));
    } finally {
      setLoading(false);
    }
  }

  function openSetup(template: AutomationTemplate) {
    if (!canWrite || !template.availability?.available) return;
    setError("");
    setSuccess("");
    setSetupModel(template);
  }

  function handleCreated(flowId: number, activated: boolean) {
    setSetupModel(null);
    if (!mountedStore.current.active || mountedStore.current.storeId !== storeId) return;
    if (activated) setSuccess(t("autoModelActivatedSuccess"));
    onFlowCreated(flowId);
  }

  return (
    <div className="automation-templates">
      {/* Category filters */}
      <div className="template-categories">
        <button
          className={`template-category ${selectedCategory === null ? "active" : ""}`}
          onClick={() => setSelectedCategory(null)}
        >
          {t("autoTemplateCategoryAll") || "All"}
        </button>
        {categories.map((cat) => (
          <button
            key={cat}
            className={`template-category ${selectedCategory === cat ? "active" : ""}`}
            onClick={() => setSelectedCategory(cat)}
          >
            {t(CATEGORY_LABELS[cat] || cat) || cat}
          </button>
        ))}
      </div>

      {/* Status messages */}
      {error && (
        <div className="stores-alert error">
          <AlertTriangle size={15} />
          {error}
        </div>
      )}

      {success && (
        <div className="stores-alert success">
          <Check size={15} />
          {success}
        </div>
      )}

      {/* Templates grid */}
      {loading ? (
        <div className="template-loading">
          <Loader2 className="spin" size={20} />
          <span>{t("commonLoading") || "Loading..."}</span>
        </div>
      ) : templates.length === 0 ? (
        <div className="template-empty">
          <Workflow size={32} />
          <h4>{t("autoTemplateEmptyTitle") || "No templates found"}</h4>
          <p>{t("autoTemplateEmptyHelp") || "Try a different category."}</p>
        </div>
      ) : (
        <div className="template-grid">
          {templates.map((template) => {
            const Icon = ICON_MAP[template.icon] || Workflow;
            const isAvailable = template.availability?.available;
            const expanded = previewId === template.id;
            const steps = templateGraphSteps(template.graph);

            return (
              <div
                key={template.id}
                className={`template-card ${!isAvailable ? "unavailable" : ""}`}
              >
                <div className="template-card-header">
                  <div className="template-icon">
                    <Icon size={20} />
                  </div>
                  <div className="template-meta">
                    <h3>{template.name}</h3>
                    <span className="template-category-label">
                      {t(CATEGORY_LABELS[template.category] || template.category) || template.category}
                    </span>
                  </div>
                </div>

                <p className="template-description">
                  {template.description}
                </p>

                <div className="template-details">
                  <div className="template-detail">
                    <Clock size={12} />
                    <span>
                      {template.estimated_setup_minutes} {t("autoTemplateMinutes") || "min"}
                    </span>
                  </div>

                  {template.trigger_mode && (
                    <span
                      className={`template-integration ${template.trigger_mode === "automatic" ? "connected" : "missing"}`}
                      title={template.trigger_mode === "automatic" ? t("autoModelAutomaticHint") : t("autoModelManual")}
                    >
                      {template.trigger_mode === "automatic" ? t("autoModelBadgeAutomatic") : t("autoModelBadgeManual")}
                    </span>
                  )}

                  {template.required_integrations.length > 0 && (
                    <div className="template-integrations">
                      {template.required_integrations.map((integ) => (
                        <span key={integ} className={`template-integration ${isAvailable ? "connected" : "missing"}`}>
                          {integ}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {!isAvailable && template.availability?.missing && (
                  <div className="template-missing">
                    <AlertTriangle size={14} />
                    <span>
                      {t("autoTemplateRequires") || "Requires"}:{" "}
                      {template.availability.missing.join(", ")}
                    </span>
                  </div>
                )}

                {steps.length > 0 && (
                  <>
                    <button
                      type="button"
                      className="template-preview-toggle"
                      aria-expanded={expanded}
                      aria-controls={`template-preview-${template.id}`}
                      onClick={() => setPreviewId(expanded ? null : template.id)}
                    >
                      {expanded ? t("autoTemplateHideSteps") : t("autoTemplateShowSteps")}
                    </button>
                    {expanded && (
                      <ol className="template-preview-steps" id={`template-preview-${template.id}`}>
                        {steps.map((step, index) => (
                          <li key={`${template.id}-${index}`}>{t(`autoTemplateStep_${step}`)}</li>
                        ))}
                      </ol>
                    )}
                  </>
                )}

                {canWrite && (
                  <button
                    className="template-create-button"
                    onClick={() => openSetup(template)}
                    disabled={!isAvailable || setupModel !== null}
                  >
                    <ChevronRight size={14} />
                    {t("autoModelUse")}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {setupModel && (
        <AutomationModelSetupDialog
          storeId={storeId}
          model={setupModel}
          onClose={() => setSetupModel(null)}
          onCreated={handleCreated}
        />
      )}
    </div>
  );
}
