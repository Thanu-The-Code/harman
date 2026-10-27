import { api } from "./baseApi";
import type { RecordStage } from "./records.api";

/* The signed-in person's approval queue for records (`/api/my-approvals`). */

export type MyApprovalsTab = "overdue" | "pending" | "returned";

export interface MyApprovalItem {
  record_id: string;
  step_id: string | null;
  document_name: string;
  department: string | null;
  assigned_by: string | null;
  submitted_on: string | null;
  due_at: string | null;
  stage: RecordStage;
}

export interface MyApprovalsPage {
  tab: MyApprovalsTab;
  items: MyApprovalItem[];
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
  counts: Record<MyApprovalsTab, number>;
}

export interface TaskStats {
  pending: number;
  approved_today: number;
  returned: number;
  overdue: number;
}

export const approvalsApi = api.injectEndpoints({
  endpoints: (build) => ({
    myApprovals: build.query<
      MyApprovalsPage,
      { tab: MyApprovalsTab; search?: string; department?: string; page?: number; per_page?: number }
    >({
      query: (params) => ({ url: "api/my-approvals", params }),
      providesTags: ["MyApprovals"],
    }),
    myApprovalDepartments: build.query<string[], void>({
      query: () => ({ url: "api/my-approvals/departments" }),
      providesTags: ["MyApprovals"],
    }),
    taskStats: build.query<TaskStats, void>({
      query: () => ({ url: "api/workflow/tasks/stats" }),
      providesTags: ["MyApprovals", "Stats"],
    }),
  }),
});

export const { useMyApprovalsQuery, useMyApprovalDepartmentsQuery, useTaskStatsQuery } = approvalsApi;

/** "PO approval" etc. for a record stage in a list. */
export const STAGE_STEP: Record<string, string> = {
  filling: "Returned for correction",
  po_approval: "Process Owner approval",
  opo_approval: "Overall Process Owner approval",
  cft_review: "CFT joint review",
  final_decision: "Final decision",
  stored: "Filed",
};
