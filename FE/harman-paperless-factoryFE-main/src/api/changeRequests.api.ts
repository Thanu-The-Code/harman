import { api } from "./baseApi";
import type { Frequency } from "./formats.api";
import type { Person } from "./records.api";

/* ---------------------------------------------------------------- DCR
 * Document (format) Change Requests: the record process's "any change in an
 * existing format / generation of a new format", approved by the QMS
 * Coordinator before execution (`/api/change-requests`).
 */

export type DcrKind = "change_existing" | "new_format";
export type DcrStatus = "submitted" | "under_review" | "approved" | "rejected" | "implemented";

export interface Dcr {
  id: string;
  number: string;
  kind: DcrKind;
  kind_label: string;
  format: { id: string; code: string; title: string; revision: string; status: string } | null;
  team: { id: string; code: string; name: string } | null;
  title: string;
  reason: string;
  current_state: string | null;
  proposed_change: string;
  justification: string | null;
  raised_by: Person | null;
  raised_at: string;
  coordinator: Person | null;
  status: DcrStatus;
  status_label: string;
  decided_at: string | null;
  decided_by: Person | null;
  decision_comment: string | null;
  resulting_format: { id: string; code: string; title?: string; revision: string; status: string } | null;
  can: { decide: boolean; execute: boolean };
}

export interface DcrList {
  requests: Dcr[];
  stats: Record<"total" | DcrStatus, number>;
  waiting_on_me: number;
}

export interface RaiseDcrPayload {
  kind: DcrKind;
  format_id?: string;
  team_id?: string;
  qms_coordinator_id?: string;
  title: string;
  reason: string;
  current_state?: string;
  proposed_change: string;
  justification?: string;
}

export interface ExecuteDcrPayload {
  code?: string;
  title?: string;
  frequency?: Frequency;
  team_id?: string;
}

/* ---------------------------------------------------------------- RCR
 * Record Change Requests: a change asked for on a filled record
 * (`/api/record-change-requests`).
 */

export type RcrStatus = "open" | "approved" | "not_approved" | "implemented";

export interface Rcr {
  id: string;
  number: string;
  title: string;
  reason: string;
  status: RcrStatus;
  status_label: string;
  raised_by: Person | null;
  raised_at: string;
  assigned_to: Person | null;
  assigned_at: string | null;
  decided_by: Person | null;
  decided_at: string | null;
  decision_comment: string | null;
  implemented_by: Person | null;
  implemented_at: string | null;
  implementation_note: string | null;
  record: {
    id: string;
    number: string;
    document_name: string;
    document_type: string | null;
    format: { id: string; code: string; title: string; revision: string } | null;
    department: string | null;
    filled_by: Person | null;
    filled_at: string | null;
    submitted_at: string | null;
    total_items: number;
    completed_items: number;
    completion_percent: number;
    fields: { id?: string; label: string; value: string | null; unit?: string | null; in_spec?: boolean | null }[];
    document: { id: string; title: string; mime_type: string; file_url: string } | null;
  } | null;
  can: { edit: boolean; assign: boolean; decide: boolean; implement: boolean };
}

export interface RcrList {
  requests: Rcr[];
  stats: Record<RcrStatus, number>;
  total: number;
  page: number;
  page_size: number;
  pages: number;
  waiting_on_me: number;
}

const DCR = { type: "DCR" as const, id: "LIST" };
const RCR = { type: "RCR" as const, id: "LIST" };

