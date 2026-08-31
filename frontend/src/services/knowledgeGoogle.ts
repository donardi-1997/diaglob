import { api } from "./api";


export interface GoogleStatus {
  connected: boolean;
  email: string | null;
  status: string | null;
  connected_at: string | null;
}


export interface GoogleSheetItem {
  spreadsheet_id: string;
  name: string;
  modified_time: string | null;
}


export interface GoogleTabItem {
  sheetId: number;
  title: string;
  index: number;
}


export type GoogleSyncStatus =
  | "syncing"
  | "indexing"
  | "partial_failed"
  | "uploaded"
  | "failed"
  | "disconnected"
  | "synced";


export type GoogleFreshnessStatus =
  | "syncing"
  | "failed"
  | "disconnected"
  | "fresh"
  | "changed"
  | "static";


export async function getGoogleStatus() {
  const response =
    await api.get<GoogleStatus>(
      "/api/integrations/google/status",
    );

  return response.data;
}


export async function startGoogleOAuth() {
  const response =
    await api.get<{
      authorization_url: string;
    }>(
      "/api/integrations/google/oauth/start",
    );

  return response.data;
}


export async function disconnectGoogle() {
  const response =
    await api.delete(
      "/api/integrations/google",
    );

  return response.data;
}


export async function listGoogleSheets() {
  const response =
    await api.get<{
      sheets: GoogleSheetItem[];
    }>(
      "/api/integrations/google/sheets",
    );

  return response.data;
}


export async function listGoogleSheetTabs(
  spreadsheetId: string,
) {
  const response =
    await api.get<{
      title: string;
      tabs: GoogleTabItem[];
    }>(
      `/api/integrations/google/sheets/${spreadsheetId}/tabs`,
    );

  return response.data;
}


export async function addGoogleSheetSource(
  knowledgeBaseId: number,
  spreadsheetId: string,
  spreadsheetName: string,
  sheetName: string,
) {
  const response =
    await api.post<{
      source_id: number;
      sync_status: GoogleSyncStatus;
      ingestion_job_id: string | null;
      name: string;
      message?: string;
    }>(
      `/api/knowledge-bases/${knowledgeBaseId}/sources/google-sheet`,
      {
        spreadsheet_id: spreadsheetId,
        spreadsheet_name: spreadsheetName,
        sheet_name: sheetName,
      },
    );

  return response.data;
}


export async function syncGoogleSheetSource(
  knowledgeBaseId: number,
  sourceId: number,
) {
  const response =
    await api.post<{
      source_id: number;
      sync_status: GoogleSyncStatus;
      ingestion_job_id: string | null;
      message?: string;
    }>(
      `/api/knowledge-bases/${knowledgeBaseId}/sources/${sourceId}/sync`,
    );

  return response.data;
}


export async function getIngestionStatus(
  knowledgeBaseId: number,
  sourceId: number,
) {
  const response =
    await api.get<{
      source_id: number;
      sync_status: GoogleSyncStatus;
      last_synced_at: string | null;
      sync_error: string | null;
    }>(
      `/api/knowledge-bases/${knowledgeBaseId}/sources/${sourceId}/ingestion-status`,
    );

  return response.data;
}


// ============================================================
// GOOGLE DRIVE / DOCS — PHASE 2
// ============================================================


export interface GoogleDriveScopeStatus {
  connected: boolean;
  has_drive_scope: boolean;
  scopes: string[];
}


export interface GoogleDriveFileItem {
  id: string;
  name: string;
  mime_type: string;
  modified_time: string | null;
  size: string | null;
  parents: string[];
}


export interface GoogleDriveFolderItem {
  id: string;
  name: string;
  modified_time: string | null;
}


export interface GoogleDriveFilesPage {
  files: GoogleDriveFileItem[];
  next_page_token: string | null;
}


export interface GoogleDriveFoldersPage {
  folders: GoogleDriveFolderItem[];
  next_page_token: string | null;
}


