import { useTranslation } from "react-i18next";
import { useEffect, useState } from "react";
import {
  LoaderCircle,
  Pencil,
  Play,
  Plus,
  Power,
  PowerOff,
  Trash2,
  X,
} from "lucide-react";
import {
  listAutomations,
  createAutomation,
  updateAutomation,
  deleteAutomation,
  toggleAutomation,
  runAutomation,
  type Automation,
  type AutomationCondition,
  type AutomationAction,
} from "../services/automations";


interface AutomationsRulesProps {
  canWrite: boolean;
}


interface AutomationFormState {
  name: string;
  description: string;
  active: boolean;
  trigger_type: string;
  conditions: AutomationCondition[];
  actions: AutomationAction[];
}


const EMPTY_FORM: AutomationFormState = {
  name: "",
  description: "",
  active: true,
  trigger_type: "manual",
  conditions: [],
  actions: [],
};


const TRIGGER_OPTIONS = [
  "manual",
  "order.created",
  "order.failed",
  "conversation.created",
  "message.received",
];


const OPERATOR_OPTIONS = [
  "eq",
  "neq",
  "gt",
  "gte",
  "lt",
  "lte",
  "contains",
  "exists",
];


const CONDITION_FIELD_OPTIONS = [
  "order.total",
  "order.source",
  "order.financial_status",
  "order.currency",
  "customer_name",
  "amount",
  "event_type",
];


const ACTION_TYPE_OPTIONS = [
  "log_event",
  "add_order_note",
];