export const changeRequestsApi = api.injectEndpoints({
  endpoints: (build) => ({
    /* DCR */
    listDcr: build.query<DcrList, { status?: DcrStatus; team_id?: string; mine?: boolean; waiting?: boolean }>({
      query: (params) => ({ url: "api/change-requests", params }),
      providesTags: [DCR],
    }),
    getDcr: build.query<Dcr, string>({
      query: (id) => ({ url: `api/change-requests/${id}` }),
      providesTags: (_r, _e, id) => [{ type: "DCR", id }],
    }),
    raiseDcr: build.mutation<Dcr, RaiseDcrPayload>({
      query: (data) => ({ url: "api/change-requests", method: "POST", data }),
      invalidatesTags: [DCR, "Notifications", "Stats"],
    }),
    reviewDcr: build.mutation<Dcr, string>({
      query: (id) => ({ url: `api/change-requests/${id}/review`, method: "POST" }),
      invalidatesTags: (_r, _e, id) => [{ type: "DCR", id }, DCR],
    }),
    decideDcr: build.mutation<Dcr, { id: string; action: "approve" | "reject"; comment: string }>({
      query: ({ id, ...data }) => ({ url: `api/change-requests/${id}/decide`, method: "POST", data }),
      invalidatesTags: (_r, _e, { id }) => [{ type: "DCR", id }, DCR, "Notifications", "Stats"],
    }),
    executeDcr: build.mutation<{ request: Dcr; format: { id: string; code: string; title: string; revision: string; status: string } }, { id: string } & ExecuteDcrPayload>({
      query: ({ id, ...data }) => ({ url: `api/change-requests/${id}/execute`, method: "POST", data }),
      invalidatesTags: (_r, _e, { id }) => [{ type: "DCR", id }, DCR, { type: "Format", id: "LIST" }, "Notifications", "Stats"],
    }),

    /* RCR */
    listRcr: build.query<
      RcrList,
      { status?: RcrStatus; department?: string; search?: string; mine?: boolean; waiting?: boolean; page?: number; page_size?: number }
    >({
      query: (params) => ({ url: "api/record-change-requests", params }),
      providesTags: [RCR],
    }),
    getRcr: build.query<Rcr, string>({
      query: (id) => ({ url: `api/record-change-requests/${id}` }),
      providesTags: (_r, _e, id) => [{ type: "RCR", id }],
    }),
    raiseRcr: build.mutation<Rcr, { record_id: string; title?: string; reason: string; assigned_to_id?: string }>({
      query: (data) => ({ url: "api/record-change-requests", method: "POST", data }),
      invalidatesTags: [RCR, "Notifications", "Stats"],
    }),
    updateRcr: build.mutation<Rcr, { id: string; title?: string; reason?: string }>({
      query: ({ id, ...data }) => ({ url: `api/record-change-requests/${id}`, method: "PATCH", data }),
      invalidatesTags: (_r, _e, { id }) => [{ type: "RCR", id }, RCR],
    }),
    assignRcr: build.mutation<Rcr, { id: string; assigned_to_id: string }>({
      query: ({ id, ...data }) => ({ url: `api/record-change-requests/${id}/assign`, method: "POST", data }),
      invalidatesTags: (_r, _e, { id }) => [{ type: "RCR", id }, RCR, "Notifications"],
    }),
    decideRcr: build.mutation<Rcr, { id: string; action: "approve" | "not_approved"; comment: string }>({
      query: ({ id, ...data }) => ({ url: `api/record-change-requests/${id}/decide`, method: "POST", data }),
      invalidatesTags: (_r, _e, { id }) => [{ type: "RCR", id }, RCR, "Notifications", "Stats"],
    }),
    implementRcr: build.mutation<Rcr, { id: string; note: string }>({
      query: ({ id, ...data }) => ({ url: `api/record-change-requests/${id}/implement`, method: "POST", data }),
      invalidatesTags: (_r, _e, { id }) => [{ type: "RCR", id }, RCR, "Notifications", "Stats"],
    }),
  }),
});

export const {
  useListDcrQuery,
  useGetDcrQuery,
  useRaiseDcrMutation,
  useReviewDcrMutation,
  useDecideDcrMutation,
  useExecuteDcrMutation,
  useListRcrQuery,
  useGetRcrQuery,
  useRaiseRcrMutation,
  useUpdateRcrMutation,
  useAssignRcrMutation,
  useDecideRcrMutation,
  useImplementRcrMutation,
} = changeRequestsApi;