export interface GoogleSourceFreshness {
  source_id: number;
  freshness: GoogleFreshnessStatus;
  last_synced_at: string | null;
  external_modified_at: string | null;
  sync_status: GoogleSyncStatus;
  source_type: string;
}


export async function checkGoogleDriveScopes() {
  const response =
    await api.get<GoogleDriveScopeStatus>(
      "/api/integrations/google/drive/scopes",
    );

  return response.data;
}


export async function expandGoogleScopes() {
  const response =
    await api.get<{
      authorization_url: string;
    }>(
      "/api/integrations/google/oauth/expand-scopes",
    );

  return response.data;
}


export async function listGoogleDriveFiles(
  query: string = "",
  pageToken?: string,
  mimeType?: string,
) {
  const response =
    await api.get<GoogleDriveFilesPage>(
      "/api/integrations/google/drive/files",
      { params: { query, page_token: pageToken, mime_type: mimeType } },
    );

  return response.data;
}


export async function listGoogleDriveFolders(
  query: string = "",
  pageToken?: string,
) {
  const response =
    await api.get<GoogleDriveFoldersPage>(
      "/api/integrations/google/drive/folders",
      { params: { query, page_token: pageToken } },
    );

  return response.data;
}


export async function addGoogleDocSource(
  knowledgeBaseId: number,
  fileId: string,
  fileName: string,
) {
  const response =
    await api.post<{
      source_id: number;
      sync_status: GoogleSyncStatus;
      ingestion_job_id: string | null;
      name: string;
      message?: string;
    }>(
      `/api/knowledge-bases/${knowledgeBaseId}/sources/google-doc`,
      {
        file_id: fileId,
        file_name: fileName,
        mime_type:
          "application/vnd.google-apps.document",
      },
    );

  return response.data;
}


export async function addGoogleDriveFileSource(
  knowledgeBaseId: number,
  fileId: string,
  fileName: string,
  mimeType: string,
) {
  const response =
    await api.post<{
      source_id: number;
      sync_status: GoogleSyncStatus;
      ingestion_job_id: string | null;
      name: string;
      message?: string;
    }>(
      `/api/knowledge-bases/${knowledgeBaseId}/sources/google-drive-file`,
      {
        file_id: fileId,
        file_name: fileName,
        mime_type: mimeType,
      },
    );

  return response.data;
}


export async function addGoogleDriveFolderSource(
  knowledgeBaseId: number,
  folderId: string,
  folderName: string,
) {
  const response =
    await api.post<{
      source_id: number;
      sync_status: GoogleSyncStatus;
      ingestion_job_id: string | null;
      name: string;
      child_count: number;
      message?: string;
    }>(
      `/api/knowledge-bases/${knowledgeBaseId}/sources/google-drive-folder`,
      {
        folder_id: folderId,
        folder_name: folderName,
      },
    );

  return response.data;
}


export async function syncDriveFolder(
  knowledgeBaseId: number,
  sourceId: number,
) {
  const response =
    await api.post<{
      source_id: number;
      sync_status: GoogleSyncStatus;
      ingestion_job_id: string | null;
      new_files: number;
      modified_files: number;
      removed_files: number;
      message?: string;
    }>(
      `/api/knowledge-bases/${knowledgeBaseId}/sources/${sourceId}/sync-folder`,
    );

  return response.data;
}


export async function syncDriveFileSource(
  knowledgeBaseId: number,
  sourceId: number,
) {
  const response =
    await api.post<{
      source_id: number;
      sync_status: GoogleSyncStatus;
      ingestion_job_id: string | null;
      message?: string;
    }>(
      `/api/knowledge-bases/${knowledgeBaseId}/sources/${sourceId}/sync-drive-file`,
    );

  return response.data;
}


export async function getSourceFreshness(
  knowledgeBaseId: number,
  sourceId: number,
) {
  const response =
    await api.get<GoogleSourceFreshness>(
      `/api/knowledge-bases/${knowledgeBaseId}/sources/${sourceId}/freshness`,
    );

  return response.data;
}
