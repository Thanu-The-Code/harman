import { api } from "./baseApi";

/* The inspection dashboard (`/api/actions/dashboard`). */

export interface TrendBucket {
  from: string;
  to: string;
  label: string;
  total: number;
  passed: number;
  failed: number;
  open: number;
  completed: number;
}

export interface Dashboard {
  window: { days: number; from: string; to: string };
  totals: {
    total: number;
    completed: number;
    pending: number;
    failed: number;
    /** of the records with readings to judge; null when there are none */
    pass_rate: number | null;
    growth: { total: number; completed: number; pending: number; failed: number };
  };
  by_department: { id: string; name: string; code: string; total: number; completed: number; pending: number; failed: number }[];
  recent: { id: string; number: string; department: string; type: string; date: string; inspector: string; status: string }[];
  trend: TrendBucket[];
  missed: { format: { id: string; code: string; title: string }; period: string; frequency_label: string }[];
}

export const dashboardApi = api.injectEndpoints({
  endpoints: (build) => ({
    dashboard: build.query<Dashboard, { days: number }>({
      query: (params) => ({ url: "api/actions/dashboard", params }),
      providesTags: ["Stats", "Record"],
    }),
  }),
});

export const { useDashboardQuery } = dashboardApi;
