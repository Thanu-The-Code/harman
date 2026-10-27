import { api } from "./baseApi";
import type { Frequency, LayoutItem } from "./formats.api";

/* ------------------------------------------------------------------ types */

export type RecordStage =
  | "filling"
  | "po_approval"
  | "opo_approval"
  | "cft_review"
  | "final_decision"
  | "stored"
  | "cancelled";

export type Rag = "green" | "yellow" | "red";
export type ResponsibilityRole = "process_owner" | "overall_process_owner" | "cft_members" | "qms_coordinator";

export interface Person {
  id: string;
  name: string;
  email?: string | null;
  job_title?: string | null;
}

/** What the signed-in person may do with this record, decided by the server. */
export interface RecordCan {
  fill: boolean;
  submit: boolean;
  clear_nok: boolean;
  send_back: boolean;
  return_for_correction: boolean;
  amend: boolean;
  store: boolean;
  request_change: boolean;
}

export interface RecordAwaiting {
  step: string;
  stage: string | null;
  people: Person[];
  due: string | null;
  overdue: boolean;
}

export interface RecordValue {
  id: string;
  field_id: string | null;
  layout_key: string | null;
  order: number;
  label: string;
  field_type: "text" | "number" | "select" | "date" | "boolean";
  options: string[] | null;
  required: boolean;
  help_text: string | null;
  unit: string | null;
  spec_min: number | null;
  spec_max: number | null;
  spec_text: string | null;
  spec_label: string;
  value: string | null;
  numeric_value: number | null;
  in_spec: boolean | null;
  remark: string | null;
}

export interface RecordAttachment {
  id: string;
  filename: string;
  caption: string | null;
  mime_type: string;
  size: number;
  is_image: boolean;
  uploaded_by: Person | null;
  uploaded_at: string;
  href: string;
}

export interface RecordEvent {
  id: string;
  kind: string;
  summary: string;
  detail: string | null;
  actor: Person | null;
  at: string;
}

export interface RecordRouteStep {
  order: number;
  name: string;
  stage: string | null;
  addressed_to: ResponsibilityRole | "people" | string;
  mode: "any" | "all";
  requires_signature: boolean;
  days: number;
  people: Person[];
}

export interface RecordSummary {
  id: string;
  number: string;
  format: {
    id: string;
    code: string;
    title: string;
    frequency: Frequency;
    frequency_label: string;
    work_instruction_ref: string | null;
    work_instruction: string | null;
    layout: LayoutItem[];
  };
  format_revision: string;
  team: { id: string; code: string; name: string } | null;
  period_key: string;
  period_label: string;
  entry_mode: "digital" | "hardcopy";
  stage: RecordStage;
  stage_label: string;
  observation_status: "ok" | "not_ok" | null;
  rag: Rag;
  rag_label: string;
  cft_objection: string | null;
  nok_summary: string | null;
  nok_flagged_at: string | null;
  nok_flagged_to: Person | null;
  nok_cleared_at: string | null;
  nok_open: boolean;
  cft_target_date: string | null;
  reverify_count: number;
  filled_by: Person | null;
  filled_at: string | null;
  submitted_at: string | null;
  document_id: string | null;
  workflow_id: string | null;
  approval_overrides: Partial<Record<ResponsibilityRole, string[]>>;
  workflow_status: string | null;
  storage_path: string | null;
  stored_at: string | null;
  stored_by: Person | null;
  created_at: string;
  can: RecordCan;
  awaiting: RecordAwaiting | null;
  value_count: number;
}

export interface RecordDetail extends RecordSummary {
  values: RecordValue[];
  missing: string[];
  /** the latest return for correction, while the record is back with its owner */
  returned: { by: { name: string } | null; at: string; reason: string | null } | null;
  attachments: RecordAttachment[];
  events: RecordEvent[];
  responsibilities: {
    process_owner: Person | null;
    overall_process_owner: Person | null;
    cft_members: Person[];
    qms_coordinator: Person | null;
  };
  route: RecordRouteStep[];
  storage_preview: string;
}

/** One row of My Documents (`GET /api/records/documents-listing`). */
export interface DocumentListItem {
  id: string;
  number: string;
  document_name: string;
  department: { id: string; name: string } | null;
  type: string;
  frequency: Frequency;
  start_on: string | null;
  last_update: string | null;
  last_approval: { order: number; name: string; by: string } | null;
  stage: RecordStage;
  stage_label: string;
  rag: Rag;
  workflow_id: string | null;
  document_id: string | null;
  awaiting: RecordAwaiting | null;
  can: RecordCan;
}

