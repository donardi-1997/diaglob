import { useTranslation } from "react-i18next";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
} from "react";

import {
  BrainCircuit,
  Database,
  FileSpreadsheet,
  FileText,
  Link2,
  LoaderCircle,
  Pencil,
  Plus,
  RefreshCw,
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
  addGoogleSheetSource,
  disconnectGoogle,
  getGoogleStatus,
  getIngestionStatus,
  listGoogleSheets,
  listGoogleSheetTabs,
  startGoogleOAuth,
  syncGoogleSheetSource,
  type GoogleSheetItem,
  type GoogleStatus,
  type GoogleTabItem,
} from "../services/knowledgeGoogle";

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


  // =========================================================
  // GOOGLE SHEETS
  // =========================================================

  const [
    googleStatus,
    setGoogleStatus,
  ] = useState<GoogleStatus | null>(
    null,
  );

  const [
    googleSheetsOpen,
    setGoogleSheetsOpen,
  ] = useState(false);

  const [
    googleSheets,
    setGoogleSheets,
  ] = useState<GoogleSheetItem[]>([]);

  const [
    googleSheetsLoading,
    setGoogleSheetsLoading,
  ] = useState(false);

  const [
    selectedGoogleSheet,
    setSelectedGoogleSheet,
  ] = useState<GoogleSheetItem | null>(
    null,
  );

  const [
    googleTabsOpen,
    setGoogleTabsOpen,
  ] = useState(false);

  const [
    googleTabs,
    setGoogleTabs,
  ] = useState<GoogleTabItem[]>([]);

  const [
    googleTabsLoading,
    setGoogleTabsLoading,
  ] = useState(false);

  const [
    googleConnecting,
    setGoogleConnecting,
  ] = useState(false);

  const [
    googleAdding,
    setGoogleAdding,
  ] = useState(false);

  const pollingRef =
    useRef<number | null>(null);

  const [
    syncPollingSourceId,
    setSyncPollingSourceId,
  ] = useState<number | null>(null);


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

    await Promise.all([
      loadSources(
        knowledgeBase.id,
      ),
      loadGoogleStatus(),
    ]);
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


  async function loadGoogleStatus() {
    try {
      const status =
        await getGoogleStatus();

      setGoogleStatus(status);
    } catch {
      setGoogleStatus({
        connected: false,
        email: null,
        status: null,
        connected_at: null,
      });
    }
  }


  async function handleConnectGoogle() {
    try {
      setGoogleConnecting(true);
      setError("");

      const { authorization_url } =
        await startGoogleOAuth();

      window.open(
        authorization_url,
        "_blank",
      );
    } catch (err) {
      console.error(err);
      setGoogleConnecting(false);
      setError(
        t("knowledgeGoogleConnectionError"),
      );
    }
  }


  async function handleDisconnectGoogle() {
    const confirmed = window.confirm(
      t("knowledgeGoogleDisconnectConfirm"),
    );

    if (!confirmed) return;

    try {
      await disconnectGoogle();
      await loadGoogleStatus();
    } catch (err) {
      console.error(err);
      setError(
        t("knowledgeGoogleDisconnectError"),
      );
    }
  }


  async function handleOpenGoogleSheets() {
    if (!selectedKnowledgeBase) return;

    try {
      setGoogleSheetsOpen(true);
      setGoogleSheetsLoading(true);
      setError("");

      const response =
        await listGoogleSheets();

      setGoogleSheets(response.sheets);
    } catch (err) {
      console.error(err);
      setError(
        t("knowledgeGoogleSheetsLoadError"),
      );
      setGoogleSheetsOpen(false);
    } finally {
      setGoogleSheetsLoading(false);
    }
  }


  async function handleSelectGoogleSheet(
    sheet: GoogleSheetItem,
  ) {
    try {
      setSelectedGoogleSheet(sheet);
      setGoogleTabsOpen(true);
      setGoogleTabsLoading(true);
      setError("");

      const response =
        await listGoogleSheetTabs(
          sheet.spreadsheet_id,
        );

      setGoogleTabs(response.tabs);
    } catch (err) {
      console.error(err);
      setError(
        t("knowledgeGoogleTabsLoadError"),
      );
      setGoogleTabsOpen(false);
    } finally {
      setGoogleTabsLoading(false);
    }
  }


  async function handleAddGoogleSheetSource(
    tab: GoogleTabItem,
  ) {
    if (
      !selectedKnowledgeBase ||
      !selectedGoogleSheet
    )
      return;

    try {
      setGoogleAdding(true);
      setError("");

      const result =
        await addGoogleSheetSource(
          selectedKnowledgeBase.id,
          selectedGoogleSheet.spreadsheet_id,
          selectedGoogleSheet.name,
          tab.title,
        );

      setGoogleTabsOpen(false);
      setSelectedGoogleSheet(null);
      setGoogleSheetsOpen(false);

      await loadSources(
        selectedKnowledgeBase.id,
      );

      if (result.sync_status === "indexing") {
        startPollingIngestion(
          selectedKnowledgeBase.id,
          result.source_id,
        );
      }
    } catch (err) {
      console.error(err);
      setError(
        t("knowledgeGoogleAddSourceError"),
      );
    } finally {
      setGoogleAdding(false);
    }
  }


  async function handleSyncGoogleSource(
    source: KnowledgeSource,
  ) {
    if (!selectedKnowledgeBase) return;

    try {
      setError("");

      const result =
        await syncGoogleSheetSource(
          selectedKnowledgeBase.id,
          source.id,
        );

      await loadSources(
        selectedKnowledgeBase.id,
      );

      if (result.sync_status === "indexing") {
        startPollingIngestion(
          selectedKnowledgeBase.id,
          source.id,
        );
      }
    } catch (err) {
      console.error(err);
      setError(
        t("knowledgeGoogleSyncError"),
      );
    }
  }


  function startPollingIngestion(
    kbId: number,
    sourceId: number,
  ) {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
    }

    setSyncPollingSourceId(sourceId);

    pollingRef.current = window.setInterval(
      async () => {
        try {
          const result =
            await getIngestionStatus(
              kbId,
              sourceId,
            );

          if (
            result.sync_status !== "indexing"
          ) {
            if (pollingRef.current) {
              clearInterval(
                pollingRef.current,
              );
              pollingRef.current = null;
            }
            setSyncPollingSourceId(null);
            await loadSources(kbId);
          }
        } catch {
          if (pollingRef.current) {
            clearInterval(
              pollingRef.current,
            );
            pollingRef.current = null;
          }
          setSyncPollingSourceId(null);
        }
      },
      5000,
    );
  }


  useEffect(() => {
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    };
  }, []);


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
                    {t("knowledgeGoogleDocuments")}
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

              {canWrite && (
                <div className="knowledge-google-banner">
                  {googleStatus?.connected ? (
                    <>
                      <Link2 size={14} />
                      <span>
                        {t("knowledgeGoogleConnected")}{" "}
                        <strong>
                          {googleStatus.email}
                        </strong>
                      </span>
                      <button
                        className="text-button danger"
                        onClick={() =>
                          void handleDisconnectGoogle()
                        }
                      >
                        {t("knowledgeGoogleDisconnect")}
                      </button>
                    </>
                  ) : (
                    <>
                      <Link2 size={14} />
                      <span>
                        {t("knowledgeGoogleNotConnected")}
                      </span>
                      <button
                        className="primary-button google-button"
                        onClick={() =>
                          void handleConnectGoogle()
                        }
                        disabled={
                          googleConnecting
                        }
                      >
                        {googleConnecting ? (
                          <LoaderCircle
                            className="spin"
                            size={14}
                          />
                        ) : (
                          <Link2 size={14} />
                        )}
                        {t("knowledgeGoogleConnect")}
                      </button>
                    </>
                  )}
                </div>
              )}


              <div className="management-form">
                {canWrite && (
                  <div className="knowledge-upload-box">
                    <Upload
                      size={22}
                    />

                    <div>
                      <strong>
                        {t("knowledgeGoogleAddDocument")}
                      </strong>

                      <span>
                        {t("knowledgeGoogleAddDocumentFormats")}
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

                      {t("knowledgeGoogleUploadFile")}
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

                {canWrite && googleStatus?.connected && (
                  <div className="knowledge-google-connect-box">
                    <FileSpreadsheet
                      size={22}
                    />

                    <div>
                      <strong>
                        {t("knowledgeGoogleSheetTitle")}
                      </strong>

                      <span>
                        {t("knowledgeGoogleSheetDescription")}
                      </span>
                    </div>

                    <button
                      className="google-button"
                      onClick={() =>
                        void handleOpenGoogleSheets()
                      }
                      disabled={
                        googleSheetsLoading
                      }
                    >
                      {googleSheetsLoading ? (
                        <LoaderCircle
                          className="spin"
                          size={16}
                        />
                      ) : (
                        <FileSpreadsheet
                          size={16}
                        />
                      )}

                      {t("knowledgeGoogleSelectSheet")}
                    </button>
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
                      (source) => {
                        const isGoogleSheets =
                          source.source_type ===
                          "google_sheet";

                        const isSyncing =
                          syncPollingSourceId ===
                          source.id;

                        const syncLabel =
                          source.sync_status ===
                          "indexing" || isSyncing
                            ? t("knowledgeGoogleSyncing")
                            : source.sync_status ===
                              "synced"
                              ? t("knowledgeGoogleSynced")
                              : source.sync_status ===
                                "error"
                                ? t("knowledgeGoogleSyncError")
                                : null;

                        return (
                          <div
                            key={
                              source.id
                            }
                            className={`
                              knowledge-source-row
                              ${isGoogleSheets ? "google-source-row" : ""}
                            `}
                          >
                            <div className="management-icon">
                              {isGoogleSheets ? (
                                <FileSpreadsheet
                                  size={18}
                                />
                              ) : (
                                <FileText
                                  size={18}
                                />
                              )}
                            </div>

                            <div className="knowledge-source-info">
                              <strong>
                                {
                                  source.name
                                }
                              </strong>

                              <span>
                                {isGoogleSheets ? (
                                  <>
                                    {source.sheet_name && (
                                      <>
                                        {source.sheet_name}
                                        {" · "}
                                      </>
                                    )}
                                    {syncLabel || t("knowledgeGoogleSyncPending")}
                                    {source.last_synced_at && (
                                      <>
                                        {" · "}
                                        {new Date(
                                          source.last_synced_at,
                                        ).toLocaleDateString()}
                                      </>
                                    )}
                                  </>
                                ) : (
                                  <>
                                    {
                                      formatFileSize(
                                        source.size_bytes,
                                      )
                                    }
                                    {" · "}
                                    {
                                      source.status
                                    }
                                  </>
                                )}
                              </span>
                            </div>

                            {canWrite && isGoogleSheets && (
                              <button
                                className="icon-button google-sync-button"
                                onClick={() =>
                                  void handleSyncGoogleSource(
                                    source,
                                  )
                                }
                                disabled={
                                  isSyncing ||
                                  source.sync_status ===
                                    "indexing"
                                }
                                title={t("knowledgeGoogleSync")}
                              >
                                <RefreshCw
                                  size={16}
                                  className={
                                    isSyncing
                                      ? "spin"
                                      : ""
                                  }
                                />
                              </button>
                            )}

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
                        );
                      },
                    )}


                    {!sources.length && (
                      <div className="empty-management">
                        <FileText
                          size={30}
                        />

                        <strong>
                          {t("knowledgeGoogleNoDocuments")}
                        </strong>

                        <span>
                          {t("knowledgeGoogleNoDocumentsDescription")}
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


      {/* ===================================================
          GOOGLE SHEETS PICKER
          =================================================== */}

      {
        googleSheetsOpen && (
          <div
            className="management-modal-backdrop"
            onMouseDown={() => {
              if (!googleAdding) {
                setGoogleSheetsOpen(false);
                setSelectedGoogleSheet(null);
              }
            }}
          >
            <div
              className="management-modal knowledge-source-modal"
              onMouseDown={(event) =>
                event.stopPropagation()
              }
            >
              <header className="management-modal-header">
                <div>
                  <span className="eyebrow">
                    {t("knowledgeGoogleSheetTitle")}
                  </span>

                  <h2>
                    {t("knowledgeGoogleSelectSpreadsheet")}
                  </h2>
                </div>

                <button
                  className="icon-button"
                  onClick={() => {
                    setGoogleSheetsOpen(false);
                    setSelectedGoogleSheet(null);
                  }}
                  disabled={googleAdding}
                >
                  <X size={18} />
                </button>
              </header>

              <div className="management-form">
                {googleSheetsLoading ? (
                  <div className="conversation-loading">
                    <LoaderCircle className="spin" size={24} />
                  </div>
                ) : (
                  <div className="knowledge-source-list">
                    {googleSheets.map((sheet) => (
                      <div
                        key={sheet.spreadsheet_id}
                        className="knowledge-source-row google-source-row"
                        onClick={() => {
                          if (!googleAdding) {
                            void handleSelectGoogleSheet(sheet);
                          }
                        }}
                        style={{ cursor: "pointer" }}
                      >
                        <div className="management-icon">
                          <FileSpreadsheet size={18} />
                        </div>

                        <div className="knowledge-source-info">
                          <strong>{sheet.name}</strong>

                          <span>{sheet.spreadsheet_id}</span>
                        </div>
                      </div>
                    ))}

                    {!googleSheets.length && (
                      <div className="empty-management">
                        <FileSpreadsheet size={30} />

                        <strong>{t("knowledgeGoogleNoSheets")}</strong>

                        <span>{t("knowledgeGoogleNoSheetsDescription")}</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        )
      }


      {/* ===================================================
          GOOGLE SHEET TABS PICKER
          =================================================== */}

      {
        googleTabsOpen && (
          <div
            className="management-modal-backdrop"
            onMouseDown={() => {
              if (!googleAdding) {
                setGoogleTabsOpen(false);
                setSelectedGoogleSheet(null);
              }
            }}
          >
            <div
              className="management-modal knowledge-source-modal"
              onMouseDown={(event) =>
                event.stopPropagation()
              }
            >
              <header className="management-modal-header">
                <div>
                  <span className="eyebrow">
                    {selectedGoogleSheet?.name}
                  </span>

                  <h2>
                    {t("knowledgeGoogleSelectTab")}
                  </h2>
                </div>

                <button
                  className="icon-button"
                  onClick={() => {
                    setGoogleTabsOpen(false);
                    setSelectedGoogleSheet(null);
                  }}
                  disabled={googleAdding}
                >
                  <X size={18} />
                </button>
              </header>

              <div className="management-form">
                {googleTabsLoading ? (
                  <div className="conversation-loading">
                    <LoaderCircle className="spin" size={24} />
                  </div>
                ) : (
                  <div className="knowledge-source-list">
                    {googleTabs.map((tab) => (
                      <div
                        key={tab.sheetId}
                        className="knowledge-source-row google-source-row"
                        onClick={() => {
                          if (!googleAdding) {
                            void handleAddGoogleSheetSource(tab);
                          }
                        }}
                        style={{ cursor: "pointer" }}
                      >
                        <div className="management-icon">
                          <FileText size={18} />
                        </div>

                        <div className="knowledge-source-info">
                          <strong>{tab.title}</strong>
                        </div>
                      </div>
                    ))}

                    {!googleTabs.length && (
                      <div className="empty-management">
                        <FileText size={30} />

                        <strong>{t("knowledgeGoogleNoTabs")}</strong>

                        <span>{t("knowledgeGoogleNoTabsDescription")}</span>
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
