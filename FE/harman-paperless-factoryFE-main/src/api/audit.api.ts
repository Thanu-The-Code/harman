import { api } from "./baseApi";

/* The audit trail (`/api/audit`). */

export interface AuditEvent {
  id: string;
  action: string;
  label: string;
  icon: string;
  tone: string;
  module: string;
  user: string | null;
  resource_type: string | null;
  resource_id: string | null;
  summary: string;
  ip_address: string | null;
  at: string;
}

export type AuditParams = {
  q?: string;
  module?: string;
  date_from?: string;
  date_to?: string;
  days?: number;
  page?: number;
  page_size?: number;
  /** leave out sign-ins: what people did, not when they logged in */
  work_only?: boolean;
};

export interface AuditPage {
  events: AuditEvent[];
  count: number;
  days: number;
  pagination: { page: number; page_size: number; total: number; total_pages: number };
}

export const auditApi = api.injectEndpoints({
  endpoints: (build) => ({
    audit: build.query<AuditPage, AuditParams>({
      query: (params) => ({ url: "api/audit", params }),
      providesTags: ["Audit"],
    }),
    auditModules: build.query<{ modules: string[] }, void>({
      query: () => ({ url: "api/audit/modules" }),
    }),
  }),
});

export const { useAuditQuery, useAuditModulesQuery } = auditApi;
