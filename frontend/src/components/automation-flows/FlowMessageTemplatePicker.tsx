import { useEffect, useMemo, useState } from "react";

import {
  listWhatsAppTemplates,
  type WhatsAppMessageTemplate,
} from "../../services/automations";
import type { FlowNodeConfig } from "./flowGraphUtils";
import {
  FLOW_TEMPLATE_VARIABLES,
  previewTemplateBody,
  resizeTemplateMapping,
  templateBodyText,
  templateConfigIssue,
  templateParameterCount,
} from "./flowWhatsAppTemplates";

interface Props {
  storeId: number;
  nodeId: string;
  config: FlowNodeConfig;
  canWrite: boolean;
  onUpdate: (nodeId: string, config: Partial<FlowNodeConfig>) => void;
  t: (key: string) => string;
}

type LoadState = "loading" | "ready" | "error";

export default function FlowMessageTemplatePicker({
  storeId,
  nodeId,
  config,
  canWrite,
  onUpdate,
  t,
}: Props) {
  const [templates, setTemplates] = useState<WhatsAppMessageTemplate[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");

  useEffect(() => {
    let active = true;
    if (!storeId) {
      return () => { active = false; };
    }
    void listWhatsAppTemplates(storeId)
      .then((data) => {
        if (!active) return;
        setTemplates(data.items);
        setLoadState("ready");
      })
      .catch(() => {
        if (!active) return;
        setTemplates([]);
        setLoadState("error");
      });
    return () => { active = false; };
  }, [storeId]);

  const mode = config.message_mode || "auto";
  const selected = useMemo(
    () => templates.find((item) => item.id === config.whatsapp_template_id) ?? null,
    [templates, config.whatsapp_template_id],
  );
  const mapping = config.template_variables?.body ?? [];
  const body = templateBodyText(selected);
  const issue = loadState === "ready" ? templateConfigIssue(config, selected) : null;

  function selectTemplate(rawId: string) {
    if (!canWrite) return;
    const template = templates.find((item) => item.id === Number(rawId));
    if (!template) {
      onUpdate(nodeId, {
        whatsapp_template_id: undefined,
        template_variables: undefined,
        template_provider_name: undefined,
        template_language: undefined,
      });
      return;
    }
    onUpdate(nodeId, {
      whatsapp_template_id: template.id,
      template_provider_name: template.provider_template_name,
      template_language: template.language_code,
      template_variables: {
        body: resizeTemplateMapping(mapping, templateParameterCount(template)),
      },
    });
  }

  function setParameter(index: number, variable: string) {
    if (!canWrite) return;
    const next = [...mapping];
    next[index] = variable;
    onUpdate(nodeId, { template_variables: { body: next } });
  }

  const helpKey = mode === "template"
    ? "flowWaTemplateHelpTemplate"
    : mode === "free_form"
      ? "flowWaTemplateHelpFreeForm"
      : "flowWaTemplateHelpAuto";

  return (
    <>
      <small className="flow-field-hint">{t(helpKey)}</small>

      {mode !== "free_form" && (
        <>
          <label>
            <span>{t("flowWaTemplate")}</span>
            <select
              value={config.whatsapp_template_id ?? ""}
              onChange={(event) => selectTemplate(event.target.value)}
              disabled={!canWrite || loadState !== "ready"}
            >
              <option value="">
                {loadState === "loading" ? t("flowWaTemplateLoading") : t("flowWaTemplateNone")}
              </option>
              {templates.map((template) => (
                <option
                  key={template.id}
                  value={template.id}
                  disabled={template.status !== "approved"}
                >
                  {template.provider_template_name} · {template.language_code}
                  {template.status !== "approved" ? ` · ${template.status}` : ""}
                </option>
              ))}
            </select>
          </label>

          {loadState === "error" && (
            <small className="flow-field-hint" role="alert">{t("flowWaTemplateLoadError")}</small>
          )}
          {loadState === "ready" && templates.length === 0 && (
            <small className="flow-field-hint">{t("flowWaTemplateEmpty")}</small>
          )}

          {selected && mapping.map((variable, index) => (
            <label key={`param-${index}`}>
              <span>{`${t("flowWaTemplateParam")} {{${index + 1}}}`}</span>
              <select
                value={variable}
                onChange={(event) => setParameter(index, event.target.value)}
                disabled={!canWrite}
              >
                {FLOW_TEMPLATE_VARIABLES.map((item) => (
                  <option key={item} value={item}>{`{{${item}}}`}</option>
                ))}
              </select>
            </label>
          ))}

          {selected && body && (
            <div className="flow-field-hint">
              <strong>{t("flowWaTemplatePreview")}</strong>
              <p style={{ margin: "4px 0 0", whiteSpace: "pre-wrap" }}>
                {previewTemplateBody(body, mapping)}
              </p>
            </div>
          )}
        </>
      )}

      {issue && (
        <small className="flow-field-hint" role="alert" style={{ color: "var(--danger, #c2410c)" }}>
          {t(`flowWaIssue_${issue}`)}
        </small>
      )}
    </>
  );
}
