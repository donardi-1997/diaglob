import { useTranslation } from "react-i18next";
import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
} from "react";

import {
  BrainCircuit,
  Database,
  FileText,
  LoaderCircle,
  Pencil,
  Plus,
  Store as StoreIcon,
  Trash2,
  Upload,
  Users,
  X,
} from "lucide-react";

import {
  createKnowledgeBase,
  getKnowledgeBases,
  updateKnowledgeBase,
  type KnowledgeBase,
} from "../services/knowledgeBases";

import {
  deleteKnowledgeSource,
  getKnowledgeSources,
  uploadKnowledgeSource,
  type KnowledgeSource,
} from "../services/knowledgeSources";

import {
  getStores,
  type Store,
} from "../services/stores";


interface KnowledgeBasesPageProps {
  canWrite: boolean;
}


interface KnowledgeFormState {
  name: string;

  scope:
    | "organization"
    | "selected_stores";

  external_id: string;

  active: boolean;

  store_ids: number[];
}


const EMPTY_FORM: KnowledgeFormState = {
  name: "",
  scope: "selected_stores",
  external_id: "",
  active: true,
  store_ids: [],
};


function formatFileSize(
  bytes: number | null,
) {
  if (!bytes) {
    return "—";
  }

  if (bytes < 1024) {
    return `${bytes} B`;
  }

  if (bytes < 1024 * 1024) {
    return `${(
      bytes / 1024
    ).toFixed(1)} KB`;
  }

  return `${(
    bytes /
    (1024 * 1024)
  ).toFixed(1)} MB`;
}


