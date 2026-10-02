import { useTranslation } from "react-i18next";
import { useEffect, useState } from "react";
import {
  Bot,
  BrainCircuit,
  LoaderCircle,
  Pencil,
  Plus,
  Store as StoreIcon,
  X,
} from "lucide-react";

import {
  createAgent,
  getAgents,
  getWorkforceCatalog,
  updateAgent,
  type Agent,
  type WorkforceRole,
} from "../services/agents";

import {
  getKnowledgeBases,
  type KnowledgeBase,
} from "../services/knowledgeBases";

import {
  type Store,
} from "../services/stores";
import "../workforce-catalog.css";


interface AgentsPageProps {
  stores: Store[];
  canWrite: boolean;
}


interface AgentFormState {
  name: string;
  role: string;
  active: boolean;
  store_ids: number[];
  knowledge_base_ids: number[];
}


const EMPTY_FORM: AgentFormState = {
  name: "",
  role: "sales",
  active: true,
  store_ids: [],
  knowledge_base_ids: [],
};


export default function AgentsPage({
  stores,
  canWrite,
}: AgentsPageProps) {
  const { t } = useTranslation();
  const [agents, setAgents] =
    useState<Agent[]>([]);

  const [workforceRoles, setWorkforceRoles] =
    useState<WorkforceRole[]>([]);

  const [knowledgeBases, setKnowledgeBases] =
    useState<KnowledgeBase[]>([]);

  const [loading, setLoading] =
    useState(true);

  const [saving, setSaving] =
    useState(false);

  const [error, setError] =
    useState("");

  const [modalOpen, setModalOpen] =
    useState(false);

  const [editingAgent, setEditingAgent] =
    useState<Agent | null>(null);

  const [form, setForm] =
    useState<AgentFormState>(
      EMPTY_FORM,
    );


  useEffect(() => {
    loadData();
  }, []);


  async function loadData() {
    try {
      setLoading(true);
      setError("");

      const [
        agentsResponse,
        knowledgeResponse,
        workforceResponse,
      ] = await Promise.all([
        getAgents(),
        getKnowledgeBases(),
        getWorkforceCatalog(),
      ]);

      setAgents(
        agentsResponse.items,
      );

      setKnowledgeBases(
        knowledgeResponse.items,
      );

      setWorkforceRoles(
        workforceResponse.roles,
      );
    } catch (err) {
      console.error(err);

      setError(
        t("agentsI18nLoadError"),
      );
    } finally {
      setLoading(false);
    }
  }


  function openCreate() {
    setEditingAgent(null);

    setForm({
      ...EMPTY_FORM,
    });

    setModalOpen(true);
  }


  function openPreset(
    role: WorkforceRole,
  ) {
    setEditingAgent(null);

    setForm({
      name: role.name,
      role: role.id,
      active: true,
      store_ids:
        stores.length === 1
          ? [stores[0].id]
          : [],
      knowledge_base_ids: [],
    });

    setModalOpen(true);
  }


  function openEdit(
    agent: Agent,
  ) {
    setEditingAgent(agent);

    setForm({
      name: agent.name,
      role: agent.role,
      active: agent.active,

      store_ids:
        agent.stores.map(
          (store) => store.id,
        ),

      knowledge_base_ids:
        agent.knowledge_bases.map(
          (knowledgeBase) =>
            knowledgeBase.id,
        ),
    });

    setModalOpen(true);
  }


  function closeModal() {
    if (saving) {
      return;
    }

    setModalOpen(false);
    setEditingAgent(null);

    setForm({
      ...EMPTY_FORM,
    });
  }


  function toggleStore(
    storeId: number,
  ) {
    setForm((current) => ({
      ...current,

      store_ids:
        current.store_ids.includes(
          storeId,
        )
          ? current.store_ids.filter(
              (id) => id !== storeId,
            )
          : [
              ...current.store_ids,
              storeId,
            ],
    }));
  }


  function toggleKnowledgeBase(
    knowledgeBaseId: number,
  ) {
    setForm((current) => ({
      ...current,

      knowledge_base_ids:
        current.knowledge_base_ids.includes(
          knowledgeBaseId,
        )
          ? current.knowledge_base_ids.filter(
              (id) =>
                id !== knowledgeBaseId,
            )
          : [
              ...current.knowledge_base_ids,
              knowledgeBaseId,
            ],
    }));
  }


  async function handleSave() {
    const name =
      form.name.trim();

    const role =
      form.role.trim();

    if (!name) {
      setError(
        t("agentsI18nNameRequired"),
      );

      return;
    }

    if (!role) {
      setError(
        t("agentsI18nRoleRequired"),
      );

      return;
    }

    try {
      setSaving(true);
      setError("");

      if (editingAgent) {
        await updateAgent(
          editingAgent.id,
          {
            name,
            role,
            active: form.active,
            store_ids:
              form.store_ids,
            knowledge_base_ids:
              form.knowledge_base_ids,
          },
        );
      } else {
        await createAgent({
          name,
          role,
          active: form.active,
          store_ids:
            form.store_ids,
          knowledge_base_ids:
            form.knowledge_base_ids,
        });
      }

      closeModal();

      await loadData();
    } catch (err) {
      console.error(err);

      setError(
        t("agentsI18nSaveError"),
      );
    } finally {
      setSaving(false);
    }
  }


  async function toggleActive(
    agent: Agent,
  ) {
    if (!canWrite) {
      return;
    }

    try {
      setError("");

      await updateAgent(
        agent.id,
        {
          active:
            !agent.active,
        },
      );

      await loadData();
    } catch (err) {
      console.error(err);

      setError(
        t("agentsI18nStatusError"),
      );
    }
  }


  return (
    <div className="content">
      <section className="page-heading management-heading">
        <div>
          <span className="eyebrow">
            DIAGLOB AI
          </span>

          <h1>
            Agentes IA
          </h1>

          <p>
            {t("agentsI18nSubtitle")}
          </p>
        </div>

        {canWrite && (
          <button
            className="primary-button"
            onClick={openCreate}
          >
            <Plus size={17} />
            Nuevo agente
          </button>
        )}
      </section>


      {error && (
        <div className="api-error">
          {error}
        </div>
      )}

      <section className="workforce-section">
        <div className="workforce-heading">
          <div>
            <span className="eyebrow">AI WORKFORCE</span>
            <h2>Tu equipo operativo de IA</h2>
            <p>
              Roles predefinidos sobre la misma capa de Knowledge, comercio,
              tracking, automatizaciones y permisos de Diaglob.
            </p>
          </div>
          <span className="workforce-count">
            {workforceRoles.length} roles
          </span>
        </div>

        <div className="workforce-grid">
          {workforceRoles.map((role) => {
            const configured = agents.filter(
              (agent) => agent.role === role.id,
            ).length;

            return (
              <article className="workforce-card" key={role.id}>
                <div className="workforce-card-top">
                  <span className="management-icon">
                    <Bot size={19} />
                  </span>
                  <div>
                    <strong>{role.name}</strong>
                    <span>
                      {role.customer_facing
                        ? "Cliente"
                        : "Operación interna"}
                    </span>
                  </div>
                  {configured > 0 && (
                    <span className="status-pill active">
                      {configured} configurado{configured > 1 ? "s" : ""}
                    </span>
                  )}
                </div>

                <p>{role.purpose}</p>

                <div className="workforce-capabilities">
                  {role.capabilities.slice(0, 4).map(
                    (capability) => (
                      <span key={capability}>
                        {capability}
                      </span>
                    ),
                  )}
                </div>

                {canWrite && (
                  <button
                    className="secondary-button"
                    onClick={() => openPreset(role)}
                  >
                    <Plus size={15} />
                    Crear desde rol
                  </button>
                )}
              </article>
            );
          })}
        </div>
      </section>


      {loading ? (
        <div className="conversation-loading">
          <LoaderCircle
            className="spin"
            size={26}
          />
        </div>
      ) : (
        <div className="management-grid">
          {agents.map((agent) => (
            <article
              key={agent.id}
              className="panel management-card"
            >
              <div className="management-card-header">
                <div className="management-icon">
                  <Bot size={20} />
                </div>

                <div className="management-title">
                  <h3>
                    {agent.name}
                  </h3>

                  <span>
                    {agent.role}
                  </span>
                </div>

                <span
                  className={
                    agent.active
                      ? "status-pill active"
                      : "status-pill"
                  }
                >
                  {agent.active
                    ? t("agentsI18nActive")
                    : t("agentsI18nInactive")}
                </span>
              </div>


              <div className="management-section">
                <strong>
                  <StoreIcon size={15} />
                  {t("agentsI18nStores")}
                </strong>

                <div className="tag-list">
                  {agent.stores.length ? (
                    agent.stores.map(
                      (store) => (
                        <span
                          key={store.id}
                        >
                          {store.name}
                        </span>
                      ),
                    )
                  ) : (
                    <span>
                      {t("agentsI18nNoStores")}
                    </span>
                  )}
                </div>
              </div>


              <div className="management-section">
                <strong>
                  <BrainCircuit size={15} />
                  Knowledge Bases
                </strong>

                <div className="tag-list">
                  {agent.knowledge_bases.length
                    ? agent.knowledge_bases.map(
                        (knowledgeBase) => (
                          <span
                            key={
                              knowledgeBase.id
                            }
                          >
                            {
                              knowledgeBase.name
                            }
                          </span>
                        ),
                      )
                    : (
                      <span>
                        Sin fuentes asignadas
                      </span>
                    )}
                </div>
              </div>


              {canWrite && (
                <div className="management-actions">
                  <button
                    className="secondary-button"
                    onClick={() =>
                      openEdit(agent)
                    }
                  >
                    <Pencil size={15} />
                    {t("agentsI18nEdit")}
                  </button>

                  <button
                    className="secondary-button"
                    onClick={() =>
                      toggleActive(agent)
                    }
                  >
                    {agent.active
                      ? t("agentsI18nDeactivate")
                      : t("agentsI18nActivate")}
                  </button>
                </div>
              )}
            </article>
          ))}


          {!agents.length && (
            <div className="panel empty-management">
              <Bot size={28} />

              <strong>
                No hay agentes
              </strong>

              <span>
                {t("agentsI18nEmptyHelp")}
              </span>
            </div>
          )}
        </div>
      )}


      {modalOpen && (
        <div
          className="management-modal-backdrop"
          onMouseDown={closeModal}
        >
          <div
            className="management-modal"
            onMouseDown={(event) =>
              event.stopPropagation()
            }
          >
            <header className="management-modal-header">
              <div>
                <span className="eyebrow">
                  DIAGLOB AI
                </span>

                <h2>
                  {editingAgent
                    ? t("agentsI18nEditAgent")
                    : t("agentsI18nNewAgent")}
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
                  {t("agentsI18nName")}
                </span>

                <input
                  value={form.name}
                  onChange={(event) =>
                    setForm(
                      (current) => ({
                        ...current,
                        name:
                          event.target.value,
                      }),
                    )
                  }
                  placeholder={t("agentsI18nNamePlaceholder")}
                />
              </label>


              <label>
                <span>
                  Rol del agente
                </span>

                <input
                  value={form.role}
                  onChange={(event) =>
                    setForm(
                      (current) => ({
                        ...current,
                        role:
                          event.target.value,
                      }),
                    )
                  }
                  placeholder={t("agentsI18nRolePlaceholder")}
                />
              </label>


              <div className="management-form-section">
                <strong>
                  {t("agentsI18nStores")}
                </strong>

                <div className="selection-grid">
                  {stores.map((store) => (
                    <label
                      key={store.id}
                      className="selection-option"
                    >
                      <input
                        type="checkbox"
                        checked={
                          form.store_ids.includes(
                            store.id,
                          )
                        }
                        onChange={() =>
                          toggleStore(
                            store.id,
                          )
                        }
                      />

                      <div>
                        <strong>
                          {store.name}
                        </strong>

                        <span>
                          {
                            store.country_code
                          }
                          {" · "}
                          {store.currency}
                        </span>
                      </div>
                    </label>
                  ))}
                </div>
              </div>


              <div className="management-form-section">
                <strong>
                  Knowledge Bases
                </strong>

                <div className="selection-grid">
                  {knowledgeBases.map(
                    (knowledgeBase) => (
                      <label
                        key={
                          knowledgeBase.id
                        }
                        className="selection-option"
                      >
                        <input
                          type="checkbox"
                          checked={
                            form.knowledge_base_ids.includes(
                              knowledgeBase.id,
                            )
                          }
                          onChange={() =>
                            toggleKnowledgeBase(
                              knowledgeBase.id,
                            )
                          }
                        />

                        <div>
                          <strong>
                            {
                              knowledgeBase.name
                            }
                          </strong>

                          <span>
                            {
                              knowledgeBase.scope ===
                              "organization"
                                ? t("agentsI18nOrganization")
                                : t("agentsI18nSelectedStores")
                            }
                          </span>
                        </div>
                      </label>
                    ),
                  )}
                </div>
              </div>


              <label className="toggle-row">
                <input
                  type="checkbox"
                  checked={form.active}
                  onChange={(event) =>
                    setForm(
                      (current) => ({
                        ...current,
                        active:
                          event.target.checked,
                      }),
                    )
                  }
                />

                <span>
                  {t("agentsI18nAgentActive")}
                </span>
              </label>
            </div>


            <footer className="management-modal-actions">
              <button
                className="secondary-button"
                onClick={closeModal}
                disabled={saving}
              >
                {t("agentsI18nCancel")}
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

                {editingAgent
                  ? t("agentsI18nSaveChanges")
                  : t("agentsI18nCreateAgent")}
              </button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}
