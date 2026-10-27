import { api } from "./baseApi";

/* The approval chain a record runs through (`/api/workflow`). */

export interface WorkflowPerson {
  id: string;
  name: string;
  username: string;
  department: string | null;
  job_title: string | null;
  can_sign: boolean;
  is_admin: boolean;
}

export interface WorkflowSignature {
  id: string;
  dataUrl: string | null; // only for its signer and administrators
  name: string;
  designation: string | null;
  method: string;
  signedAt: string;
  placed: boolean;
}

export type StepStatus = "pending" | "current" | "approved" | "rejected" | "changes_requested" | "skipped";

export interface WorkflowStep {
  id: string;
  order: number;
  name: string;
  department: string | null;
  role: string | null;
  assignees: WorkflowPerson[];
  requires_signature: boolean;
  approval_mode: "any" | "all";
  qms_stage: "po_approval" | "opo_approval" | "cft_review" | "final_decision" | null;
  approved_by: WorkflowPerson[];
  outstanding: WorkflowPerson[];
  sla_hours: number;
  due_date: string | null;
  overdue: boolean;
  status: StepStatus;
  decided_at: string | null;
  decided_by: WorkflowPerson | null;
  comment: string | null;
  reason: string | null;
  signature: WorkflowSignature | null;
  can_act: boolean;
  blocked_reason: string | null;
}

export interface WorkflowEvent {
  id: string;
  kind: string;
  summary: string;
  detail: string | null;
  actor: WorkflowPerson | null;
  at: string;
}

export interface Workflow {
  id: string;
  document_id: string;
  name: string;
  template_id: string | null;
  status: "draft" | "active" | "approved" | "rejected" | "changes_requested" | "cancelled" | "published";
  priority: "low" | "normal" | "high" | "urgent";
  department: string | null;
  created_by: WorkflowPerson | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  due_date: string | null;
  notes: string | null;
  current_step: WorkflowStep | null;
  steps: WorkflowStep[];
  events: WorkflowEvent[];
}

export interface SignaturePayload {
  dataUrl: string; // data:image/png;base64,… (≤ 2 MB)
  name?: string;
  designation?: string;
  method?: "draw" | "type";
}

/**
 * One decision on one step. On a record's QMS steps the server maps a negative
 * answer onto the process: return for correction (PO / OPO), an objection
 * (CFT), or back to the CFT for re-verification (final decision).
 */
export interface DecidePayload {
  workflowId: string;
  stepId: string;
  action: "approve" | "reject" | "changes";
  comment?: string;
  reason?: string;
  signature?: SignaturePayload;
  /** The record behind the workflow, so its screens refresh too. */
  recordId?: string;
}

export const workflowApi = api.injectEndpoints({
  endpoints: (build) => ({
    getWorkflow: build.query<Workflow, string>({
      query: (id) => ({ url: `api/workflow/${id}` }),
      providesTags: (_r, _e, id) => [{ type: "Workflow", id }, "Workflow"],
    }),
    decideStep: build.mutation<Workflow, DecidePayload>({
      query: ({ workflowId, stepId, action, comment = "", reason = "", signature }) => ({
        url: `api/workflow/${workflowId}/steps/${stepId}/decide`,
        method: "POST",
        data: { action, comment, reason, ...(signature ? { signature } : {}) },
      }),
      invalidatesTags: (_r, _e, { workflowId, recordId }) => [
        { type: "Workflow", id: workflowId },
        ...(recordId ? [{ type: "Record" as const, id: recordId }] : []),
        { type: "Record", id: "LIST" },
        "MyApprovals",
        "Notifications",
        "Stats",
        "Repository",
      ],
    }),
  }),
});

export const { useGetWorkflowQuery, useDecideStepMutation } = workflowApi;
