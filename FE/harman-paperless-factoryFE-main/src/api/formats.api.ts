import { api } from "./baseApi";

/* ------------------------------------------------------------------ types */

export type Frequency =
  | "shift"
  | "daily"
  | "weekly"
  | "monthly"
  | "quarterly"
  | "half_yearly"
  | "yearly"
  | "per_event";

export const FREQUENCY_OPTIONS: { value: Frequency; label: string }[] = [
  { value: "shift", label: "Per shift" },
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
  { value: "monthly", label: "Monthly" },
  { value: "quarterly", label: "Quarterly" },
  { value: "half_yearly", label: "Half-yearly" },
  { value: "yearly", label: "Yearly" },
  { value: "per_event", label: "Per event" },
];

export type FormatStatus = "draft" | "in_review" | "active" | "superseded" | "withdrawn";
export type BuilderStatus = "draft" | "on_verification" | "change_request";

export interface PersonRef {
  id: string;
  name: string;
  email?: string | null;
  job_title?: string | null;
  department?: string | null;
}

export interface TeamRef {
  id: string;
  code: string;
  name: string;
}

export interface RouteStep {
  name: string;
  stage: string;
  addressed_to: string;
  people_ids: string[];
  mode: "any" | "all";
  requires_signature: boolean;
  days: number;
  order: number;
  reaches: string;
}

/** A react-form-builder2 item, kept as the builder saved it. */
export type LayoutItem = Record<string, unknown> & {
  id?: string;
  element?: string;
  key?: string;
  field_name?: string;
  label?: string;
};

export interface Format {
  id: string;
  code: string;
  title: string;
  description: string | null;
  team: TeamRef | null;
  frequency: Frequency;
  frequency_label: string;
  revision: string;
  revision_of: string | null;
  status: FormatStatus;
  approval_status: "pending" | "rejected" | null;
  effective_date: string | null;
  work_instruction_ref: string | null;
  work_instruction: string | null;
  storage_path: string | null;
  folder_path: string | null;
  storage_preview: string;
  cft_target_days: number;
  process_owner: PersonRef | null;
  overall_process_owner: PersonRef | null;
  qms_coordinator: PersonRef | null;
  cft_members: PersonRef[];
  approval_route: RouteStep[];
  route_is_default: boolean;
  layout: LayoutItem[];
  has_blank: boolean;
  blank_mime: string | null;
  field_count: number;
  created_at: string;
  updated_at?: string | null;
  readiness: string[];
  builder_status?: BuilderStatus;
}

export interface FormatField {
  id: string;
  order: number;
  layout_key: string | null;
  label: string;
  field_type: "text" | "number" | "select" | "date" | "boolean";
  unit: string | null;
  spec_min: number | null;
  spec_max: number | null;
  spec_text: string | null;
  options: string[] | null;
  required: boolean;
  help_text: string | null;
  spec_label: string;
}

export interface ReviewDecision {
  user_id: string;
  decision: "approve" | "reject";
  comment?: string | null;
  at?: string;
  reviewer: string;
}

export interface FormatReviewStep {
  name: string;
  mode: "any" | "all";
  reviewer_ids: string[];
  role_id: string | null;
  role_name: string | null;
  due_days: number | null;
  reviewers: string[];
  decisions: ReviewDecision[];
}

export interface FormatReview {
  id?: string;
  format_id?: string;
  status: "pending" | "approved" | "rejected" | "none";
  current_step?: number;
  submitted_by?: { id: string; name: string } | null;
  submitted_at?: string;
  completed_at?: string | null;
  priority?: "low" | "normal" | "high" | "urgent";
  can_act: boolean;
  decision_comments?: { step: string; decision: string; comment?: string; reviewer: string; at?: string }[];
  steps: FormatReviewStep[];
}

export interface FormatDetail extends Format {
  fields: FormatField[];
  record_count: number;
  approval: FormatReview;
  previous_revisions: { id: string; revision: string; status: FormatStatus; effective_date: string | null }[];
  versions?: (FormatDetail & { approval: FormatReview })[];
}

export interface BuilderListResponse {
  formats: Format[];
  frequencies: { value: Frequency; label: string }[];
  summary?: {
    total_document: number;
    on_verification: number;
    change_request: number;
    draft: number;
    published: number;
  };
  total?: number;
}

export interface FormatStats {
  total: number;
  published: number;
  in_approval: number;
  on_verification: number;
  change_request: number;
  draft: number;
}

