import { useTranslation } from "react-i18next";
import {
  useCallback,
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
  LogOut,
  LoaderCircle,
  Info,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Shield,
  Store as StoreIcon,
  Trash2,
  Upload,
  Users,
  X,
} from "lucide-react";

import {
  createKnowledgeBase,
  deleteKnowledgeBase,
  getKnowledgeBases,
  retryKnowledgeBaseProvisioning,
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

  active: boolean;

  store_ids: number[];
}


const EMPTY_FORM: KnowledgeFormState = {
  name: "",
  scope: "selected_stores",
  active: true,
  store_ids: [],
};


const GOOGLE_DOC_MIME_TYPE =
  "application/vnd.google-apps.document";

type InitialSource =
  | "local"
  | "sheets"
  | "docs"
  | "drive-file"
  | "drive-folder";

const PROVISIONING_STATUS_KEYS: Record<
  KnowledgeBase["external_status"],
  string
> = {
  pending: "knowledgeI18nProvisioningPending",
  provisioning: "knowledgeI18nProvisioningInProgress",
  retrying: "knowledgeI18nProvisioningRetrying",
  ready: "knowledgeI18nProvisioningReady",
  failed: "knowledgeI18nProvisioningFailed",
  deleting: "knowledgeI18nDeletingKnowledgeBase",
};

const PROVISIONING_STAGE_KEYS: Record<
  NonNullable<KnowledgeBase["provisioning_stage"]>,
  string
> = {
  queued: "knowledgeI18nStageQueued",
  creating_vector_index: "knowledgeI18nStageStorage",
  creating_knowledge_base: "knowledgeI18nStageKnowledge",
  creating_data_source: "knowledgeI18nStageSources",
  finalizing: "knowledgeI18nStageFinalizing",
  retrying: "knowledgeI18nStageRetrying",
  ready: "knowledgeI18nProvisioningReady",
  failed: "knowledgeI18nProvisioningFailed",
  deleting: "knowledgeI18nDeletingKnowledgeBase",
};


function isProvisioningFailure(error: unknown) {
  return (
    typeof error === "object" &&
    error !== null &&
    "response" in error &&
    (error as { response?: { data?: { detail?: { code?: string } } } }).response
      ?.data?.detail?.code === "BEDROCK_PROVISIONING_FAILED"
  );
}


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


function hasProvisioningChange(
  current: KnowledgeBase,
  next: KnowledgeBase,
) {
  return (
    current.external_status !== next.external_status ||
    current.external_last_error !== next.external_last_error ||
    current.external_id !== next.external_id ||
    current.provisioning_stage !== next.provisioning_stage ||
    current.provisioning_started_at !== next.provisioning_started_at ||
    current.provisioning_stage_started_at !== next.provisioning_stage_started_at
  );
}


