import { useTranslation } from "react-i18next";
import {
  useEffect,
  useEffectEvent,
  useRef,
  useState,
  type ChangeEvent,
} from "react";

import {
  BrainCircuit,
  Database,
  File,
  FileSpreadsheet,
  FileText,
  Folder,
  Link2,
  LoaderCircle,
  Pencil,
  Plus,
  RefreshCw,
  Search,
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
  addGoogleDocSource,
  addGoogleDriveFileSource,
  addGoogleDriveFolderSource,
  addGoogleSheetSource,
  checkGoogleDriveScopes,
  disconnectGoogle,
  expandGoogleScopes,
  getGoogleStatus,
  getIngestionStatus,
  listGoogleDriveFiles,
  listGoogleDriveFolders,
  listGoogleSheets,
  listGoogleSheetTabs,
  startGoogleOAuth,
  syncDriveFileSource,
  syncDriveFolder,
  syncGoogleSheetSource,
  type GoogleDriveFileItem,
  type GoogleDriveFolderItem,
  type GoogleDriveScopeStatus,
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


const GOOGLE_DOC_MIME_TYPE =
  "application/vnd.google-apps.document";


function isSyncInProgress(
  status: string | null | undefined,
) {
  return (
    status === "syncing" ||
    status === "indexing"
  );
}


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


  // =========================================================
  // DRIVE / DOCS STATE
  // =========================================================

  const [
    driveScopeStatus,
    setDriveScopeStatus,
  ] = useState<GoogleDriveScopeStatus | null>(
    null,
  );

  const [
    driveFilesOpen,
    setDriveFilesOpen,
  ] = useState(false);

  const [
    driveFiles,
    setDriveFiles,
  ] = useState<GoogleDriveFileItem[]>([]);

  const [
    driveFilesLoading,
    setDriveFilesLoading,
  ] = useState(false);

  const [
    driveFilesLoadingMore,
    setDriveFilesLoadingMore,
  ] = useState(false);

  const [
    driveFilesNextPageToken,
    setDriveFilesNextPageToken,
  ] = useState<string | null>(null);

  const [
    driveFoldersOpen,
    setDriveFoldersOpen,
  ] = useState(false);

  const [
    driveFolders,
    setDriveFolders,
  ] = useState<GoogleDriveFolderItem[]>([]);

  const [
    driveFoldersLoading,
    setDriveFoldersLoading,
  ] = useState(false);

  const [
    driveFoldersLoadingMore,
    setDriveFoldersLoadingMore,
  ] = useState(false);

  const [
    driveFoldersNextPageToken,
    setDriveFoldersNextPageToken,
  ] = useState<string | null>(null);

  const [
    addSourceMode,
    setAddSourceMode,
  ] = useState<
    "menu" | "sheets" | "docs" | "drive-file" | "drive-folder"
  >("menu");

  const [
    driveSearchQuery,
    setDriveSearchQuery,
  ] = useState("");

  const driveFilesSearchRef =
    useRef<HTMLInputElement | null>(null);

  const driveFoldersSearchRef =
    useRef<HTMLInputElement | null>(null);

  const driveFilesTriggerRef =
    useRef<HTMLElement | null>(null);

  const driveFoldersTriggerRef =
    useRef<HTMLElement | null>(null);

  const driveFilesRequestRef =
    useRef(0);

  const driveFoldersRequestRef =
    useRef(0);


  const refreshAfterWindowFocus =
    useEffectEvent(() => {
      setGoogleConnecting(false);

      const requests: Promise<unknown>[] = [
        loadGoogleStatus(),
        loadDriveScopeStatus(),
      ];

      if (
        sourcesOpen &&
        selectedKnowledgeBase
      ) {
        requests.push(
          loadSources(
            selectedKnowledgeBase.id,
          ),
        );
      }

      void Promise.all(requests);
    });


  useEffect(() => {
    void loadData();
  }, []);


  function getSyncStatusLabel(
    status: string | null | undefined,
  ) {
    switch (status) {
      case "syncing":
        return t("knowledgeGoogleSyncing");
      case "indexing":
        return t("knowledgeGoogleIndexing");
      case "partial_failed":
        return t("knowledgeGooglePartialFailed");
      case "uploaded":
        return t("knowledgeGoogleUploaded");
      case "failed":
        return t("knowledgeGoogleFailed");
      case "disconnected":
        return t("knowledgeGoogleDisconnected");
      case "synced":
        return t("knowledgeGoogleSynced");
      default:
        return null;
    }
  }


  function getFreshnessLabel(
    freshness: string | null | undefined,
  ) {
    switch (freshness) {
      case "syncing":
        return t("knowledgeGoogleSyncing");
      case "failed":
        return t("knowledgeGoogleFailed");
      case "disconnected":
        return t("knowledgeGoogleDisconnected");
      case "fresh":
        return t("knowledgeGoogleFresh");
      case "changed":
        return t("knowledgeGoogleChanged");
      case "static":
        return t("knowledgeGoogleStatic");
      default:
        return null;
    }
  }


  useEffect(() => {
    const handleWindowFocus = () => {
      refreshAfterWindowFocus();
    };

    window.addEventListener(
      "focus",
      handleWindowFocus,
    );

    return () => {
      window.removeEventListener(
        "focus",
        handleWindowFocus,
      );
    };
  }, []);


  useEffect(() => {
    if (
      !driveFilesOpen &&
      !driveFoldersOpen
    ) {
      return;
    }

    const handleKeyDown = (
      event: KeyboardEvent,
    ) => {
      if (event.key !== "Escape") {
        return;
      }

      event.preventDefault();

      if (driveFilesOpen) {
        closeDriveFilesPicker();
      } else {
        closeDriveFoldersPicker();
      }
    };

    window.addEventListener(
      "keydown",
      handleKeyDown,
    );

    return () => {
      window.removeEventListener(
        "keydown",
        handleKeyDown,
      );
    };
  }, [
    driveFilesOpen,
    driveFoldersOpen,
  ]);


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
    setAddSourceMode("menu");

    await Promise.all([
      loadSources(
        knowledgeBase.id,
      ),
      loadGoogleStatus(),
      loadDriveScopeStatus(),
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
      clearDriveState();
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

      if (
        isSyncInProgress(
          result.sync_status,
        )
      ) {
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

      if (
        isSyncInProgress(
          result.sync_status,
        )
      ) {
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


  // =========================================================
  // DRIVE / DOCS HANDLERS
  // =========================================================

  function restoreDriveTrigger(
    trigger: HTMLElement | null,
  ) {
    window.requestAnimationFrame(() => {
      trigger?.focus();
    });
  }


  function closeDriveFilesPicker() {
    setDriveFilesOpen(false);
    restoreDriveTrigger(
      driveFilesTriggerRef.current,
    );
  }


  function closeDriveFoldersPicker() {
    setDriveFoldersOpen(false);
    restoreDriveTrigger(
      driveFoldersTriggerRef.current,
    );
  }


  function clearDriveState() {
    driveFilesRequestRef.current += 1;
    driveFoldersRequestRef.current += 1;
    setDriveScopeStatus(null);
    setDriveFilesOpen(false);
    setDriveFoldersOpen(false);
    setDriveFiles([]);
    setDriveFolders([]);
    setDriveFilesNextPageToken(null);
    setDriveFoldersNextPageToken(null);
    setDriveFilesLoading(false);
    setDriveFoldersLoading(false);
    setDriveFilesLoadingMore(false);
    setDriveFoldersLoadingMore(false);
    setDriveSearchQuery("");
    setAddSourceMode("menu");
  }

  async function loadDriveScopeStatus() {
    try {
      const status =
        await checkGoogleDriveScopes();
      setDriveScopeStatus(status);
    } catch {
      setDriveScopeStatus(null);
    }
  }

  async function handleExpandScopes() {
    try {
      setGoogleConnecting(true);
      const result =
        await expandGoogleScopes();
      window.open(
        result.authorization_url,
        "_blank",
      );
    } catch {
      setError(
        t("knowledgeGoogleConnectionError"),
      );
    } finally {
      setGoogleConnecting(false);
    }
  }

  async function loadDriveFiles(
    query: string,
    mode: "docs" | "drive-file",
    pageToken?: string,
  ) {
    const append = Boolean(pageToken);
    const requestId =
      ++driveFilesRequestRef.current;

    try {
      if (append) {
        setDriveFilesLoadingMore(true);
      } else {
        setDriveFilesLoading(true);
      }

      setError("");

      const result =
        await listGoogleDriveFiles(
          query,
          pageToken,
          mode === "docs"
            ? GOOGLE_DOC_MIME_TYPE
            : undefined,
        );

      if (
        requestId !==
        driveFilesRequestRef.current
      ) {
        return;
      }

      setDriveFiles((current) =>
        append
          ? [
              ...current,
              ...result.files,
            ]
          : result.files,
      );
      setDriveFilesNextPageToken(
        result.next_page_token,
      );
    } catch (err) {
      if (
        requestId !==
        driveFilesRequestRef.current
      ) {
        return;
      }

      console.error(err);
      setError(
        t("knowledgeGoogleDriveFilesLoadError"),
      );
    } finally {
      if (
        requestId !==
        driveFilesRequestRef.current
      ) {
        return;
      }

      if (append) {
        setDriveFilesLoadingMore(false);
      } else {
        setDriveFilesLoading(false);
      }
    }
  }


  async function handleOpenDriveFiles(
    mode: "docs" | "drive-file",
    trigger: HTMLElement,
  ) {
    if (
      !driveScopeStatus?.has_drive_scope
    ) {
      await handleExpandScopes();
      return;
    }

    driveFilesTriggerRef.current =
      trigger;
    setAddSourceMode(mode);
    setDriveSearchQuery("");
    setDriveFiles([]);
    setDriveFilesNextPageToken(null);
    setDriveFilesOpen(true);

    await loadDriveFiles("", mode);
  }


  async function handleSearchDriveFiles(
    query: string,
  ) {
    if (
      addSourceMode !== "docs" &&
      addSourceMode !== "drive-file"
    ) {
      return;
    }

    setDriveFiles([]);
    setDriveFilesNextPageToken(null);
    await loadDriveFiles(
      query,
      addSourceMode,
    );
  }


  async function handleLoadMoreDriveFiles() {
    if (
      !driveFilesNextPageToken ||
      (addSourceMode !== "docs" &&
        addSourceMode !== "drive-file")
    ) {
      return;
    }

    await loadDriveFiles(
      driveSearchQuery,
      addSourceMode,
      driveFilesNextPageToken,
    );
  }

  async function handleAddGoogleDoc(
    file: GoogleDriveFileItem,
  ) {
    if (!selectedKnowledgeBase) return;
    try {
      setGoogleAdding(true);
      setError("");
      const result =
        await addGoogleDocSource(
          selectedKnowledgeBase.id,
          file.id,
          file.name,
        );
      closeDriveFilesPicker();
      setAddSourceMode("menu");
      await loadSources(
        selectedKnowledgeBase.id,
      );

      if (
        isSyncInProgress(
          result.sync_status,
        )
      ) {
        startPollingIngestion(
          selectedKnowledgeBase.id,
          result.source_id,
        );
      }
    } catch {
      setError(
        t("knowledgeGoogleAddSourceError"),
      );
    } finally {
      setGoogleAdding(false);
    }
  }

  async function handleAddDriveFile(
    file: GoogleDriveFileItem,
  ) {
    if (!selectedKnowledgeBase) return;
    try {
      setGoogleAdding(true);
      setError("");
      const result =
        await addGoogleDriveFileSource(
          selectedKnowledgeBase.id,
          file.id,
          file.name,
          file.mime_type,
        );
      closeDriveFilesPicker();
      setAddSourceMode("menu");
      await loadSources(
        selectedKnowledgeBase.id,
      );

      if (
        isSyncInProgress(
          result.sync_status,
        )
      ) {
        startPollingIngestion(
          selectedKnowledgeBase.id,
          result.source_id,
        );
      }
    } catch {
      setError(
        t("knowledgeGoogleAddSourceError"),
      );
    } finally {
      setGoogleAdding(false);
    }
  }

  async function loadDriveFolders(
    query: string,
    pageToken?: string,
  ) {
    const append = Boolean(pageToken);
    const requestId =
      ++driveFoldersRequestRef.current;

    try {
      if (append) {
        setDriveFoldersLoadingMore(true);
      } else {
        setDriveFoldersLoading(true);
      }

      setError("");

      const result =
        await listGoogleDriveFolders(
          query,
          pageToken,
        );

      if (
        requestId !==
        driveFoldersRequestRef.current
      ) {
        return;
      }

      setDriveFolders((current) =>
        append
          ? [
              ...current,
              ...result.folders,
            ]
          : result.folders,
      );
      setDriveFoldersNextPageToken(
        result.next_page_token,
      );
    } catch (err) {
      if (
        requestId !==
        driveFoldersRequestRef.current
      ) {
        return;
      }

      console.error(err);
      setError(
        t("knowledgeGoogleDriveFoldersLoadError"),
      );
    } finally {
      if (
        requestId !==
        driveFoldersRequestRef.current
      ) {
        return;
      }

      if (append) {
        setDriveFoldersLoadingMore(false);
      } else {
        setDriveFoldersLoading(false);
      }
    }
  }


  async function handleOpenDriveFolders(
    trigger: HTMLElement,
  ) {
    if (
      !driveScopeStatus?.has_drive_scope
    ) {
      await handleExpandScopes();
      return;
    }

    driveFoldersTriggerRef.current =
      trigger;
    setAddSourceMode("drive-folder");
    setDriveSearchQuery("");
    setDriveFolders([]);
    setDriveFoldersNextPageToken(null);
    setDriveFoldersOpen(true);

    await loadDriveFolders("");
  }


  async function handleSearchDriveFolders(
    query: string,
  ) {
    setDriveFolders([]);
    setDriveFoldersNextPageToken(null);
    await loadDriveFolders(query);
  }


  async function handleLoadMoreDriveFolders() {
    if (!driveFoldersNextPageToken) {
      return;
    }

    await loadDriveFolders(
      driveSearchQuery,
      driveFoldersNextPageToken,
    );
  }

  async function handleAddDriveFolder(
    folder: GoogleDriveFolderItem,
  ) {
    if (!selectedKnowledgeBase) return;
    try {
      setGoogleAdding(true);
      setError("");
      const result =
        await addGoogleDriveFolderSource(
          selectedKnowledgeBase.id,
          folder.id,
          folder.name,
        );
      closeDriveFoldersPicker();
      setAddSourceMode("menu");
      await loadSources(
        selectedKnowledgeBase.id,
      );

      if (
        isSyncInProgress(
          result.sync_status,
        )
      ) {
        startPollingIngestion(
          selectedKnowledgeBase.id,
          result.source_id,
        );
      }
    } catch {
      setError(
        t("knowledgeGoogleAddSourceError"),
      );
    } finally {
      setGoogleAdding(false);
    }
  }

  async function handleSyncDriveFolder(
    source: KnowledgeSource,
  ) {
    if (!selectedKnowledgeBase) return;
    try {
      setGoogleAdding(true);
      setError("");
      const result = await syncDriveFolder(
        selectedKnowledgeBase.id,
        source.id,
      );

      if (
        isSyncInProgress(
          result.sync_status,
        )
      ) {
        startPollingIngestion(
          selectedKnowledgeBase.id,
          source.id,
        );
      }

      await loadSources(
        selectedKnowledgeBase.id,
      );
    } catch {
      setError(
        t("knowledgeGoogleAddSourceError"),
      );
    } finally {
      setGoogleAdding(false);
    }
  }

  async function handleSyncDriveFile(
    source: KnowledgeSource,
  ) {
    if (!selectedKnowledgeBase) return;
    try {
      setGoogleAdding(true);
      setError("");
      const result =
        await syncDriveFileSource(
          selectedKnowledgeBase.id,
          source.id,
        );

      if (
        isSyncInProgress(
          result.sync_status,
        )
      ) {
        startPollingIngestion(
          selectedKnowledgeBase.id,
          source.id,
        );
      }

      await loadSources(
        selectedKnowledgeBase.id,
      );
    } catch {
      setError(
        t("knowledgeGoogleAddSourceError"),
      );
    } finally {
      setGoogleAdding(false);
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
            !isSyncInProgress(
              result.sync_status,
            )
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
                        {t("knowledgeGoogleWorkspaceTitle")}
                      </strong>

                      <span>
                        {t("knowledgeGoogleWorkspaceDescription")}
                      </span>
                    </div>

                    <div className="knowledge-google-source-buttons">
                      <button
                        className="google-button"
                        onClick={() => {
                          setAddSourceMode("sheets");
                          void handleOpenGoogleSheets();
                        }}
                        disabled={googleSheetsLoading}
                      >
                        {googleSheetsLoading ? (
                          <LoaderCircle className="spin" size={16} />
                        ) : (
                          <FileSpreadsheet size={16} />
                        )}
                        {t("knowledgeGoogleSelectSheet")}
                      </button>

                      <button
                        className="google-button"
                        onClick={(event) => {
                          void handleOpenDriveFiles(
                            "docs",
                            event.currentTarget,
                          );
                        }}
                        disabled={driveFilesLoading}
                      >
                        {driveFilesLoading ? (
                          <LoaderCircle className="spin" size={16} />
                        ) : (
                          <FileText size={16} />
                        )}
                        {t("knowledgeGoogleDocs")}
                      </button>

                      <button
                        className="google-button"
                        onClick={(event) => {
                          void handleOpenDriveFiles(
                            "drive-file",
                            event.currentTarget,
                          );
                        }}
                        disabled={driveFilesLoading}
                      >
                        {driveFilesLoading ? (
                          <LoaderCircle className="spin" size={16} />
                        ) : (
                          <File size={16} />
                        )}
                        {t("knowledgeGoogleDriveFile")}
                      </button>

                      <button
                        className="google-button"
                        onClick={(event) => {
                          void handleOpenDriveFolders(
                            event.currentTarget,
                          );
                        }}
                        disabled={driveFoldersLoading}
                      >
                        {driveFoldersLoading ? (
                          <LoaderCircle className="spin" size={16} />
                        ) : (
                          <Folder size={16} />
                        )}
                        {t("knowledgeGoogleDriveFolder")}
                      </button>
                    </div>

                    {driveScopeStatus &&
                      !driveScopeStatus.has_drive_scope && (
                        <div className="knowledge-drive-permissions">
                          <span>
                            {t("knowledgeGoogleAdditionalPermissions")}
                          </span>
                          <button
                            className="secondary-button"
                            onClick={() =>
                              void handleExpandScopes()
                            }
                            disabled={googleConnecting}
                          >
                            {t("knowledgeGoogleExpandPermissions")}
                          </button>
                        </div>
                      )}
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

                        const isDriveFolder =
                          source.source_type ===
                          "google_drive_folder";

                        const isGoogleDriveSource =
                          source.source_type ===
                            "google_doc" ||
                          source.source_type ===
                            "google_drive_file" ||
                          isDriveFolder;

                        const isPolling =
                          syncPollingSourceId ===
                          source.id;

                        const syncInProgress =
                          isPolling ||
                          isSyncInProgress(
                            source.sync_status,
                          );

                        const syncLabel = isPolling
                          ? t("knowledgeGoogleSyncing")
                          : getSyncStatusLabel(
                              source.sync_status,
                            ) ||
                            getSyncStatusLabel(
                              source.status,
                            );

                        const freshnessLabel =
                          getFreshnessLabel(
                            source.freshness,
                          );

                        const prefersFreshness =
                          source.freshness ===
                            "disconnected" ||
                          source.sync_status ===
                            "synced";

                        const driveStatusLabel =
                          prefersFreshness
                            ? freshnessLabel || syncLabel
                            : syncLabel || freshnessLabel;

                        return (
                          <div
                            key={
                              source.id
                            }
                            className={`
                              knowledge-source-row
                              ${isGoogleDriveSource ? "google-source-row" : ""}
                            `}
                          >
                            <div className="management-icon">
                              {isGoogleSheets ? (
                                <FileSpreadsheet
                                  size={18}
                                />
                              ) : isDriveFolder ? (
                                <Folder size={18} />
                              ) : source.source_type === "google_doc" ? (
                                <FileText size={18} />
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
                                ) : isGoogleDriveSource ? (
                                  <>
                                    {driveStatusLabel || t("knowledgeGoogleSyncPending")}
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
                                      syncLabel ||
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
                                  syncInProgress
                                }
                                title={t("knowledgeGoogleSync")}
                              >
                                <RefreshCw
                                  size={16}
                                  className={
                                    syncInProgress
                                      ? "spin"
                                      : ""
                                  }
                                />
                              </button>
                            )}

                            {canWrite && isDriveFolder && (
                              <button
                                className="icon-button google-sync-button"
                                onClick={() =>
                                  void handleSyncDriveFolder(source)
                                }
                                disabled={
                                  syncInProgress
                                }
                                title={t("knowledgeGoogleSyncFolder")}
                              >
                                <RefreshCw
                                  size={16}
                                  className={syncInProgress ? "spin" : ""}
                                />
                              </button>
                            )}

                            {canWrite &&
                              isGoogleDriveSource &&
                              !isDriveFolder && (
                                <button
                                  className="icon-button google-sync-button"
                                  onClick={() =>
                                    void handleSyncDriveFile(source)
                                  }
                                  disabled={
                                    syncInProgress
                                  }
                                  title={t("knowledgeGoogleSync")}
                                >
                                  <RefreshCw
                                    size={16}
                                    className={syncInProgress ? "spin" : ""}
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

      {driveFilesOpen && (
        <div
          className="management-modal-backdrop"
          onMouseDown={() => {
            if (!googleAdding) {
              closeDriveFilesPicker();
            }
          }}
        >
          <div
            className="management-modal knowledge-source-modal"
            onMouseDown={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label={t("knowledgeGoogleSelectFile")}
          >
            <header className="management-modal-header">
              <div>
                <span className="eyebrow">
                  {addSourceMode === "docs"
                    ? t("knowledgeGoogleDocs")
                    : t("knowledgeGoogleDriveFile")}
                </span>
                <h2>{t("knowledgeGoogleSelectFile")}</h2>
              </div>
              <button
                className="icon-button"
                aria-label={t("knowledgeGoogleClose")}
                onClick={closeDriveFilesPicker}
                disabled={googleAdding}
              >
                <X size={18} />
              </button>
            </header>
            <div className="management-form">
              <label className="knowledge-drive-search">
                <Search size={16} />
                <input
                  ref={driveFilesSearchRef}
                  autoFocus
                  aria-label={t("knowledgeGoogleSearchDrive")}
                  value={driveSearchQuery}
                  placeholder={t("knowledgeGoogleSearchDrive")}
                  onChange={(event) => {
                    driveFilesRequestRef.current += 1;
                    setDriveSearchQuery(
                      event.target.value,
                    );
                    setDriveFiles([]);
                    setDriveFilesNextPageToken(null);
                    setDriveFilesLoading(false);
                    setDriveFilesLoadingMore(false);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      void handleSearchDriveFiles(
                        event.currentTarget.value,
                      );
                    }
                  }}
                />
              </label>
              {driveFilesLoading ? (
                <div className="conversation-loading">
                  <LoaderCircle className="spin" size={24} />
                </div>
              ) : (
                <div className="knowledge-source-list">
                  {driveFiles
                    .filter((file) =>
                      addSourceMode !== "docs" ||
                      file.mime_type ===
                        GOOGLE_DOC_MIME_TYPE,
                    )
                    .map((file) => {
                      const isDoc = file.mime_type ===
                        GOOGLE_DOC_MIME_TYPE;
                      return (
                        <div
                          key={file.id}
                          className="knowledge-source-row google-source-row"
                        >
                          <div className="management-icon">
                            <FileText size={18} />
                          </div>
                          <div className="knowledge-source-info">
                            <strong>{file.name}</strong>
                            <span>{file.modified_time || ""}</span>
                          </div>
                          <button
                            className="google-button"
                            disabled={googleAdding}
                            onClick={() => {
                              if (isDoc) {
                                void handleAddGoogleDoc(file);
                              } else {
                                void handleAddDriveFile(file);
                              }
                            }}
                          >
                            {isDoc
                              ? t("knowledgeGoogleAddDoc")
                              : t("knowledgeGoogleAddFile")}
                          </button>
                        </div>
                      );
                    })}
                  {!driveFiles.filter((file) =>
                    addSourceMode !== "docs" ||
                    file.mime_type ===
                      GOOGLE_DOC_MIME_TYPE,
                  ).length && (
                    <div className="empty-management">
                      <FileText size={30} />
                      <strong>{t("knowledgeGoogleNoDriveFiles")}</strong>
                    </div>
                  )}
                  {driveFilesNextPageToken && (
                    <button
                      className="secondary-button knowledge-drive-load-more"
                      onClick={() =>
                        void handleLoadMoreDriveFiles()
                      }
                      disabled={driveFilesLoadingMore}
                    >
                      {driveFilesLoadingMore && (
                        <LoaderCircle
                          className="spin"
                          size={16}
                        />
                      )}
                      {t("knowledgeGoogleLoadMore")}
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {driveFoldersOpen && (
        <div
          className="management-modal-backdrop"
          onMouseDown={() => {
            if (!googleAdding) {
              closeDriveFoldersPicker();
            }
          }}
        >
          <div
            className="management-modal knowledge-source-modal"
            onMouseDown={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label={t("knowledgeGoogleSelectFolder")}
          >
            <header className="management-modal-header">
              <div>
                <span className="eyebrow">
                  {t("knowledgeGoogleDriveFolder")}
                </span>
                <h2>{t("knowledgeGoogleSelectFolder")}</h2>
              </div>
              <button
                className="icon-button"
                aria-label={t("knowledgeGoogleClose")}
                onClick={closeDriveFoldersPicker}
                disabled={googleAdding}
              >
                <X size={18} />
              </button>
            </header>
            <div className="management-form">
              <label className="knowledge-drive-search">
                <Search size={16} />
                <input
                  ref={driveFoldersSearchRef}
                  autoFocus
                  aria-label={t("knowledgeGoogleSearchDrive")}
                  value={driveSearchQuery}
                  placeholder={t("knowledgeGoogleSearchDrive")}
                  onChange={(event) => {
                    driveFoldersRequestRef.current += 1;
                    setDriveSearchQuery(
                      event.target.value,
                    );
                    setDriveFolders([]);
                    setDriveFoldersNextPageToken(null);
                    setDriveFoldersLoading(false);
                    setDriveFoldersLoadingMore(false);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      void handleSearchDriveFolders(
                        event.currentTarget.value,
                      );
                    }
                  }}
                />
              </label>
              {driveFoldersLoading ? (
                <div className="conversation-loading">
                  <LoaderCircle className="spin" size={24} />
                </div>
              ) : (
                <div className="knowledge-source-list">
                  {driveFolders.map((folder) => (
                    <div
                      key={folder.id}
                      className="knowledge-source-row google-source-row"
                    >
                      <div className="management-icon">
                        <Folder size={18} />
                      </div>
                      <div className="knowledge-source-info">
                        <strong>{folder.name}</strong>
                        <span>{folder.modified_time || ""}</span>
                      </div>
                      <button
                        className="google-button"
                        disabled={googleAdding}
                        onClick={() =>
                          void handleAddDriveFolder(folder)
                        }
                      >
                        {t("knowledgeGoogleAddFolder")}
                      </button>
                    </div>
                  ))}
                  {!driveFolders.length && (
                    <div className="empty-management">
                      <Folder size={30} />
                      <strong>{t("knowledgeGoogleNoDriveFolders")}</strong>
                    </div>
                  )}
                  {driveFoldersNextPageToken && (
                    <button
                      className="secondary-button knowledge-drive-load-more"
                      onClick={() =>
                        void handleLoadMoreDriveFolders()
                      }
                      disabled={driveFoldersLoadingMore}
                    >
                      {driveFoldersLoadingMore && (
                        <LoaderCircle
                          className="spin"
                          size={16}
                        />
                      )}
                      {t("knowledgeGoogleLoadMore")}
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