export interface QualityTeam {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  is_active: boolean;
  format_count: number;
  people: { id: string; name: string; username: string; email: string; job_title: string | null; department: string | null; can_approve: boolean; can_sign: boolean; is_admin: boolean }[];
}

export interface ResponsibilityPeople {
  process_owner: PersonRef[];
  overall_process_owner: PersonRef[];
  cft_members: PersonRef[];
  qms_coordinator: PersonRef[];
}

export interface TemplateFolder {
  id: string | null;
  name: string;
  path: string;
  parent_path: string | null;
  children: TemplateFolder[];
  templates?: { id: string; code: string; title: string; revision: string; status: FormatStatus }[];
}

export interface RepositoryVersion {
  id: string;
  revision: string;
  revision_of: string | null;
  title: string;
  status: FormatStatus;
  effective_date: string | null;
  created_at: string;
  approval_status: string | null;
}

export interface RepositoryTemplate {
  id: string;
  code: string;
  title: string;
  team: TeamRef | null;
  frequency: Frequency;
  frequency_label: string;
  latest_version: RepositoryVersion;
  released_version: RepositoryVersion | null;
  version_count: number;
  versions: RepositoryVersion[];
}

export interface CallableFormat extends FormatDetail {
  period: { key: string; label: string };
  existing_for_period: { id: string; number: string; stage: string } | null;
}

/** What the designer saves (POST creates, PUT updates). */
export interface FormatPayload {
  code: string;
  title: string;
  description?: string | null;
  frequency: Frequency;
  team_id?: string | null;
  layout?: LayoutItem[];
  fields?: unknown[];
  work_instruction_ref?: string | null;
  work_instruction?: string | null;
  storage_path?: string | null;
  cft_target_days?: number;
  process_owner_id?: string | null;
  overall_process_owner_id?: string | null;
  qms_coordinator_id?: string | null;
  cft_member_ids?: string[];
}

export interface ReviewStepPayload {
  name: string;
  reviewer_ids: string[];
  mode: "any" | "all";
  due_days?: number | null;
}

/* -------------------------------------------------------------- endpoints */

const formatTags = (id: string) => [{ type: "Format" as const, id }, { type: "Format" as const, id: "LIST" }, "Stats" as const];

