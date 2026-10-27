import { api } from "./baseApi";
import type { Person } from "./records.api";

/* Filed quality records, in their date- and month-wise folders (`/api/documents/repository`). */

export interface RepositoryFolder {
  name: string;
  path: string; // "Records / Process Quality / QF-PQ-001 / 2026 / 10-Oct / 23"
  records_count: number;
  total_records: number;
  is_pinned: boolean;
  children: RepositoryFolder[];
}

export interface RepositoryDocument {
  id: string;
  record_id: string;
  document_id: string | null;
  document_name: string;
  form_name: string;
  form_code: string;
  document_number: string;
  department: string | null;
  type: string;
  filed_by: { id: string; name: string } | null;
  filed_by_name: string | null;
  filed_date: string | null;
  folder_path: string | null;
  period: string | null;
}

export interface RepositoryPage {
  folders: RepositoryFolder[];
  documents: RepositoryDocument[];
  pagination: { page: number; page_size: number; total: number; total_pages: number };
}

// a type alias (not an interface) so it is assignable to the query's params record
export type RepositoryParams = {
  search?: string;
  folder_path?: string;
  filed_date?: string;
  team_id?: string;
  page?: number;
  page_size?: number;
};

export interface RecordFileSummary {
  record_id: string;
  record_number: string;
  document: {
    id: string;
    title: string;
    filename: string;
    file_size: number;
    mime_type: string;
    version: string;
    created_at: string;
    file_url: string;
    download_url: string;
  } | null;
  summary: {
    name: string;
    code: string;
    revision?: string | null;
    document_type: string;
    department: string;
    filled_by: Person | null;
    filled_on: string | null;
    filed_by: Person | null;
    filed_on: string | null;
    total_items: number;
    completed_items: number;
    completion_percent: number;
    fields: { id: string; label: string; value: string | null; unit: string | null; specification: string | null; in_spec: boolean | null }[];
  };
}

export interface TimelineStepItem {
  id: string;
  order: number;
  name: string;
  status: string;
  stage: string | null;
  assigned_to: Person[];
  due_at: string | null;
  decided_at: string | null;
  decided_by: Person | null;
  comment: string | null;
  reason: string | null;
  signature: { name: string; designation: string | null; signed_at?: string } | null;
}

export interface RecordTimeline {
  record_id: string;
  workflow: { id: string; status: string; priority: string; submitted_by: Person | null; submitted_on: string | null; completed_on: string | null } | null;
  steps: TimelineStepItem[];
  events: { id: string; kind: string; summary: string; detail: string | null; by: Person | null; at: string }[];
}

export const repositoryApi = api.injectEndpoints({
  endpoints: (build) => ({
    repository: build.query<RepositoryPage, RepositoryParams>({
      query: (params) => ({ url: "api/documents/repository", params }),
      providesTags: ["Repository"],
    }),
    repositorySummary: build.query<RecordFileSummary, string>({
      query: (recordId) => ({ url: `api/documents/repository/${recordId}/summary` }),
      providesTags: ["Repository"],
    }),
    repositoryTimeline: build.query<RecordTimeline, string>({
      query: (recordId) => ({ url: `api/documents/repository/${recordId}/approval-timeline` }),
      providesTags: ["Repository"],
    }),
    renameRepositoryFolder: build.mutation<{ old_path: string; new_path: string }, { folder_path: string; new_name: string }>({
      query: (data) => ({ url: "api/documents/repository/folders/rename", method: "PATCH", data }),
      invalidatesTags: ["Repository"],
    }),
    pinRepositoryFolder: build.mutation<{ folder_path: string; is_pinned: boolean }, { folder_path: string; pinned: boolean }>({
      query: (data) => ({ url: "api/documents/repository/folders/pin", method: "PUT", data }),
      invalidatesTags: ["Repository"],
    }),
  }),
});

export const {
  useRepositoryQuery,
  useRepositorySummaryQuery,
  useRepositoryTimelineQuery,
  useRenameRepositoryFolderMutation,
  usePinRepositoryFolderMutation,
} = repositoryApi;

/** Tree ids cannot hold "/" (the folder tree joins ids with it): paths travel as "A>B>C". */
export const pathToId = (path: string) => path.split(" / ").join(">");
export const idToPath = (id: string) => id.split(">").join(" / ");
