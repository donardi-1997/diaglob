import { api } from "./api";


export interface KnowledgeSource {
  id: number;
  organization_id: number;
  knowledge_base_id: number;

  name: string;

  source_type: string;

  content_type:
    | string
    | null;

  size_bytes:
    | number
    | null;

  status: string;

  ingestion_job_id:
    | string
    | null;

  error_message:
    | string
    | null;

  active: boolean;

  created_at:
    | string
    | null;

  external_id?:
    | string
    | null;

  external_name?:
    | string
    | null;

  sheet_name?:
    | string
    | null;

  last_synced_at?:
    | string
    | null;

  sync_status?:
    | string
    | null;

  sync_error?:
    | string
    | null;

  external_mime_type?:
    | string
    | null;

  external_modified_at?:
    | string
    | null;

  parent_source_id?:
    | number
    | null;

  external_size?:
    | number
    | null;

  sync_generation?: number;

  freshness?: string;
}


export async function getKnowledgeSources(
  knowledgeBaseId: number,
) {
  const response =
    await api.get<{
      items: KnowledgeSource[];
      total: number;
    }>(
      `/api/knowledge-bases/${knowledgeBaseId}/sources`,
    );

  return response.data;
}


export async function uploadKnowledgeSource(
  knowledgeBaseId: number,
  file: File,
) {
  const data =
    new FormData();

  data.append(
    "file",
    file,
  );

  const response =
    await api.post<KnowledgeSource>(
      `/api/knowledge-bases/${knowledgeBaseId}/sources`,
      data,
    );

  return response.data;
}


export async function deleteKnowledgeSource(
  knowledgeBaseId: number,
  sourceId: number,
) {
  const response =
    await api.delete(
      `/api/knowledge-bases/${knowledgeBaseId}/sources/${sourceId}`,
    );

  return response.data;
}
