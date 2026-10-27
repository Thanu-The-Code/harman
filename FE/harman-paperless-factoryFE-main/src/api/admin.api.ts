import { api } from "./baseApi";
import type { CurrentUser } from "./auth.api";

/* People, roles, departments and quality teams (administrators). */

export type User = CurrentUser;

export type Capability = "documents.view" | "records.fill" | "templates.create" | "approvals.approve";

export interface Role {
  id: string;
  name: string;
  description: string | null;
  permissions: Capability[];
  assignable: boolean;
  user_count: number;
  created_at: string;
  updated_at: string | null;
}

export interface Department {
  id: string;
  name: string;
}

export interface NewUserPayload {
  username: string;
  email: string;
  full_name: string;
  password: string;
  role_id: string;
  department_id?: string | null;
  job_title?: string | null;
}

export interface UserUpdatePayload {
  email?: string;
  full_name?: string;
  is_active?: boolean;
  password?: string;
  department_id?: string | null;
  job_title?: string | null;
  quality_team_id?: string | null;
}

export interface TeamPayload {
  code: string;
  name: string;
  description?: string | null;
}

export const adminApi = api.injectEndpoints({
  endpoints: (build) => ({
    /* people */
    users: build.query<User[], void>({
      query: () => ({ url: "api/auth/users" }),
      providesTags: ["Users"],
    }),
    createUser: build.mutation<User, NewUserPayload>({
      query: (data) => ({ url: "api/auth/users", method: "POST", data }),
      invalidatesTags: ["Users", "Roles", "Teams"],
    }),
    updateUser: build.mutation<User, { id: string } & UserUpdatePayload>({
      query: ({ id, ...data }) => ({ url: `api/auth/users/${id}`, method: "PUT", data }),
      invalidatesTags: ["Users", "Teams", "Me"],
    }),
    deleteUser: build.mutation<{ message: string }, string>({
      query: (id) => ({ url: `api/auth/users/${id}`, method: "DELETE" }),
      invalidatesTags: ["Users", "Roles", "Teams"],
    }),
    assignRole: build.mutation<unknown, { userId: string; role_id: string }>({
      query: ({ userId, role_id }) => ({ url: `api/roles/users/${userId}`, method: "PUT", data: { role_id } }),
      invalidatesTags: ["Users", "Roles", "Me"],
    }),

    /* roles: no trailing slash on /api/roles */
    roles: build.query<Role[], void>({
      query: () => ({ url: "api/roles" }),
      providesTags: ["Roles"],
    }),
    capabilities: build.query<{ key: Capability; description: string }[], void>({
      query: () => ({ url: "api/roles/permissions" }),
    }),
    createRole: build.mutation<Role, { name: string; description?: string; permissions: Capability[] }>({
      query: (data) => ({ url: "api/roles", method: "POST", data }),
      invalidatesTags: ["Roles"],
    }),
    updateRole: build.mutation<Role, { id: string; name?: string; description?: string; permissions?: Capability[] }>({
      query: ({ id, ...data }) => ({ url: `api/roles/${id}`, method: "PUT", data }),
      invalidatesTags: ["Roles", "Users"],
    }),
    deleteRole: build.mutation<{ message: string }, string>({
      query: (id) => ({ url: `api/roles/${id}`, method: "DELETE" }),
      invalidatesTags: ["Roles"],
    }),

    /* departments: no trailing slash on /api/departments */
    departments: build.query<{ departments: Department[]; total: number }, void>({
      query: () => ({ url: "api/departments" }),
      providesTags: ["Departments"],
    }),
    createDepartment: build.mutation<Department, { name: string }>({
      query: (data) => ({ url: "api/departments", method: "POST", data }),
      invalidatesTags: ["Departments"],
    }),
    deleteDepartment: build.mutation<{ message: string }, string>({
      query: (id) => ({ url: `api/departments/${id}`, method: "DELETE" }),
      invalidatesTags: ["Departments", "Users"],
    }),

    /* quality teams (read with formatsApi.formatTeams) */
    createTeam: build.mutation<{ id: string; code: string; name: string }, TeamPayload>({
      query: (data) => ({ url: "api/formats/teams", method: "POST", data }),
      invalidatesTags: ["Teams"],
    }),
    updateTeam: build.mutation<{ id: string; code: string; name: string }, { id: string } & TeamPayload>({
      query: ({ id, ...data }) => ({ url: `api/formats/teams/${id}`, method: "PUT", data }),
      invalidatesTags: ["Teams"],
    }),
    setTeamActive: build.mutation<{ id: string; is_active: boolean }, { id: string; active: boolean }>({
      query: ({ id, active }) => ({ url: `api/formats/teams/${id}/${active ? "restore" : "retire"}`, method: "POST" }),
      invalidatesTags: ["Teams"],
    }),
  }),
});

export const {
  useUsersQuery,
  useCreateUserMutation,
  useUpdateUserMutation,
  useDeleteUserMutation,
  useAssignRoleMutation,
  useRolesQuery,
  useCapabilitiesQuery,
  useCreateRoleMutation,
  useUpdateRoleMutation,
  useDeleteRoleMutation,
  useDepartmentsQuery,
  useCreateDepartmentMutation,
  useDeleteDepartmentMutation,
  useCreateTeamMutation,
  useUpdateTeamMutation,
  useSetTeamActiveMutation,
} = adminApi;
