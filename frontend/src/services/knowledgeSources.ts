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
