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
      sync_status: string;
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
      sync_status: string;
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
      sync_status: string;
      last_synced_at: string | null;
      sync_error: string | null;
    }>(
      `/api/knowledge-bases/${knowledgeBaseId}/sources/${sourceId}/ingestion-status`,
    );

  return response.data;
}