export default function AutomationsRules({
  canWrite,
}: AutomationsRulesProps) {
  const { t } = useTranslation();

  const [automations, setAutomations] =
    useState<Automation[]>([]);

  const [loading, setLoading] =
    useState(true);

  const [error, setError] =
    useState("");

  const [modalOpen, setModalOpen] =
    useState(false);

  const [editing, setEditing] =
    useState<Automation | null>(null);

  const [form, setForm] =
    useState<AutomationFormState>(EMPTY_FORM);

  const [saving, setSaving] =
    useState(false);

  const [runModalOpen, setRunModalOpen] =
    useState(false);

  const [runningAutomation, setRunningAutomation] =
    useState<Automation | null>(null);

  const [runPayload, setRunPayload] =
    useState("{}");

  const [runResult, setRunResult] =
    useState<string | null>(null);

  const [running, setRunning] =
    useState(false);

  const [deleteConfirm, setDeleteConfirm] =
    useState<Automation | null>(null);


  useEffect(() => {
    loadData();
  }, []);


  async function loadData() {
    try {
      setLoading(true);
      setError("");

      const data =
        await listAutomations(0);

      setAutomations(data.items);
    } catch {
      setError(t("autoLoadError"));
    } finally {
      setLoading(false);
    }
  }


  function openCreate() {
    setEditing(null);
    setForm({ ...EMPTY_FORM });
    setModalOpen(true);
  }


  function openEdit(auto: Automation) {
    setEditing(auto);
    setForm({
      name: auto.name,
      description: auto.description ?? "",
      active: auto.active,
      trigger_type: auto.trigger_type,
      conditions: [...auto.conditions_json],
      actions: [...auto.actions_json],
    });
    setModalOpen(true);
  }


  function closeModal() {
    if (saving) return;
    setModalOpen(false);
    setEditing(null);
    setForm({ ...EMPTY_FORM });
  }


  async function handleSave() {
    if (!form.name.trim()) {
      setError(t("autoNameRequired"));
      return;
    }

    try {
      setSaving(true);
      setError("");

      const payload = {
        name: form.name.trim(),
        description:
          form.description.trim() || undefined,
        active: form.active,
        trigger_type: form.trigger_type,
        conditions_json: form.conditions,
        actions_json: form.actions,
      };

      if (editing) {
        await updateAutomation(
          0,
          editing.id,
          payload,
        );
      } else {
        await createAutomation(0, payload);
      }

      closeModal();
      await loadData();
    } catch {
      setError(t("autoSaveError"));
    } finally {
      setSaving(false);
    }
  }


  async function handleToggle(
    auto: Automation,
  ) {
    if (!canWrite) return;

    try {
      setError("");
      await toggleAutomation(0, auto.id);
      await loadData();
    } catch {
      setError(t("autoToggleError"));
    }
  }


  async function handleDelete() {
    if (!deleteConfirm || !canWrite) return;

    try {
      setError("");
      await deleteAutomation(
        0,
        deleteConfirm.id,
      );
      setDeleteConfirm(null);
      await loadData();
    } catch {
      setError(t("autoDeleteError"));
    }
  }


  function openRun(auto: Automation) {
    setRunningAutomation(auto);
    setRunPayload(
      JSON.stringify(
        {
          customer_name: "Test Customer",
          amount: 150000,
        },
        null,
        2,
      ),
    );
    setRunResult(null);
    setRunModalOpen(true);
  }


  function closeRunModal() {
    if (running) return;
    setRunModalOpen(false);
    setRunningAutomation(null);
    setRunResult(null);
  }


  async function handleRun() {
    if (!runningAutomation) return;

    let parsed: Record<string, any>;

    try {
      parsed = JSON.parse(runPayload);
    } catch {
      setRunResult(
        JSON.stringify(
          {
            error: "Invalid JSON payload",
          },
          null,
          2,
        ),
      );
      return;
    }

    try {
      setRunning(true);
      setRunResult(null);

      const result = await runAutomation(
        0,
        runningAutomation.id,
        {
          event_type:
            runningAutomation.trigger_type,
          payload: parsed,
        },
      );

      setRunResult(
        JSON.stringify(result, null, 2),
      );
    } catch (err: any) {
      setRunResult(
        JSON.stringify(
          {
            error:
              err?.response?.data?.detail
              ?? "Execution failed",
          },
          null,
          2,
        ),
      );
    } finally {
      setRunning(false);
    }
  }


  function addCondition() {
    setForm((prev) => ({
      ...prev,
      conditions: [
        ...prev.conditions,
        {
          field: "order.total",
          operator: "gte",
          value: 0,
        },
      ],
    }));
  }


  function updateCondition(
    index: number,
    updates: Partial<AutomationCondition>,
  ) {
    setForm((prev) => ({
      ...prev,
      conditions: prev.conditions.map(
        (c, i) =>
          i === index ? { ...c, ...updates } : c,
      ),
    }));
  }


  function removeCondition(index: number) {
    setForm((prev) => ({
      ...prev,
      conditions: prev.conditions.filter(
        (_, i) => i !== index,
      ),
    }));
  }


  function addAction() {
    setForm((prev) => ({
      ...prev,
      actions: [
        ...prev.actions,
        { type: "log_event", message: "" },
      ],
    }));
  }


  function updateAction(
    index: number,
    updates: Partial<AutomationAction>,
  ) {
    setForm((prev) => ({
      ...prev,
      actions: prev.actions.map((a, i) =>
        i === index ? { ...a, ...updates } : a,
      ),
    }));
  }


  function removeAction(index: number) {
    setForm((prev) => ({
      ...prev,
      actions: prev.actions.filter(
        (_, i) => i !== index,
      ),
    }));
  }


  if (loading) {
    return (
      <div className="commerce-loading">
        <LoaderCircle
          className="spin"
          size={24}
        />
      </div>
    );
  }


  return (
    <div className="automations-rules">
      {error && (
        <div className="commerce-error">
          {error}
        </div>
      )}

      <div className="automations-toolbar">
        {canWrite && (
          <button
            className="primary-button"
            onClick={openCreate}
          >
            <Plus size={16} />
            {t("autoNewRule")}
          </button>
        )}
      </div>

      {automations.length === 0 && (
        <div className="commerce-empty">
          <p>{t("autoNoRules")}</p>
        </div>
      )}

      {automations.length > 0 && (
        <div className="automations-grid">
          {automations.map((auto) => (
            <div
              key={auto.id}
              className={
                "automation-card"
                + (!auto.active
                  ? " inactive"
                  : "")
              }
            >
              <div className="automation-card-header">
                <div className="automation-card-info">
                  <h3>{auto.name}</h3>
                  {auto.description && (
                    <p>
                      {auto.description}
                    </p>
                  )}
                </div>

                <span
                  className={
                    "automation-trigger-badge "
                    + auto.trigger_type
                  }
                >
                  {auto.trigger_type}
                </span>
              </div>

              <div className="automation-card-meta">
                <span>
                  {t("autoConditions")}:{" "}
                  {
                    auto.conditions_json
                      .length
                  }
                </span>
                <span>
                  {t("autoActions")}:{" "}
                  {auto.actions_json.length}
                </span>
              </div>

              {auto.last_execution && (
                <div className="automation-card-execution">
                  <span className="automation-exec-label">
                    {t("autoLastRun")}:
                  </span>
                  <span
                    className={
                      "automation-exec-status "
                      + auto
                        .last_execution
                        .status
                    }
                  >
                    {
                      auto.last_execution
                        .status
                    }
                  </span>
                </div>
              )}

              <div className="automation-card-actions">
                {canWrite && (
                  <>
                    <button
                      className="icon-button"
                      title={t("autoToggle")}
                      onClick={() =>
                        handleToggle(auto)
                      }
                    >
                      {auto.active ? (
                        <Power
                          size={15}
                        />
                      ) : (
                        <PowerOff
                          size={15}
                        />
                      )}
                    </button>

                    {auto.trigger_type
                      === "manual"
                      && (
                        <button
                          className="icon-button"
                          title={t(
                            "autoRun",
                          )}
                          onClick={() =>
                            openRun(
                              auto,
                            )
                          }
                        >
                          <Play
                            size={15}
                          />
                        </button>
                      )}

                    <button
                      className="icon-button"
                      title={t("autoEdit")}
                      onClick={() =>
                        openEdit(auto)
                      }
                    >
                      <Pencil
                        size={15}
                      />
                    </button>

                    <button
                      className="icon-button danger"
                      title={t("autoDelete")}
                      onClick={() =>
                        setDeleteConfirm(
                          auto,
                        )
                      }
                    >
                      <Trash2
                        size={15}
                      />
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}


      {modalOpen && (
        <div
          className="management-modal-backdrop"
          onMouseDown={closeModal}
        >
          <div
            className="management-modal"
            onMouseDown={(e) =>
              e.stopPropagation()
            }
          >
            <header className="management-modal-header">
              <div>
                <span className="eyebrow">
                  DIAGLOB AI
                </span>
                <h2>
                  {editing
                    ? t("autoEditRule")
                    : t("autoNewRule")}
                </h2>
              </div>

              <button
                className="icon-button"
                onClick={closeModal}
              >
                <X size={18} />
              </button>
            </header>

            <div className="management-form">
              <label>
                <span>
                  {t("autoFormName")}
                </span>

                <input
                  type="text"
                  value={form.name}
                  onChange={(e) =>
                    setForm((prev) => ({
                      ...prev,
                      name: e.target.value,
                    }))
                  }
                  placeholder={t(
                    "autoFormNamePlaceholder",
                  )}
                />
              </label>

              <label>
                <span>
                  {t("autoFormDescription")}
                </span>

                <input
                  type="text"
                  value={form.description}
                  onChange={(e) =>
                    setForm((prev) => ({
                      ...prev,
                      description:
                        e.target.value,
                    }))
                  }
                  placeholder={t(
                    "autoFormDescPlaceholder",
                  )}
                />
              </label>

              <label>
                <span>
                  {t("autoFormTrigger")}
                </span>

                <select
                  value={form.trigger_type}
                  onChange={(e) =>
                    setForm((prev) => ({
                      ...prev,
                      trigger_type:
                        e.target.value,
                    }))
                  }
                >
                  {TRIGGER_OPTIONS.map(
                    (opt) => (
                      <option
                        key={opt}
                        value={opt}
                      >
                        {t(
                          "autoTrigger_"
                            + opt,
                        )}
                      </option>
                    ),
                  )}
                </select>
              </label>

              <div className="management-form-section">
                <strong>
                  {t("autoFormConditions")}
                </strong>

                {form.conditions.length
                  === 0
                  && (
                    <p className="automation-empty-note">
                      {t(
                        "autoNoConditions",
                      )}
                    </p>
                  )}

                {form.conditions.map(
                  (cond, idx) => (
                    <div
                      key={idx}
                      className="automation-condition-row"
                    >
                      <select
                        value={cond.field}
                        onChange={(e) =>
                          updateCondition(
                            idx,
                            {
                              field:
                                e.target
                                  .value,
                            },
                          )
                        }
                      >
                        {CONDITION_FIELD_OPTIONS.map(
                          (f) => (
                            <option
                              key={f}
                              value={f}
                            >
                              {f}
                            </option>
                          ),
                        )}
                      </select>

                      <select
                        value={
                          cond.operator
                        }
                        onChange={(e) =>
                          updateCondition(
                            idx,
                            {
                              operator:
                                e.target
                                  .value,
                            },
                          )
                        }
                      >
                        {OPERATOR_OPTIONS.map(
                          (o) => (
                            <option
                              key={o}
                              value={o}
                            >
                              {o}
                            </option>
                          ),
                        )}
                      </select>

                      <input
                        type="text"
                        value={
                          cond.value ?? ""
                        }
                        onChange={(e) =>
                          updateCondition(
                            idx,
                            {
                              value:
                                e.target
                                  .value,
                            },
                          )
                        }
                        placeholder={t(
                          "autoFormValue",
                        )}
                      />

                      <button
                        className="icon-button danger"
                        onClick={() =>
                          removeCondition(
                            idx,
                          )
                        }
                      >
                        <X size={14} />
                      </button>
                    </div>
                  ),
                )}

                <button
                  className="secondary-button automation-add-btn"
                  onClick={addCondition}
                >
                  <Plus size={14} />
                  {t("autoAddCondition")}
                </button>
              </div>

              <div className="management-form-section">
                <strong>
                  {t("autoFormActions")}
                </strong>

                {form.actions.length
                  === 0
                  && (
                    <p className="automation-empty-note">
                      {t("autoNoActions")}
                    </p>
                  )}

                {form.actions.map(
                  (action, idx) => (
                    <div
                      key={idx}
                      className="automation-action-row"
                    >
                      <select
                        value={action.type}
                        onChange={(e) =>
                          updateAction(
                            idx,
                            {
                              type:
                                e.target
                                  .value,
                            },
                          )
                        }
                      >
                        {ACTION_TYPE_OPTIONS.map(
                          (a) => (
                            <option
                              key={a}
                              value={a}
                            >
                              {t(
                                "autoAction_"
                                  + a,
                              )}
                            </option>
                          ),
                        )}
                      </select>

                      {action.type
                        === "log_event"
                        && (
                          <input
                            type="text"
                            value={
                              action.message
                              ?? ""
                            }
                            onChange={(
                              e,
                            ) =>
                              updateAction(
                                idx,
                                {
                                  message:
                                    e
                                      .target
                                      .value,
                                },
                              )
                            }
                            placeholder={t(
                              "autoFormLogMessage",
                            )}
                          />
                        )}

                      {action.type
                        === "add_order_note"
                        && (
                          <input
                            type="text"
                            value={
                              action.note
                              ?? ""
                            }
                            onChange={(
                              e,
                            ) =>
                              updateAction(
                                idx,
                                {
                                  note:
                                    e
                                      .target
                                      .value,
                                },
                              )
                            }
                            placeholder={t(
                              "autoFormNoteText",
                            )}
                          />
                        )}

                      <button
                        className="icon-button danger"
                        onClick={() =>
                          removeAction(idx)
                        }
                      >
                        <X size={14} />
                      </button>
                    </div>
                  ),
                )}

                <button
                  className="secondary-button automation-add-btn"
                  onClick={addAction}
                >
                  <Plus size={14} />
                  {t("autoAddAction")}
                </button>
              </div>

              <label className="toggle-row">
                <input
                  type="checkbox"
                  checked={form.active}
                  onChange={(e) =>
                    setForm((prev) => ({
                      ...prev,
                      active:
                        e.target.checked,
                    }))
                  }
                />
                <span>
                  {t("autoFormActive")}
                </span>
              </label>
            </div>

            <footer className="management-modal-actions">
              <button
                className="secondary-button"
                onClick={closeModal}
                disabled={saving}
              >
                {t("autoCancel")}
              </button>

              <button
                className="primary-button"
                onClick={handleSave}
                disabled={saving}
              >
                {saving && (
                  <LoaderCircle
                    className="spin"
                    size={16}
                  />
                )}

                {editing
                  ? t("autoSaveChanges")
                  : t("autoCreate")}
              </button>
            </footer>
          </div>
        </div>
      )}


      {runModalOpen && runningAutomation && (
        <div
          className="management-modal-backdrop"
          onMouseDown={closeRunModal}
        >
          <div
            className="management-modal"
            onMouseDown={(e) =>
              e.stopPropagation()
            }
          >
            <header className="management-modal-header">
              <div>
                <span className="eyebrow">
                  DIAGLOB AI
                </span>
                <h2>
                  {t("autoRun")}{" "}
                  {runningAutomation.name}
                </h2>
              </div>

              <button
                className="icon-button"
                onClick={closeRunModal}
              >
                <X size={18} />
              </button>
            </header>

            <div className="management-form">
              <label>
                <span>
                  {t("autoRunPayload")}
                </span>

                <textarea
                  className="automation-json-input"
                  value={runPayload}
                  onChange={(e) =>
                    setRunPayload(
                      e.target.value,
                    )
                  }
                  rows={8}
                />
              </label>

              {runResult && (
                <div className="automation-result-block">
                  <strong>
                    {t("autoRunResult")}
                  </strong>
                  <pre>{runResult}</pre>
                </div>
              )}
            </div>

            <footer className="management-modal-actions">
              <button
                className="secondary-button"
                onClick={closeRunModal}
                disabled={running}
              >
                {t("autoCancel")}
              </button>

              <button
                className="primary-button"
                onClick={handleRun}
                disabled={running}
              >
                {running && (
                  <LoaderCircle
                    className="spin"
                    size={16}
                  />
                )}
                {t("autoRunNow")}
              </button>
            </footer>
          </div>
        </div>
      )}


      {deleteConfirm && (
        <div
          className="management-modal-backdrop"
          onMouseDown={() =>
            setDeleteConfirm(null)
          }
        >
          <div
            className="management-modal management-modal-sm"
            onMouseDown={(e) =>
              e.stopPropagation()
            }
          >
            <header className="management-modal-header">
              <div>
                <span className="eyebrow">
                  DIAGLOB AI
                </span>
                <h2>{t("autoDeleteTitle")}</h2>
              </div>

              <button
                className="icon-button"
                onClick={() =>
                  setDeleteConfirm(null)
                }
              >
                <X size={18} />
              </button>
            </header>

            <div className="management-form">
              <p>
                {t("autoDeleteConfirm", {
                  name: deleteConfirm.name,
                })}
              </p>
            </div>

            <footer className="management-modal-actions">
              <button
                className="secondary-button"
                onClick={() =>
                  setDeleteConfirm(null)
                }
              >
                {t("autoCancel")}
              </button>

              <button
                className="primary-button danger-button"
                onClick={handleDelete}
              >
                {t("autoDelete")}
              </button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}