export interface DocumentListing {
  tab: "verification" | "draft";
  items: DocumentListItem[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  counts: { verification: number; draft: number };
  departments: { id: string; name: string }[];
}

export interface ValueInput {
  id?: string;
  layout_key?: string | null;
  value: string;
  remark?: string;
}

/* -------------------------------------------------------------- endpoints */

const recordTags = (id: string) => [
  { type: "Record" as const, id },
  { type: "Record" as const, id: "LIST" },
  "Stats" as const,
];

export const recordsApi = api.injectEndpoints({
  endpoints: (build) => ({
    /** The Process Owner calls a released format: a record is raised for the current period. */
    callFormat: build.mutation<RecordDetail, { format_id: string; entry_mode?: "digital" | "hardcopy" }>({
      query: ({ entry_mode = "digital", ...rest }) => ({
        url: "api/records/call",
        method: "POST",
        data: { ...rest, entry_mode },
      }),
      invalidatesTags: [{ type: "Record", id: "LIST" }, { type: "Format", id: "LIST" }, "Stats"],
    }),
    getRecord: build.query<RecordDetail, string>({
      query: (id) => ({ url: `api/records/${id}` }),
      providesTags: (_r, _e, id) => [{ type: "Record", id }],
    }),
    documentsListing: build.query<
      DocumentListing,
      { tab: "verification" | "draft"; q?: string; team_id?: string; page?: number; page_size?: number }
    >({
      query: (params) => ({ url: "api/records/documents-listing", params }),
      providesTags: [{ type: "Record", id: "LIST" }],
    }),
    /** Readings are judged as they are saved; the answer goes straight into the cached record. */
    saveValues: build.mutation<RecordDetail, { id: string; values: ValueInput[] }>({
      query: ({ id, values }) => ({ url: `api/records/${id}/values`, method: "PUT", data: { values } }),
      async onQueryStarted({ id }, { dispatch, queryFulfilled }) {
        try {
          const { data } = await queryFulfilled;
          dispatch(recordsApi.util.upsertQueryData("getRecord", id, data));
        } catch {
          /* the caller shows the error */
        }
      },
      invalidatesTags: [{ type: "Record", id: "LIST" }],
    }),
    uploadAttachment: build.mutation<RecordAttachment, { id: string; file: File; caption?: string }>({
      query: ({ id, file, caption }) => {
        const data = new FormData();
        data.append("file", file);
        if (caption) data.append("caption", caption);
        return { url: `api/records/${id}/attachments`, method: "POST", data };
      },
      invalidatesTags: (_r, _e, { id }) => [{ type: "Record", id }],
    }),
    deleteAttachment: build.mutation<{ removed: boolean }, { id: string; attachmentId: string }>({
      query: ({ id, attachmentId }) => ({ url: `api/records/${id}/attachments/${attachmentId}`, method: "DELETE" }),
      invalidatesTags: (_r, _e, { id }) => [{ type: "Record", id }],
    }),
    /** Attach the scanned paper record. OCR is switched off on the server, so nothing is read from it. */
    uploadScan: build.mutation<{ record: RecordDetail; document_id: string }, { id: string; file: File }>({
      query: ({ id, file }) => {
        const data = new FormData();
        data.append("file", file);
        return { url: `api/records/${id}/scan`, method: "POST", data };
      },
      invalidatesTags: (_r, _e, { id }) => [{ type: "Record", id }],
    }),
    submitRecord: build.mutation<
      RecordDetail,
      { id: string; document_id?: string | null; approval_overrides?: Partial<Record<ResponsibilityRole, string[]>> }
    >({
      query: ({ id, ...data }) => ({ url: `api/records/${id}/submit`, method: "POST", data }),
      invalidatesTags: (_r, _e, { id }) => [...recordTags(id), "MyApprovals", "Notifications", "Workflow"],
    }),
    /** The Overall Process Owner has acted on the N-OK observations. */
    clearNok: build.mutation<RecordDetail, { id: string; note: string }>({
      query: ({ id, note }) => ({ url: `api/records/${id}/nok/clear`, method: "POST", data: { note } }),
      invalidatesTags: (_r, _e, { id }) => [...recordTags(id), "MyApprovals", "Notifications"],
    }),
    /** File the approved record in its date / month folder. */
    storeRecord: build.mutation<RecordDetail, string>({
      query: (id) => ({ url: `api/records/${id}/store`, method: "POST" }),
      invalidatesTags: (_r, _e, id) => [...recordTags(id), "MyApprovals", "Notifications", "Repository", "Workflow"],
    }),
  }),
});

export const {
  useCallFormatMutation,
  useGetRecordQuery,
  useDocumentsListingQuery,
  useSaveValuesMutation,
  useUploadAttachmentMutation,
  useDeleteAttachmentMutation,
  useUploadScanMutation,
  useSubmitRecordMutation,
  useClearNokMutation,
  useStoreRecordMutation,
} = recordsApi;