function isSlowProvisioning(knowledgeBase: KnowledgeBase) {
  if (!knowledgeBase.provisioning_started_at) return false;
  return Date.now() - Date.parse(knowledgeBase.provisioning_started_at) > 180_000;
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

  const [retryingKnowledgeBaseId, setRetryingKnowledgeBaseId] =
    useState<number | null>(null);
  const [deletingKnowledgeBase, setDeletingKnowledgeBase] = useState<KnowledgeBase | null>(null);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [deleting, setDeleting] = useState(false);

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

  const [selectedInitialSource, setSelectedInitialSource] =
    useState<InitialSource | null>(null);

  const [securityAcknowledged, setSecurityAcknowledged] =
    useState(false);

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

  const [googleSheetImportMode, setGoogleSheetImportMode] =
    useState<"choose" | "sheet">("choose");

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

  const [disconnectGoogleOpen, setDisconnectGoogleOpen] = useState(false);
  const [disconnectingGoogle, setDisconnectingGoogle] = useState(false);
  const [disconnectGoogleError, setDisconnectGoogleError] = useState("");

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

  const refreshProvisioningStatuses = useCallback(async () => {
    try {
      const response = await getKnowledgeBases();
      const nextItems = response.items;

      setItems((currentItems) => {
        if (
          currentItems.length === nextItems.length &&
          currentItems.every((item, index) =>
            item.id === nextItems[index]?.id &&
            !hasProvisioningChange(item, nextItems[index]),
          )
        ) {
          return currentItems;
        }
        return currentItems.map((item) => {
          const next = nextItems.find((candidate) => candidate.id === item.id);
          return next && hasProvisioningChange(item, next)
            ? { ...item, ...next }
            : item;
        });
      });

      setSelectedKnowledgeBase((current) => {
        const next = current && nextItems.find((item) => item.id === current.id);
        return next && hasProvisioningChange(current, next)
          ? { ...current, ...next }
          : current;
      });
    } catch (err) {
      console.error(err);
    }
  }, []);

  const pollingTimeoutRef = useRef<number | undefined>(undefined);
  const isPollingRef = useRef(false);
  const pollingInFlightRef = useRef(false);

  const stopPolling = useCallback(() => {
    isPollingRef.current = false;
    if (pollingTimeoutRef.current !== undefined) {
      window.clearTimeout(pollingTimeoutRef.current);
      pollingTimeoutRef.current = undefined;
    }
  }, []);

  const startPolling = useCallback(() => {
    if (isPollingRef.current) return;
    isPollingRef.current = true;

    const poll = async () => {
      pollingTimeoutRef.current = undefined;
      if (!isPollingRef.current || pollingInFlightRef.current) return;

      pollingInFlightRef.current = true;
      try {
        await refreshProvisioningStatuses();
      } finally {
        pollingInFlightRef.current = false;
        if (isPollingRef.current) {
          pollingTimeoutRef.current = window.setTimeout(poll, 7_500);
        }
      }
    };

    pollingTimeoutRef.current = window.setTimeout(poll, 7_500);
  }, [refreshProvisioningStatuses]);

  const hasActiveProvisioning = items.some(
    (item) =>
      item.external_status === "pending" ||
      item.external_status === "provisioning" ||
      item.external_status === "retrying",
  );

  useEffect(() => {
    if (hasActiveProvisioning) {
      startPolling();
    } else {
      stopPolling();
    }
  }, [hasActiveProvisioning, startPolling, stopPolling]);

  useEffect(() => stopPolling, [stopPolling]);


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

      await loadData();

      setError(
        t(
          isProvisioningFailure(err)
            ? "knowledgeI18nProvisioningCreateError"
            : "knowledgeI18nSaveError",
        ),
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
    resetSecurityAcknowledgement();

    await Promise.all([
      loadSources(
        knowledgeBase.id,
      ),
      loadGoogleStatus(),
      loadDriveScopeStatus(),
    ]);
  }


  function resetSecurityAcknowledgement() {
    setSelectedInitialSource(null);
    setSecurityAcknowledged(false);
  }


  function requiresSecurityAcknowledgement(
    source: InitialSource,
  ) {
    if (selectedInitialSource !== source) {
      const sourceWasAlreadySelected = selectedInitialSource !== null;
      setSelectedInitialSource(source);
      if (sourceWasAlreadySelected) {
        setSecurityAcknowledged(false);
      }
      return sourceWasAlreadySelected || !securityAcknowledged;
    }

    return !securityAcknowledged;
  }


  function selectInitialSource(
    source: InitialSource,
  ) {
    if (selectedInitialSource !== source) {
      setSelectedInitialSource(source);
      setSecurityAcknowledged(false);
    }
  }


  function closeSources() {
    if (uploading) {
      return;
    }

    setSourcesOpen(false);
    resetSecurityAcknowledgement();
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


  function handleOpenDisconnectGoogle() {
    setDisconnectGoogleError("");
    setDisconnectGoogleOpen(true);
  }

  function handleCloseDisconnectGoogle() {
    if (disconnectingGoogle) return;
    setDisconnectGoogleOpen(false);
    setDisconnectGoogleError("");
  }

  async function handleDisconnectGoogle() {
    try {
      setDisconnectingGoogle(true);
      setDisconnectGoogleError("");
      await disconnectGoogle();
      clearDriveState();
      await loadGoogleStatus();
      setDisconnectGoogleOpen(false);
    } catch (err) {
      console.error(err);
      setDisconnectGoogleError(t("knowledgeGoogleDisconnectError"));
    } finally {
      setDisconnectingGoogle(false);
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
      setGoogleSheetImportMode("choose");
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
      resetSecurityAcknowledgement();

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


  async function handleRetryProvisioning(
    knowledgeBaseId: number,
  ) {
    try {
      setRetryingKnowledgeBaseId(knowledgeBaseId);
      setError("");
      await retryKnowledgeBaseProvisioning(knowledgeBaseId);
      await loadData();
    } catch (err) {
      console.error(err);
      await loadData();
      setError(t("knowledgeI18nProvisioningRetryError"));
    } finally {
      setRetryingKnowledgeBaseId(null);
    }
  }

  async function handleDeleteKnowledgeBase() {
    if (!deletingKnowledgeBase || deleteConfirmation !== deletingKnowledgeBase.name) return;
    try {
      setDeleting(true);
      await deleteKnowledgeBase(deletingKnowledgeBase.id);
      setItems((current) => current.filter((item) => item.id !== deletingKnowledgeBase.id));
      setDeletingKnowledgeBase(null);
      setDeleteConfirmation("");
    } catch (err) {
      console.error(err);
      setError(t("knowledgeI18nDeleteKnowledgeBaseError"));
    } finally {
      setDeleting(false);
    }
  }

  async function handleAddGoogleWorkbookSource() {
    if (!selectedKnowledgeBase || !selectedGoogleSheet) return;

    try {
      setGoogleAdding(true);
      setError("");
      const result = await addGoogleSheetSource(
        selectedKnowledgeBase.id,
        selectedGoogleSheet.spreadsheet_id,
        selectedGoogleSheet.name,
        undefined,
        "workbook",
      );
      setGoogleTabsOpen(false);
      setGoogleSheetsOpen(false);
      setSelectedGoogleSheet(null);
      resetSecurityAcknowledgement();
      await loadSources(selectedKnowledgeBase.id);
      if (isSyncInProgress(result.sync_status)) {
        startPollingIngestion(selectedKnowledgeBase.id, result.source_id);
      }
    } catch (err) {
      console.error(err);
      setError(t("knowledgeGoogleAddSourceError"));
    } finally {
      setGoogleAdding(false);
    }
  }


  function closeDriveFilesPicker() {
    setDriveFilesOpen(false);
    resetSecurityAcknowledgement();
    restoreDriveTrigger(
      driveFilesTriggerRef.current,
    );
  }


  function closeDriveFoldersPicker() {
    setDriveFoldersOpen(false);
    resetSecurityAcknowledgement();
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
    resetSecurityAcknowledgement();
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
      !selectedKnowledgeBase ||
      requiresSecurityAcknowledgement("local")
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
      resetSecurityAcknowledgement();

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
                    {t("knowledgeI18nProvisioningLabel")}
                  </strong>

                  <span
                    className={
                      knowledgeBase.external_status === "ready"
                        ? "status-pill active"
                        : "status-pill"
                    }
                  >
                    {t(
                      PROVISIONING_STATUS_KEYS[
                        knowledgeBase.external_status
                      ],
                    )}
                  </span>
                  {knowledgeBase.external_status !== "ready" &&
                    knowledgeBase.provisioning_stage && (
                      <small className="knowledge-card-provisioning-stage">
                        {t(PROVISIONING_STAGE_KEYS[knowledgeBase.provisioning_stage])}
                      </small>
                    )}
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
                      {knowledgeBase.external_status === "failed" && (
                        <button
                          className="secondary-button"
                          disabled={
                            retryingKnowledgeBaseId === knowledgeBase.id
                          }
                          onClick={() =>
                            void handleRetryProvisioning(
                              knowledgeBase.id,
                            )
                          }
                        >
                          <RefreshCw
                            className={
                              retryingKnowledgeBaseId === knowledgeBase.id
                                ? "spin"
                                : undefined
                            }
                            size={15}
                          />
                          {t("knowledgeI18nRetryProvisioning")}
                        </button>
                      )}

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
                      <button
                        className="secondary-button danger"
                        onClick={() => {
                          setDeletingKnowledgeBase(knowledgeBase);
                          setDeleteConfirmation("");
                        }}
                      >
                        <Trash2 size={15} />
                        {t("knowledgeI18nDeleteKnowledgeBase")}
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
              closeSources();
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
                  <p className="knowledge-modal-description">
                    {t("knowledgeDocumentsDescription")}
                  </p>
                </div>

                <button
                  className="icon-button"
                  onClick={() =>
                    closeSources()
                  }
                  disabled={
                    uploading
                  }
                >
                  <X size={18} />
                </button>
              </header>

              {canWrite && !googleStatus?.connected && (
                <div className="knowledge-google-connect-box">
                  <Link2 size={22} />
                  <div>
                    <strong>{t("knowledgeGoogleWorkspaceTitle")}</strong>
                    <span>{t("knowledgeGoogleNotConnected")}</span>
                  </div>
                  <button
                    className="primary-button google-button"
                    onClick={() =>
                      void handleConnectGoogle()
                    }
                    disabled={googleConnecting}
                  >
                    {googleConnecting ? (
                      <LoaderCircle className="spin" size={14} />
                    ) : (
                      <Link2 size={14} />
                    )}
                    {t("knowledgeGoogleConnect")}
                  </button>
                </div>
              )}


              <div className="management-form knowledge-documents-form">
                <div className="knowledge-add-source-heading">
                  <div>
                    <span className="eyebrow">{t("knowledgeAddSourceEyebrow")}</span>
                    <h3>{t("knowledgeAddSourceTitle")}</h3>
                  </div>
                  <span className="knowledge-source-count">
                    {t("knowledgeSourceCount", { count: sources.length })}
                  </span>
                  {selectedKnowledgeBase.external_status !== "ready" &&
                    selectedKnowledgeBase.provisioning_stage && (
                      <small className="knowledge-card-provisioning-stage">
                        {t(PROVISIONING_STAGE_KEYS[selectedKnowledgeBase.provisioning_stage])}
                      </small>
                    )}
                </div>
                {selectedKnowledgeBase.external_status !== "ready" && (
                  <section
                    className="knowledge-provisioning-notice"
                    role="status"
                    aria-labelledby="knowledge-provisioning-title"
                  >
                    <Info size={16} aria-hidden="true" />
                    <div className="knowledge-provisioning-notice-content">
                      <div className="knowledge-provisioning-notice-heading">
                        <strong id="knowledge-provisioning-title">
                          {t(selectedKnowledgeBase.external_status === "failed" ? "knowledgeI18nFailedTitle" : selectedKnowledgeBase.external_status === "retrying" ? "knowledgeI18nRetryingTitle" : "knowledgeI18nPreparingTitle")}
                        </strong>
                        <span className="knowledge-provisioning-status">
                          {t("knowledgeSourcesCurrentStatus", {
                            status: t(
                              PROVISIONING_STATUS_KEYS[
                                selectedKnowledgeBase.external_status
                              ],
                            ),
                          })}
                        </span>
                      </div>
                      <p>{t(selectedKnowledgeBase.external_status === "failed" ? "knowledgeI18nFailedBody" : selectedKnowledgeBase.external_status === "retrying" ? "knowledgeI18nRetryingBody" : "knowledgeI18nPreparingBody")}</p>
                      {selectedKnowledgeBase.external_status === "failed" ? <>
                        <small>{t("knowledgeI18nFailedSupport")}</small>
                        {canWrite && (
                          <button
                            className="secondary-button knowledge-provisioning-retry"
                            disabled={retryingKnowledgeBaseId === selectedKnowledgeBase.id}
                            onClick={() => void handleRetryProvisioning(selectedKnowledgeBase.id)}
                          >
                            {retryingKnowledgeBaseId === selectedKnowledgeBase.id
                              ? t("knowledgeI18nProvisioningRetrying")
                              : t("knowledgeI18nRetryProvisioning")}
                          </button>
                        )}
                      </> : <>
                        {selectedKnowledgeBase.provisioning_stage && (
                          <div className="knowledge-provisioning-stage">
                            <span className="knowledge-provisioning-stage-dot" aria-hidden="true" />
                            {t(PROVISIONING_STAGE_KEYS[selectedKnowledgeBase.provisioning_stage])}
                          </div>
                        )}
                        <small>
                          {selectedKnowledgeBase.external_status === "retrying"
                            ? t("knowledgeI18nRetryingTime")
                            : isSlowProvisioning(selectedKnowledgeBase)
                              ? t("knowledgeI18nSlowProvisioning")
                              : t("knowledgeI18nEstimatedTime")}
                        </small>
                        <small>{t("knowledgeI18nProvisioningProgress")}</small>
                      </>}
                    </div>
                  </section>
                )}
                {canWrite && (
                  <div className="knowledge-security-notice">
                    <Shield size={18} aria-hidden="true" />
                    <div>
                      <strong>{t("knowledgeSecurityTitle")}</strong>
                      <p>{t("knowledgeSecurityBody")}</p>
                      <details>
                        <summary>{t("knowledgeSecurityDetails")}</summary>
                        <ul>
                          <li>{t("knowledgeSecurityPracticeAccess")}</li>
                          <li>{t("knowledgeSecurityPracticeReview")}</li>
                          <li>{t("knowledgeSecurityPracticeRemove")}</li>
                        </ul>
                      </details>
                      <label
                        className="knowledge-security-acknowledgement"
                        htmlFor="knowledge-security-acknowledgement"
                      >
                        <input
                          id="knowledge-security-acknowledgement"
                          type="checkbox"
                          checked={securityAcknowledged}
                          onChange={(event) =>
                            setSecurityAcknowledged(event.target.checked)
                          }
                        />
                        <span>{t("knowledgeSecurityAcknowledgement")}</span>
                      </label>
                    </div>
                  </div>
                )}

                {canWrite && (
                  <div className="knowledge-upload-box">
                    <Upload
                      size={22}
                    />

                    <div>
                      <strong>
                        {t("knowledgeGoogleUploadTitle")}
                      </strong>

                      <span>
                        {t("knowledgeGoogleUploadFormats")}
                      </span>
                    </div>

                    <button
                      className="primary-button"
                      onClick={() => {
                        fileInputRef.current?.click();
                      }}
                      disabled={
                        uploading || selectedKnowledgeBase.external_status !== "ready"
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
                      {selectedKnowledgeBase.external_status !== "ready" && (
                        <small className="knowledge-source-disabled-reason">
                          {t("knowledgeSourcesPendingReason")}
                        </small>
                      )}
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
                  <section className="knowledge-google-workspace">
                    <div className="knowledge-google-workspace-status">
                      <FileSpreadsheet size={22} />
                      <div>
                        <strong>{t("knowledgeGoogleWorkspaceTitle")}</strong>
                        <span>{t("knowledgeGoogleWorkspaceDescription")}</span>
                        <span>
                          {googleStatus.email
                            ? `${t("knowledgeGoogleConnected")} ${googleStatus.email}`
                            : t("knowledgeGoogleConnectedGeneric")}
                        </span>
                      </div>
                      <button
                        className="knowledge-google-disconnect-button"
                        onClick={handleOpenDisconnectGoogle}
                        type="button"
                      >
                        <LogOut size={14} aria-hidden="true" />
                        {t("knowledgeGoogleDisconnect")}
                      </button>
                    </div>

                    <div className="knowledge-google-source-buttons">
                      <button
                        className="google-button"
                        onClick={() => {
                          selectInitialSource("sheets");
                          setAddSourceMode("sheets");
                          void handleOpenGoogleSheets();
                        }}
                        disabled={
                          selectedKnowledgeBase.external_status !== "ready" ||
                          googleSheetsLoading
                        }
                      >
                        {googleSheetsLoading ? (
                          <LoaderCircle className="spin" size={16} />
                        ) : (
                          <FileSpreadsheet size={16} />
                        )}
                        <span className="knowledge-source-option-copy"><strong>{t("knowledgeGoogleSelectSheet")}</strong><small>{t("knowledgeGoogleSheetsDescription")}</small>{selectedKnowledgeBase.external_status !== "ready" && <small className="knowledge-source-disabled-reason">{t("knowledgeSourcesPendingReason")}</small>}</span>
                      </button>

                      <button
                        className="google-button"
                        onClick={(event) => {
                          selectInitialSource("docs");
                          void handleOpenDriveFiles(
                            "docs",
                            event.currentTarget,
                          );
                        }}
                        disabled={
                          selectedKnowledgeBase.external_status !== "ready" ||
                          driveFilesLoading ||
                          driveScopeStatus?.has_drive_scope === false
                        }
                      >
                        {driveFilesLoading ? (
                          <LoaderCircle className="spin" size={16} />
                        ) : (
                          <FileText size={16} />
                        )}
                        <span className="knowledge-source-option-copy"><strong>{t("knowledgeGoogleDocs")}</strong><small>{t("knowledgeGoogleDocsDescription")}</small>{selectedKnowledgeBase.external_status !== "ready" ? <small className="knowledge-source-disabled-reason">{t("knowledgeSourcesPendingReason")}</small> : driveScopeStatus?.has_drive_scope === false && <small className="knowledge-source-disabled-reason">{t("knowledgeGooglePermissionsReason")}</small>}</span>
                      </button>

                      <button
                        className="google-button"
                        onClick={(event) => {
                          selectInitialSource("drive-file");
                          void handleOpenDriveFiles(
                            "drive-file",
                            event.currentTarget,
                          );
                        }}
                        disabled={
                          selectedKnowledgeBase.external_status !== "ready" ||
                          driveFilesLoading ||
                          driveScopeStatus?.has_drive_scope === false
                        }
                      >
                        {driveFilesLoading ? (
                          <LoaderCircle className="spin" size={16} />
                        ) : (
                          <File size={16} />
                        )}
                        <span className="knowledge-source-option-copy"><strong>{t("knowledgeGoogleDriveFile")}</strong><small>{t("knowledgeGoogleDriveFileDescription")}</small>{selectedKnowledgeBase.external_status !== "ready" ? <small className="knowledge-source-disabled-reason">{t("knowledgeSourcesPendingReason")}</small> : driveScopeStatus?.has_drive_scope === false && <small className="knowledge-source-disabled-reason">{t("knowledgeGooglePermissionsReason")}</small>}</span>
                      </button>

                      <button
                        className="google-button"
                        onClick={(event) => {
                          selectInitialSource("drive-folder");
                          void handleOpenDriveFolders(
                            event.currentTarget,
                          );
                        }}
                        disabled={
                          selectedKnowledgeBase.external_status !== "ready" ||
                          driveFoldersLoading ||
                          driveScopeStatus?.has_drive_scope === false
                        }
                      >
                        {driveFoldersLoading ? (
                          <LoaderCircle className="spin" size={16} />
                        ) : (
                          <Folder size={16} />
                        )}
                        <span className="knowledge-source-option-copy"><strong>{t("knowledgeGoogleDriveFolder")}</strong><small>{t("knowledgeGoogleDriveFolderDescription")}</small>{selectedKnowledgeBase.external_status !== "ready" ? <small className="knowledge-source-disabled-reason">{t("knowledgeSourcesPendingReason")}</small> : driveScopeStatus?.has_drive_scope === false && <small className="knowledge-source-disabled-reason">{t("knowledgeGooglePermissionsReason")}</small>}</span>
                      </button>
                      {driveScopeStatus &&
                        !driveScopeStatus.has_drive_scope && (
                          <div className="knowledge-drive-permissions">
                            <span>{t("knowledgeGoogleAdditionalPermissions")}</span>
                            <button
                              className="secondary-button"
                              onClick={() => void handleExpandScopes()}
                              disabled={googleConnecting}
                            >
                              {t("knowledgeGoogleExpandPermissions")}
                            </button>
                          </div>
                        )}
                    </div>
                  </section>
                )}


                <div className="knowledge-sources-heading">
                  <div>
                    <span className="eyebrow">{t("knowledgeSourcesEyebrow")}</span>
                    <h3>{t("knowledgeSourcesTitle")}</h3>
                  </div>
                </div>

                {sourcesLoading ? (
                  <div className="conversation-loading">
                    <LoaderCircle
                      className="spin"
                      size={24}
                    />
                  </div>
                ) : (
                    <div className="knowledge-source-list knowledge-document-source-list">
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


      {disconnectGoogleOpen && (
        <div
          className="management-modal-backdrop"
          onMouseDown={handleCloseDisconnectGoogle}
        >
          <div
            className="management-modal knowledge-google-disconnect-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="knowledge-google-disconnect-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header className="management-modal-header">
              <div>
                <span className="eyebrow">
                  {t("knowledgeGoogleWorkspaceTitle")}
                </span>
                <h2 id="knowledge-google-disconnect-title">
                  {t("knowledgeGoogleDisconnectTitle")}
                </h2>
              </div>
              <button
                className="icon-button"
                onClick={handleCloseDisconnectGoogle}
                disabled={disconnectingGoogle}
                type="button"
                aria-label={t("knowledgeGoogleClose")}
              >
                <X size={18} />
              </button>
            </header>
            <div className="management-form knowledge-google-disconnect-body">
              <p>{t("knowledgeGoogleDisconnectBody")}</p>
              <p>{t("knowledgeGoogleDisconnectSecondary")}</p>
              {disconnectGoogleError && (
                <p className="knowledge-google-disconnect-error" role="alert">
                  {disconnectGoogleError}
                </p>
              )}
            </div>
            <footer className="management-modal-actions">
              <button
                className="secondary-button"
                onClick={handleCloseDisconnectGoogle}
                disabled={disconnectingGoogle}
                type="button"
              >
                {t("knowledgeGoogleDisconnectCancel")}
              </button>
              <button
                className="knowledge-google-disconnect-confirm"
                onClick={() => void handleDisconnectGoogle()}
                disabled={disconnectingGoogle}
                type="button"
              >
                {disconnectingGoogle && (
                  <LoaderCircle className="spin" size={15} aria-hidden="true" />
                )}
                {t(
                  disconnectingGoogle
                    ? "knowledgeGoogleDisconnecting"
                    : "knowledgeGoogleDisconnect",
                )}
              </button>
            </footer>
          </div>
        </div>
      )}


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
                resetSecurityAcknowledgement();
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
                    resetSecurityAcknowledgement();
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
                resetSecurityAcknowledgement();
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
                      {googleSheetImportMode === "choose"
                        ? t("knowledgeGoogleImportChoice")
                        : t("knowledgeGoogleSelectTab")}
                    </h2>
                </div>

                <button
                  className="icon-button"
                  onClick={() => {
                    setGoogleTabsOpen(false);
                    setSelectedGoogleSheet(null);
                    resetSecurityAcknowledgement();
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
                    {googleSheetImportMode === "choose" && (
                      <>
                        <button
                          className="knowledge-source-row google-source-row"
                          onClick={() => {
                            if (!requiresSecurityAcknowledgement("sheets")) {
                              void handleAddGoogleWorkbookSource();
                            }
                          }}
                          disabled={googleAdding || !securityAcknowledged || selectedInitialSource !== "sheets"}
                        >
                          <div className="management-icon"><FileSpreadsheet size={18} /></div>
                          <div className="knowledge-source-info">
                            <strong>{t("knowledgeGoogleEntireWorkbook")}</strong>
                            <span>{t("knowledgeGoogleEntireWorkbookDescription", { count: googleTabs.filter((tab) => !tab.hidden).length })}</span>
                            <span className="knowledge-security-contextual-warning">
                              <Info size={14} aria-hidden="true" />
                              {t("knowledgeSecurityWorkbookWarning")}
                            </span>
                          </div>
                        </button>
                        <button
                          className="knowledge-source-row google-source-row"
                          onClick={() => setGoogleSheetImportMode("sheet")}
                          disabled={googleAdding || selectedInitialSource !== "sheets"}
                        >
                          <div className="management-icon"><FileText size={18} /></div>
                          <div className="knowledge-source-info">
                            <strong>{t("knowledgeGoogleSingleSheet")}</strong>
                            <span>{t("knowledgeGoogleSingleSheetDescription")}</span>
                          </div>
                        </button>
                      </>
                    )}

                    {googleSheetImportMode === "sheet" && googleTabs.filter((tab) => !tab.hidden).map((tab) => (
                      <div
                        key={tab.sheetId}
                        className="knowledge-source-row google-source-row"
                          onClick={() => {
                            if (!googleAdding && !requiresSecurityAcknowledgement("sheets")) {
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

                    {!googleTabs.filter((tab) => !tab.hidden).length && (
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
                            disabled={googleAdding || !securityAcknowledged || selectedInitialSource !== (isDoc ? "docs" : "drive-file")}
                            onClick={() => {
                              if (requiresSecurityAcknowledgement(isDoc ? "docs" : "drive-file")) {
                                return;
                              }
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

      {deletingKnowledgeBase && (
        <div className="management-modal-backdrop" onMouseDown={() => !deleting && setDeletingKnowledgeBase(null)}>
          <div className="management-modal" onMouseDown={(event) => event.stopPropagation()}>
            <header className="management-modal-header">
              <div><span className="eyebrow">{t("knowledgeI18nDeleteKnowledgeBase")}</span><h2>{t("knowledgeI18nDeleteKnowledgeBase")}</h2></div>
              <button className="icon-button" disabled={deleting} onClick={() => setDeletingKnowledgeBase(null)}><X size={18} /></button>
            </header>
            <div className="management-form">
              <p>{t("knowledgeI18nDeleteKnowledgeBaseBody")}</p>
              <p><strong>{deletingKnowledgeBase.name}</strong></p>
              <p>{t("knowledgeI18nDeleteKnowledgeBaseConfirm", { name: deletingKnowledgeBase.name })}</p>
              <input value={deleteConfirmation} onChange={(event) => setDeleteConfirmation(event.target.value)} disabled={deleting} />
            </div>
            <footer className="management-modal-footer">
              <button className="secondary-button" disabled={deleting} onClick={() => setDeletingKnowledgeBase(null)}>{t("knowledgeI18nCancel")}</button>
              <button className="danger-button" disabled={deleting || deleteConfirmation !== deletingKnowledgeBase.name} onClick={() => void handleDeleteKnowledgeBase()}>{deleting ? t("knowledgeI18nDeletingKnowledgeBase") : t("knowledgeI18nDeleteKnowledgeBase")}</button>
            </footer>
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
                      <span className="knowledge-security-contextual-warning">
                        <Info size={14} aria-hidden="true" />
                        {t("knowledgeSecurityFolderWarning")}
                      </span>
                      <button
                        className="google-button"
                        disabled={googleAdding || !securityAcknowledged || selectedInitialSource !== "drive-folder"}
                        onClick={() => {
                          if (!requiresSecurityAcknowledgement("drive-folder")) {
                            void handleAddDriveFolder(folder);
                          }
                        }}
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
