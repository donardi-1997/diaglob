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
import { validateAgentStoreAssignment } from "../services/agentEditorValidation";
import { Link } from "react-router-dom";
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


type LocaleKey = "es" | "en" | "pt-BR";

function normalizeLocale(language: string): LocaleKey {
  const value = (language || "").toLowerCase();
  if (value.startsWith("pt")) return "pt-BR";
  if (value.startsWith("en")) return "en";
  return "es";
}

const COPY: Record<LocaleKey, {
  title: string;
  newAgent: string;
  retry: string;
  loadError: (sections: string) => string;
  sectionAgents: string;
  sectionKnowledge: string;
  sectionRoles: string;
  storeRequired: string;
  storeUnavailable: string;
  noStoresTitle: string;
  noStoresBody: string;
  goToStores: string;
  workforceTitle: string;
  workforceBody: string;
  roles: (count: number) => string;
  customerFacing: string;
  internal: string;
  configured: (count: number) => string;
  createFromRole: string;
  knowledgeBases: string;
  noSources: string;
  emptyTitle: string;
  roleLabel: string;
}> = {
  es: {
    title: "Agentes IA",
    newAgent: "Nuevo agente",
    retry: "Reintentar",
    loadError: (sections) => `No se pudo cargar: ${sections}. Inténtalo de nuevo.`,
    sectionAgents: "agentes",
    sectionKnowledge: "bases de conocimiento",
    sectionRoles: "roles de IA",
    storeRequired: "Selecciona al menos una tienda activa antes de activar el agente.",
    storeUnavailable: "Una tienda asignada ya no está disponible. Actualiza la selección.",
    noStoresTitle: "No hay tiendas disponibles para los agentes.",
    noStoresBody: "Agrega o conecta una tienda para asignar agentes de IA.",
    goToStores: "Ir a Tiendas",
    workforceTitle: "Tu equipo operativo de IA",
    workforceBody:
      "Roles predefinidos sobre la misma capa de Knowledge, comercio, tracking, automatizaciones y permisos de Diaglob.",
    roles: (count) => `${count} roles`,
    customerFacing: "Cliente",
    internal: "Operación interna",
    configured: (count) => `${count} configurado${count > 1 ? "s" : ""}`,
    createFromRole: "Crear desde rol",
    knowledgeBases: "Bases de conocimiento",
    noSources: "Sin fuentes asignadas",
    emptyTitle: "No hay agentes",
    roleLabel: "Rol del agente",
  },
  en: {
    title: "AI Agents",
    newAgent: "New agent",
    retry: "Retry",
    loadError: (sections) => `Could not load: ${sections}. Please retry.`,
    sectionAgents: "agents",
    sectionKnowledge: "knowledge bases",
    sectionRoles: "AI roles",
    storeRequired: "Select at least one active store before activating the agent.",
    storeUnavailable: "An assigned store is no longer available. Update the selection.",
    noStoresTitle: "No stores are available for agents.",
    noStoresBody: "Add or connect a store to assign AI agents.",
    goToStores: "Go to Stores",
    workforceTitle: "Your AI operations team",
    workforceBody:
      "Predefined roles built on the same Diaglob layer of knowledge, commerce, tracking, automations and permissions.",
    roles: (count) => `${count} roles`,
    customerFacing: "Customer-facing",
    internal: "Internal operations",
    configured: (count) => `${count} configured`,
    createFromRole: "Create from role",
    knowledgeBases: "Knowledge bases",
    noSources: "No sources assigned",
    emptyTitle: "No agents yet",
    roleLabel: "Agent role",
  },
  "pt-BR": {
    title: "Agentes de IA",
    newAgent: "Novo agente",
    retry: "Tentar novamente",
    loadError: (sections) => `Não foi possível carregar: ${sections}. Tente novamente.`,
    sectionAgents: "agentes",
    sectionKnowledge: "bases de conhecimento",
    sectionRoles: "funções de IA",
    storeRequired: "Selecione pelo menos uma loja ativa antes de ativar o agente.",
    storeUnavailable: "Uma loja atribuída não está mais disponível. Atualize a seleção.",
    noStoresTitle: "Não há lojas disponíveis para os agentes.",
    noStoresBody: "Adicione ou conecte uma loja para atribuir agentes de IA.",
    goToStores: "Ir para Lojas",
    workforceTitle: "Sua equipe operacional de IA",
    workforceBody:
      "Funções predefinidas sobre a mesma camada de conhecimento, comércio, rastreamento, automações e permissões da Diaglob.",
    roles: (count) => `${count} funções`,
    customerFacing: "Cliente",
    internal: "Operação interna",
    configured: (count) => `${count} configurado${count > 1 ? "s" : ""}`,
    createFromRole: "Criar a partir da função",
    knowledgeBases: "Bases de conhecimento",
    noSources: "Sem fontes atribuídas",
    emptyTitle: "Nenhum agente",
    roleLabel: "Função do agente",
  },
};

