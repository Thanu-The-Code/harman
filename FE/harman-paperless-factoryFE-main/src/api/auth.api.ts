import { api } from "./baseApi";

export interface LoginPayload {
  username: string; // a username or an email address
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  must_change_password: boolean;
  user: {
    username: string;
    full_name: string | null;
    is_admin: boolean;
    role_names: string[];
  };
}

/** `GET /api/auth/me` (UserResponse). */
export interface CurrentUser {
  id: string;
  username: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_admin: boolean;
  permissions: string[];
  role_ids: string[];
  role_names: string[];
  account_type: string | null;
  department: string | null;
  department_id: string | null;
  job_title: string | null;
  can_approve: boolean;
  can_sign: boolean;
  quality_team_id: string | null;
  last_login: string | null;
  created_at: string;
}

export interface ChangePasswordPayload {
  current_password: string;
  new_password: string;
}

export const authApi = api.injectEndpoints({
  endpoints: (build) => ({
    login: build.mutation<LoginResponse, LoginPayload>({
      query: (data) => ({ url: "api/auth/login", method: "POST", data }),
    }),
    me: build.query<CurrentUser, void>({
      query: () => ({ url: "api/auth/me" }),
      providesTags: ["Me"],
    }),
    logout: build.mutation<{ message: string }, void>({
      query: () => ({ url: "api/auth/logout", method: "POST" }),
    }),
    // the old password's sign-ins end; this one continues with the token handed back
    changePassword: build.mutation<{ message: string; access_token?: string }, ChangePasswordPayload>({
      query: (data) => ({ url: "api/auth/change-password", method: "POST", data }),
    }),
  }),
});

export const { useLoginMutation, useMeQuery, useLogoutMutation, useChangePasswordMutation } =
  authApi;

/** "Ravi Kumar" → "Ravi", falling back to the username. */
export const firstName = (user?: Pick<CurrentUser, "full_name" | "username"> | null) =>
  user?.full_name?.trim().split(/\s+/)[0] || user?.username || "";

/** What the header shows under the name. */
// what the person does ("Process Owner - Machining") says more than the shared access role
export const roleLabel = (user?: CurrentUser | null) =>
  !user ? "" : user.is_admin ? "Administrator" : user.job_title || user.role_names[0] || "Member";