export default function KnowledgeBasesPage({
  canWrite,
}: KnowledgeBasesPageProps) {
  const { t } = useTranslation();
  const [items, setItems] =
    useState<KnowledgeBase[]>([]);

  const [stores, setStores] =
    useState<Store[]>([]);

  const [loading, setLoading] =
    useState(true);

  const [saving, setSaving] =
    useState(false);

  const [error, setError] =
    useState("");

  const [formOpen, setFormOpen] =
    useState(false);

  const [
    editingKnowledgeBase,
    setEditingKnowledgeBase,
  ] = useState<KnowledgeBase | null>(
    null,
  );

  const [form, setForm] =
    useState<KnowledgeFormState>({
      ...EMPTY_FORM,
    });


  // =========================================================
  // SOURCES
  // =========================================================

  const [
    sourcesOpen,
    setSourcesOpen,
  ] = useState(false);

  const [
    selectedKnowledgeBase,
    setSelectedKnowledgeBase,
  ] = useState<KnowledgeBase | null>(
    null,
  );

  const [sources, setSources] =
    useState<KnowledgeSource[]>([]);

  const [
    sourcesLoading,
    setSourcesLoading,
  ] = useState(false);

  const [
    uploading,
    setUploading,
  ] = useState(false);

  const fileInputRef =
    useRef<HTMLInputElement | null>(
      null,
    );


  useEffect(() => {
    void loadData();
  }, []);


  async function loadData() {
    try {
      setLoading(true);
      setError("");

      const [
        knowledgeResponse,
        storesResponse,
      ] = await Promise.all([
        getKnowledgeBases(),
        getStores(),
      ]);

      setItems(
        knowledgeResponse.items,
      );

      setStores(
        storesResponse.items,
      );
    } catch (err) {
      console.error(err);

      setError(
        t("knowledgeI18nLoadError"),
      );
    } finally {
      setLoading(false);
    }
  }


  // =========================================================
  // KNOWLEDGE BASE CRUD
  // =========================================================

  function openCreate() {
    setEditingKnowledgeBase(
      null,
    );

    setForm({
      ...EMPTY_FORM,
    });

    setFormOpen(true);
  }


  function openEdit(
    knowledgeBase: KnowledgeBase,
  ) {
    setEditingKnowledgeBase(
      knowledgeBase,
    );

    setForm({
      name:
        knowledgeBase.name,

      scope:
        knowledgeBase.scope,

      external_id:
        knowledgeBase.external_id ||
        "",

      active:
        knowledgeBase.active,

      store_ids:
        knowledgeBase.stores.map(
          (store) => store.id,
        ),
    });

    setFormOpen(true);
  }


  function closeForm() {
    if (saving) {
      return;
    }

    setFormOpen(false);

    setEditingKnowledgeBase(
      null,
    );
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


  async function handleSave() {
    const name =
      form.name.trim();

    if (!name) {
      setError(
        t("knowledgeI18nNameRequired"),
      );

      return;
    }

    if (
      form.scope ===
        "selected_stores" &&
      form.store_ids.length === 0
    ) {
      setError(
        t("knowledgeI18nStoreRequired"),
      );

      return;
    }

    try {
      setSaving(true);
      setError("");

      const payload = {
        name,

        scope:
          form.scope,

        external_id:
          form.external_id.trim()
          || null,

        active:
          form.active,

        store_ids:
          form.scope ===
          "organization"
            ? []
            : form.store_ids,
      };

      if (
        editingKnowledgeBase
      ) {
        await updateKnowledgeBase(
          editingKnowledgeBase.id,
          payload,
        );
      } else {
        await createKnowledgeBase(
          payload,
        );
      }

      setFormOpen(false);

      setEditingKnowledgeBase(
        null,
      );

      await loadData();
    } catch (err) {
      console.error(err);

      setError(
        t("knowledgeI18nSaveError"),
      );
    } finally {
      setSaving(false);
    }
  }


  async function toggleActive(
    knowledgeBase: KnowledgeBase,
  ) {
    if (!canWrite) {
      return;
    }

    try {
      setError("");

      await updateKnowledgeBase(
        knowledgeBase.id,
        {
          active:
            !knowledgeBase.active,
        },
      );

      await loadData();
    } catch (err) {
      console.error(err);

      setError(
        t("knowledgeI18nStatusError"),
      );
    }
  }


  // =========================================================
  // DOCUMENTS
  // =========================================================

  async function openSources(
    knowledgeBase: KnowledgeBase,
  ) {
    setSelectedKnowledgeBase(
      knowledgeBase,
    );

    setSourcesOpen(true);

    await loadSources(
      knowledgeBase.id,
    );
  }


  async function loadSources(
    knowledgeBaseId: number,
  ) {
    try {
      setSourcesLoading(true);
      setError("");

      const response =
        await getKnowledgeSources(
          knowledgeBaseId,
        );

      setSources(
        response.items,
      );
    } catch (err) {
      console.error(err);

      setError(
        t("knowledgeI18nDocumentsLoadError"),
      );
    } finally {
      setSourcesLoading(false);
    }
  }


  async function handleFileChange(
    event: ChangeEvent<HTMLInputElement>,
  ) {
    const file =
      event.target.files?.[0];

    if (
      !file ||
      !selectedKnowledgeBase
    ) {
      return;
    }

    try {
      setUploading(true);
      setError("");

      await uploadKnowledgeSource(
        selectedKnowledgeBase.id,
        file,
      );

      await loadSources(
        selectedKnowledgeBase.id,
      );
    } catch (err) {
      console.error(err);

      setError(
        t("knowledgeI18nDocumentUploadError"),
      );
    } finally {
      setUploading(false);

      if (
        fileInputRef.current
      ) {
        fileInputRef.current.value =
          "";
      }
    }
  }


  async function handleDeleteSource(
    source: KnowledgeSource,
  ) {
    if (
      !canWrite ||
      !selectedKnowledgeBase
    ) {
      return;
    }

    const confirmed =
      window.confirm(
        t("knowledgeI18nDeleteConfirm", {
          name: source.name,
        }),
      );

    if (!confirmed) {
      return;
    }

    try {
      setError("");

      await deleteKnowledgeSource(
        selectedKnowledgeBase.id,
        source.id,
      );

      await loadSources(
        selectedKnowledgeBase.id,
      );
    } catch (err) {
      console.error(err);

      setError(
        t("knowledgeI18nDocumentDeleteError"),
      );
    }
  }


  return (
    <div className="content">
      <section
        className="
          page-heading
          management-heading
        "
      >
        <div>
          <span className="eyebrow">
            DIAGLOB KNOWLEDGE
          </span>

          <h1>
            Conocimiento
          </h1>

          <p>
            Administra las fuentes de
            conocimiento que utilizan
            tus agentes IA.
          </p>
        </div>


        {canWrite && (
          <button
            className="primary-button"
            onClick={openCreate}
          >
            <Plus size={17} />

            {t("knowledgeI18nNewKnowledgeBase")}
          </button>
        )}
      </section>


      {error && (
        <div className="api-error">
          {error}
        </div>
      )}


      {loading ? (
        <div className="conversation-loading">
          <LoaderCircle
            className="spin"
            size={26}
          />
        </div>
      ) : (
        <div className="management-grid">
          {items.map(
            (knowledgeBase) => (
              <article
                key={
                  knowledgeBase.id
                }
                className="
                  panel
                  management-card
                "
              >
                <div className="management-card-header">
                  <div className="management-icon">
                    <BrainCircuit
                      size={20}
                    />
                  </div>

                  <div className="management-title">
                    <h3>
                      {
                        knowledgeBase.name
                      }
                    </h3>

                    <span>
                      {
                        knowledgeBase.scope ===
                        "organization"
                          ? t("knowledgeI18nWholeOrganization")
                          : t("knowledgeI18nSelectedStores")
                      }
                    </span>
                  </div>

                  <span
                    className={
                      knowledgeBase.active
                        ? "status-pill active"
                        : "status-pill"
                    }
                  >
                    {
                      knowledgeBase.active
                        ? t("knowledgeI18nActive")
                        : t("knowledgeI18nInactive")
                    }
                  </span>
                </div>


                <div className="management-section">
                  <strong>
                    <StoreIcon
                      size={15}
                    />
                    {t("knowledgeI18nStores")}
                  </strong>

                  <div className="tag-list">
                    {
                      knowledgeBase.scope ===
                      "organization"
                        ? (
                          <span>
                            {t("knowledgeI18nAllStores")}
                          </span>
                        )
                        : knowledgeBase.stores.map(
                            (store) => (
                              <span
                                key={
                                  store.id
                                }
                              >
                                {
                                  store.name
                                }
                              </span>
                            ),
                          )
                    }
                  </div>
                </div>


                <div className="management-section">
                  <strong>
                    <Users size={15} />
                    Agentes
                  </strong>

                  <div className="tag-list">
                    {
                      knowledgeBase.agents.length
                        ? knowledgeBase.agents.map(
                            (agent) => (
                              <span
                                key={
                                  agent.id
                                }
                              >
                                {
                                  agent.name
                                }
                              </span>
                            ),
                          )
                        : (
                          <span>
                            Sin agentes
                          </span>
                        )
                    }
                  </div>
                </div>


                <div className="management-section">
                  <strong>
                    <Database size={15} />
                    AWS
                  </strong>

                  <span className="management-muted">
                    {
                      knowledgeBase.external_id ||
                      t("knowledgeI18nPendingBedrock")
                    }
                  </span>
                </div>


                <div className="management-actions">
                  <button
                    className="secondary-button"
                    onClick={() =>
                      void openSources(
                        knowledgeBase,
                      )
                    }
                  >
                    <FileText
                      size={15}
                    />

                    Documentos
                  </button>


                  {canWrite && (
                    <>
                      <button
                        className="secondary-button"
                        onClick={() =>
                          openEdit(
                            knowledgeBase,
                          )
                        }
                      >
                        <Pencil
                          size={15}
                        />

                        {t("knowledgeI18nEdit")}
                      </button>

                      <button
                        className="secondary-button"
                        onClick={() =>
                          void toggleActive(
                            knowledgeBase,
                          )
                        }
                      >
                        {
                          knowledgeBase.active
                            ? t("knowledgeI18nDeactivate")
                            : t("knowledgeI18nActivate")
                        }
                      </button>
                    </>
                  )}
                </div>
              </article>
            ),
          )}


          {!items.length && (
            <div
              className="
                panel
                empty-management
              "
            >
              <BrainCircuit
                size={30}
              />

              <strong>
                Sin Knowledge Bases
              </strong>

              <span>
                Crea la primera fuente
                de conocimiento.
              </span>
            </div>
          )}
        </div>
      )}


      {/* ===================================================
          KNOWLEDGE BASE FORM
          =================================================== */}

      {formOpen && (
        <div
          className="management-modal-backdrop"
          onMouseDown={closeForm}
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
                  DIAGLOB KNOWLEDGE
                </span>

                <h2>
                  {
                    editingKnowledgeBase
                      ? t("knowledgeI18nEditKnowledgeBase")
                      : t("knowledgeI18nNewKnowledgeBase")
                  }
                </h2>
              </div>

              <button
                className="icon-button"
                onClick={closeForm}
              >
                <X size={18} />
              </button>
            </header>


            <div className="management-form">
              <label>
                <span>
                  {t("knowledgeI18nName")}
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
                  placeholder={t("knowledgeI18nNamePlaceholder")}
                />
              </label>


              <label>
                <span>
                  Alcance
                </span>

                <select
                  value={form.scope}
                  onChange={(event) => {
                    const scope =
                      event.target.value as
                        | "organization"
                        | "selected_stores";

                    setForm(
                      (current) => ({
                        ...current,

                        scope,

                        store_ids:
                          scope ===
                          "organization"
                            ? []
                            : current.store_ids,
                      }),
                    );
                  }}
                >
                  <option
                    value="selected_stores"
                  >
                    {t("knowledgeI18nSelectedStores")}
                  </option>

                  <option
                    value="organization"
                  >
                    {t("knowledgeI18nWholeOrganization")}
                  </option>
                </select>
              </label>


              {
                form.scope ===
                "selected_stores" && (
                  <div className="management-form-section">
                    <strong>
                      {t("knowledgeI18nStores")}
                    </strong>

                    <div className="selection-grid">
                      {stores.map(
                        (store) => (
                          <label
                            key={
                              store.id
                            }
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
                                {
                                  store.name
                                }
                              </strong>

                              <span>
                                {
                                  store.country_code
                                }
                                {" · "}
                                {
                                  store.currency
                                }
                              </span>
                            </div>
                          </label>
                        ),
                      )}
                    </div>
                  </div>
                )
              }


              <label>
                <span>
                  External ID
                </span>

                <input
                  value={
                    form.external_id
                  }
                  onChange={(event) =>
                    setForm(
                      (current) => ({
                        ...current,

                        external_id:
                          event.target.value,
                      }),
                    )
                  }
                  placeholder={t("knowledgeI18nBedrockPlaceholder")}
                />
              </label>


              <label className="toggle-row">
                <input
                  type="checkbox"
                  checked={
                    form.active
                  }
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
                  {t("knowledgeI18nKnowledgeBaseActive")}
                </span>
              </label>
            </div>


            <footer className="management-modal-actions">
              <button
                className="secondary-button"
                onClick={closeForm}
                disabled={saving}
              >
                {t("knowledgeI18nCancel")}
              </button>

              <button
                className="primary-button"
                onClick={() =>
                  void handleSave()
                }
                disabled={saving}
              >
                {saving && (
                  <LoaderCircle
                    className="spin"
                    size={16}
                  />
                )}

                {
                  editingKnowledgeBase
                    ? t("knowledgeI18nSaveChanges")
                    : t("knowledgeI18nCreateKnowledgeBase")
                }
              </button>
            </footer>
          </div>
        </div>
      )}


      {/* ===================================================
          DOCUMENTS
          =================================================== */}

      {
        sourcesOpen &&
        selectedKnowledgeBase && (
          <div
            className="management-modal-backdrop"
            onMouseDown={() => {
              if (!uploading) {
                setSourcesOpen(
                  false,
                );
              }
            }}
          >
            <div
              className="
                management-modal
                knowledge-source-modal
              "
              onMouseDown={(event) =>
                event.stopPropagation()
              }
            >
              <header className="management-modal-header">
                <div>
                  <span className="eyebrow">
                    DOCUMENTOS
                  </span>

                  <h2>
                    {
                      selectedKnowledgeBase.name
                    }
                  </h2>
                </div>

                <button
                  className="icon-button"
                  onClick={() =>
                    setSourcesOpen(
                      false,
                    )
                  }
                  disabled={
                    uploading
                  }
                >
                  <X size={18} />
                </button>
              </header>


              <div className="management-form">
                {canWrite && (
                  <div className="knowledge-upload-box">
                    <Upload
                      size={22}
                    />

                    <div>
                      <strong>
                        Añadir documento
                      </strong>

                      <span>
                        PDF, TXT, MD,
                        HTML, DOC, DOCX,
                        CSV o XLSX.
                      </span>
                    </div>

                    <button
                      className="primary-button"
                      onClick={() =>
                        fileInputRef.current?.click()
                      }
                      disabled={
                        uploading
                      }
                    >
                      {uploading ? (
                        <LoaderCircle
                          className="spin"
                          size={16}
                        />
                      ) : (
                        <Upload
                          size={16}
                        />
                      )}

                      Subir archivo
                    </button>

                    <input
                      ref={
                        fileInputRef
                      }
                      type="file"
                      hidden
                      accept=".pdf,.txt,.md,.html,.doc,.docx,.csv,.xlsx"
                      onChange={
                        handleFileChange
                      }
                    />
                  </div>
                )}


                {sourcesLoading ? (
                  <div className="conversation-loading">
                    <LoaderCircle
                      className="spin"
                      size={24}
                    />
                  </div>
                ) : (
                  <div className="knowledge-source-list">
                    {sources.map(
                      (source) => (
                        <div
                          key={
                            source.id
                          }
                          className="knowledge-source-row"
                        >
                          <div className="management-icon">
                            <FileText
                              size={18}
                            />
                          </div>

                          <div className="knowledge-source-info">
                            <strong>
                              {
                                source.name
                              }
                            </strong>

                            <span>
                              {
                                formatFileSize(
                                  source.size_bytes,
                                )
                              }
                              {" · "}
                              {
                                source.status
                              }
                            </span>
                          </div>

                          {canWrite && (
                            <button
                              className="
                                icon-button
                                danger-button
                              "
                              onClick={() =>
                                void handleDeleteSource(
                                  source,
                                )
                              }
                              title={t("knowledgeI18nDeleteDocument")}
                            >
                              <Trash2
                                size={16}
                              />
                            </button>
                          )}
                        </div>
                      ),
                    )}


                    {!sources.length && (
                      <div className="empty-management">
                        <FileText
                          size={30}
                        />

                        <strong>
                          Sin documentos
                        </strong>

                        <span>
                          Esta Knowledge Base
                          todavía no tiene
                          fuentes cargadas.
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        )
      }
    </div>
  );
}