// The workforce catalog API returns Spanish copy; localize the known role ids
// on the client and fall back to the API text for any role added later.
const ROLE_COPY: Record<Exclude<LocaleKey, "es">, Record<string, { name: string; purpose: string }>> = {
  en: {
    sales: { name: "Sales Agent", purpose: "Turn conversations into purchases without inventing catalog data." },
    support: { name: "Support Agent", purpose: "Answer order, policy and tracking questions with real context." },
    logistics: { name: "Logistics Agent", purpose: "Monitor fulfillment, tracking and delivery issues." },
    retention: { name: "Retention Agent", purpose: "Re-engage customers and grow repeat purchases using segments and context." },
    analyst: { name: "Analyst Agent", purpose: "Turn operations, margin and performance into explainable decisions." },
    post_sales: { name: "Post-sales Agent", purpose: "Handle warranties, returns, refunds and delivery problems." },
  },
  "pt-BR": {
    sales: { name: "Agente de Vendas", purpose: "Converter conversas em compras sem inventar dados do catálogo." },
    support: { name: "Agente de Suporte", purpose: "Resolver dúvidas de pedido, políticas e rastreamento com contexto real." },
    logistics: { name: "Agente Logístico", purpose: "Monitorar fulfillment, rastreamento e ocorrências de entrega." },
    retention: { name: "Agente de Retenção", purpose: "Reativar clientes e aumentar a recompra usando segmentos e contexto." },
    analyst: { name: "Agente Analista", purpose: "Transformar operação, margem e desempenho em decisões explicáveis." },
    post_sales: { name: "Agente de Pós-venda", purpose: "Acompanhar garantias, devoluções, reembolsos e problemas de entrega." },
  },
};

function localizeRole(role: WorkforceRole, locale: LocaleKey): { name: string; purpose: string } {
  if (locale === "es") return { name: role.name, purpose: role.purpose };
  return ROLE_COPY[locale][role.id] ?? { name: role.name, purpose: role.purpose };
}


export default function AgentsPage({
  stores,
  canWrite,
}: AgentsPageProps) {
  const { t, i18n } = useTranslation();
  const locale = normalizeLocale(i18n.resolvedLanguage || i18n.language || "es");
  const copy = COPY[locale];
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
        agentsResult,
        knowledgeResult,
        workforceResult,
      ] = await Promise.allSettled([
        getAgents(),
        getKnowledgeBases(),
        getWorkforceCatalog(),
      ]);

      const failedSections: string[] = [];

      if (agentsResult.status === "fulfilled") {
        setAgents(agentsResult.value.items);
      } else {
        console.error("Failed to load AI agents", agentsResult.reason);
        failedSections.push(copy.sectionAgents);
      }

      if (knowledgeResult.status === "fulfilled") {
        setKnowledgeBases(knowledgeResult.value.items);
      } else {
        console.error("Failed to load knowledge bases", knowledgeResult.reason);
        failedSections.push(copy.sectionKnowledge);
      }

      if (workforceResult.status === "fulfilled") {
        setWorkforceRoles(workforceResult.value.roles);
      } else {
        console.error("Failed to load workforce roles", workforceResult.reason);
        failedSections.push(copy.sectionRoles);
      }

      if (failedSections.length > 0) {
        setError(copy.loadError(failedSections.join(", ")));
      }
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

    const storeValidation = validateAgentStoreAssignment(
      form.active,
      form.store_ids,
      stores.filter((store) => store.active).map((store) => store.id),
    );
    if (storeValidation) {
      setError(
        storeValidation === "STORE_REQUIRED"
          ? copy.storeRequired
          : copy.storeUnavailable,
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

      // closeModal() deliberately ignores requests while saving=true.
      // A successful save must dismiss the editor without a second click.
      setModalOpen(false);
      setEditingAgent(null);
      setForm({ ...EMPTY_FORM });

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
            {copy.title}
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
            {copy.newAgent}
          </button>
        )}
      </section>


      {error && (
        <div className="api-error" role="alert">
          {error}
          <button type="button" className="secondary-button" onClick={() => void loadData()} disabled={loading || saving}>
            {copy.retry}
          </button>
        </div>
      )}
      {stores.length === 0 && !loading && (
        <div className="panel" role="status">
          <strong>{copy.noStoresTitle}</strong>
          <p>{copy.noStoresBody}</p>
          <Link to="/app/stores" className="secondary-button">{copy.goToStores}</Link>
        </div>
      )}

      <section className="workforce-section">
        <div className="workforce-heading">
          <div>
            <span className="eyebrow">AI WORKFORCE</span>
            <h2>{copy.workforceTitle}</h2>
            <p>
              {copy.workforceBody}
            </p>
          </div>
          <span className="workforce-count">
            {copy.roles(workforceRoles.length)}
          </span>
        </div>

        <div className="workforce-grid">
          {workforceRoles.map((role) => {
            const configured = agents.filter(
              (agent) => agent.role === role.id,
            ).length;
            const roleCopy = localizeRole(role, locale);

            return (
              <article className="workforce-card" key={role.id}>
                <div className="workforce-card-top">
                  <span className="management-icon">
                    <Bot size={19} />
                  </span>
                  <div>
                    <strong>{roleCopy.name}</strong>
                    <span>
                      {role.customer_facing
                        ? copy.customerFacing
                        : copy.internal}
                    </span>
                  </div>
                  {configured > 0 && (
                    <span className="status-pill active">
                      {copy.configured(configured)}
                    </span>
                  )}
                </div>

                <p>{roleCopy.purpose}</p>

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
                    {copy.createFromRole}
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
                  {copy.knowledgeBases}
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
                        {copy.noSources}
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
                {copy.emptyTitle}
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
                  {copy.roleLabel}
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
                  {copy.knowledgeBases}
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
