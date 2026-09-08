import { useEffect, useState } from "react";
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
} from "lucide-react";

import { api } from "../services/api";


interface AutomationTemplate {
  id: string;
  name: string;
  description: string;
  category: string;
  recommended_for: string;
  trigger: { type: string };
  actions: Array<{
    type: string;
    delay_seconds?: number;
    message?: string;
  }>;
  required_integrations: string[];
  optional_integrations: string[];
  supported_store_types: string[];
  version: number;
  icon: string;
  estimated_setup_minutes: number;
  availability: {
    available: boolean;
    missing: string[];
    status: string;
  };
}


interface AutomationTemplatesProps {
  canWrite: boolean;
  storeId: number;
}


const ICON_MAP: Record<string, typeof Workflow> = {
  "cart": ShoppingCart,
  "check-circle": Check,
  "heart": Heart,
  "sparkles": Sparkles,
  "user-check": Star,
  "alert-triangle": AlertCircle,
  "truck": Truck,
  "workflow": Workflow,
};


const CATEGORY_LABELS: Record<string, string> = {
  "Sales": "autoTemplateCategorySales",
  "Orders": "autoTemplateCategoryOrders",
  "Customer Retention": "autoTemplateCategoryRetention",
  "Operations": "autoTemplateCategoryOperations",
};


export default function AutomationTemplates({
  canWrite,
  storeId,
}: AutomationTemplatesProps) {
  const { t } = useTranslation();

  const [templates, setTemplates] = useState<AutomationTemplate[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

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
        `/api/stores/${storeId}/automation-templates${params}`,
      );

      const data = response.data;
      setTemplates(data.items || []);
      setCategories(data.categories || []);
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ||
          err?.message ||
          "Could not load templates"
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateTemplate(templateId: string) {
    if (!canWrite) return;

    try {
      setCreating(templateId);
      setError("");
      setSuccess("");

      await api.post(
        `/api/stores/${storeId}/automation-templates`,
        { template_id: templateId },
      );

      setSuccess(t("autoTemplateCreated"));
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      if (typeof detail === "object" && detail.code === "TEMPLATE_INTEGRATION_REQUIRED") {
        setError(
          t("autoTemplateMissingIntegration") +
          ": " + (detail.missing || []).join(", ")
        );
      } else {
        setError(
          detail?.message ||
            detail ||
            err?.message ||
            "Could not create automation"
        );
      }
    } finally {
      setCreating(null);
    }
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
            const isCreating = creating === template.id;

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

                {canWrite && (
                  <button
                    className="template-create-button"
                    onClick={() => handleCreateTemplate(template.id)}
                    disabled={!isAvailable || isCreating}
                  >
                    {isCreating ? (
                      <Loader2 className="spin" size={14} />
                    ) : (
                      <ChevronRight size={14} />
                    )}
                    {isCreating
                      ? (t("autoTemplateCreating") || "Creating...")
                      : (t("autoTemplateCreate") || "Create automation")}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