export const formatsApi = api.injectEndpoints({
  endpoints: (build) => ({
    /** Admin builder tabs (unreleased templates) or, without a tab, the library. */
    listFormats: build.query<
      BuilderListResponse,
      { tab?: "all" | BuilderStatus; status?: FormatStatus; q?: string; team_id?: string; mine?: boolean } | void
    >({
      query: (params) => ({ url: "api/formats/", params: params ?? undefined }),
      providesTags: [{ type: "Format", id: "LIST" }],
    }),
    formatStats: build.query<FormatStats, void>({
      query: () => ({ url: "api/formats/stats" }),
      providesTags: ["Stats"],
    }),
    getFormat: build.query<FormatDetail, string>({
      query: (id) => ({ url: `api/formats/${id}` }),
      providesTags: (_r, _e, id) => [{ type: "Format", id }],
    }),
    callableFormats: build.query<{ formats: CallableFormat[] }, void>({
      query: () => ({ url: "api/formats/callable" }),
      providesTags: [{ type: "Format", id: "LIST" }],
    }),
    createFormat: build.mutation<FormatDetail, FormatPayload>({
      query: (data) => ({ url: "api/formats/", method: "POST", data }),
      invalidatesTags: [{ type: "Format", id: "LIST" }, "Stats"],
    }),
    updateFormat: build.mutation<FormatDetail, { id: string } & Partial<FormatPayload>>({
      query: ({ id, ...data }) => ({ url: `api/formats/${id}`, method: "PUT", data }),
      invalidatesTags: (_r, _e, { id }) => formatTags(id),
    }),
    submitFormatApproval: build.mutation<
      FormatReview,
      { id: string; steps: ReviewStepPayload[]; priority: "low" | "normal" | "high" | "urgent" }
    >({
      query: ({ id, ...data }) => ({ url: `api/formats/${id}/submit-approval`, method: "POST", data }),
      invalidatesTags: (_r, _e, { id }) => formatTags(id),
    }),
    publishWithoutApproval: build.mutation<FormatDetail, string>({
      query: (id) => ({ url: `api/formats/${id}/publish-without-approval`, method: "POST" }),
      invalidatesTags: (_r, _e, id) => formatTags(id),
    }),
    decideFormatApproval: build.mutation<
      { review: FormatReview; format: FormatDetail },
      { id: string; decision: "approve" | "reject"; comment?: string }
    >({
      query: ({ id, ...data }) => ({ url: `api/formats/${id}/approval/decision`, method: "POST", data }),
      invalidatesTags: (_r, _e, { id }) => [...formatTags(id), "MyApprovals", "Notifications"],
    }),
    withdrawFormat: build.mutation<FormatDetail, string>({
      query: (id) => ({ url: `api/formats/${id}/withdraw`, method: "POST" }),
      invalidatesTags: (_r, _e, id) => formatTags(id),
    }),
    uploadBlank: build.mutation<FormatDetail, { id: string; file: File }>({
      query: ({ id, file }) => {
        const data = new FormData();
        data.append("file", file);
        return { url: `api/formats/${id}/blank`, method: "POST", data };
      },
      invalidatesTags: (_r, _e, { id }) => formatTags(id),
    }),
    formatApprovalHistory: build.query<
      { format_id: string; total: number; latest_status: string; reviews: FormatReview[] },
      string
    >({
      query: (id) => ({ url: `api/formats/${id}/approval/history` }),
      providesTags: (_r, _e, id) => [{ type: "Format", id }],
    }),
    myFormatApprovals: build.query<
      { count: number; approvals: { format_id: string; code: string; title: string; review: FormatReview }[] },
      void
    >({
      query: () => ({ url: "api/formats/approvals/mine" }),
      providesTags: ["MyApprovals", { type: "Format", id: "LIST" }],
    }),
    formatTeams: build.query<{ teams: QualityTeam[]; unassigned: unknown[] }, void>({
      query: () => ({ url: "api/formats/teams" }),
      providesTags: ["Teams"],
    }),
    responsibilityPeople: build.query<ResponsibilityPeople, void>({
      query: () => ({ url: "api/formats/people" }),
      providesTags: ["Users"],
    }),
    /** Who may take each responsibility on this format (the record's approver pickers). */
    formatPeople: build.query<ResponsibilityPeople, string>({
      query: (id) => ({ url: `api/formats/${id}/people` }),
      providesTags: ["Users"],
    }),
    formatApprovers: build.query<PersonRef[], string | void>({
      query: (roleId) => ({ url: "api/formats/approvers", params: { role_id: roleId || undefined } }),
      providesTags: ["Users"],
    }),
    /** The code a new template of this team gets when its code is left blank. */
    nextFormatCode: build.query<{ code: string }, string>({
      query: (team_id) => ({ url: "api/formats/next-code", params: { team_id } }),
      providesTags: [{ type: "Format", id: "LIST" }],
    }),
    templateFolders: build.query<{ folders: TemplateFolder[] }, void>({
      query: () => ({ url: "api/formats/folders" }),
      providesTags: [{ type: "Format", id: "FOLDERS" }],
    }),
    createTemplateFolder: build.mutation<
      { id: string; name: string; path: string; parent_path: string | null },
      { name: string; parent_path?: string | null }
    >({
      query: (data) => ({ url: "api/formats/folders", method: "POST", data }),
      invalidatesTags: [{ type: "Format", id: "FOLDERS" }, { type: "Format", id: "REPO" }],
    }),
    formatRepository: build.query<{ templates: RepositoryTemplate[]; total: number; folders: TemplateFolder[] }, void>({
      query: () => ({ url: "api/formats/repository" }),
      providesTags: [{ type: "Format", id: "REPO" }, { type: "Format", id: "LIST" }],
    }),
  }),
});

export const {
  useListFormatsQuery,
  useFormatStatsQuery,
  useGetFormatQuery,
  useCallableFormatsQuery,
  useCreateFormatMutation,
  useUpdateFormatMutation,
  useSubmitFormatApprovalMutation,
  usePublishWithoutApprovalMutation,
  useDecideFormatApprovalMutation,
  useWithdrawFormatMutation,
  useUploadBlankMutation,
  useFormatApprovalHistoryQuery,
  useMyFormatApprovalsQuery,
  useFormatTeamsQuery,
  useNextFormatCodeQuery,
  useResponsibilityPeopleQuery,
  useFormatPeopleQuery,
  useFormatApproversQuery,
  useTemplateFoldersQuery,
  useCreateTemplateFolderMutation,
  useFormatRepositoryQuery,
} = formatsApi;

/** "In review", "Draft", … for a status chip. */
export const formatStatusLabel = (status: FormatStatus, approval?: string | null) => {
  if (status === "draft" && approval === "rejected") return "Changes requested";
  return (
    { draft: "Draft", in_review: "In review", active: "Released", superseded: "Superseded", withdrawn: "Withdrawn" }[status] ??
    status
  );
};
