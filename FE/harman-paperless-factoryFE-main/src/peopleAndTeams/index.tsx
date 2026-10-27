import { useMemo, useState } from "react";
import { Box, Button, IconButton } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import type { ColDef } from "ag-grid-community";
import { toast } from "react-toastify";
import CustomTabs, { type TabOption } from "../base/tabs/CustomTabs";
import CustomSelect from "../base/dropdown/CustomSelect";
import CustomSearchBox from "../base/search/CustomSearch";
import CustomAgGrid from "../base/aggrid";
import CustomDialog from "../base/dialog/CustomDialog";
import { ErrorState, PageLoader } from "../base/feedback";
import { peopleTeamsStyles } from "./style";
import PageHeader from "../base/pageHeader";
import TeamCard from "../base/card/TeamCards";
import {
  AddPersonDialog,
  DepartmentDialog,
  EditPersonDialog,
  RoleDialog,
  TeamDialog,
  type NewPersonData,
  type PersonChanges,
} from "./PeopleDialog";
import { getDepartmentColumns, getPeopleColumns, getRoleColumns, initials } from "./columns";
import { useMeQuery } from "../api/auth.api";
import { useFormatTeamsQuery, type QualityTeam } from "../api/formats.api";
import {
  useAssignRoleMutation,
  useCapabilitiesQuery,
  useCreateDepartmentMutation,
  useCreateRoleMutation,
  useCreateTeamMutation,
  useCreateUserMutation,
  useDeleteDepartmentMutation,
  useDeleteRoleMutation,
  useDeleteUserMutation,
  useDepartmentsQuery,
  useRolesQuery,
  useSetTeamActiveMutation,
  useUpdateRoleMutation,
  useUpdateTeamMutation,
  useUpdateUserMutation,
  useUsersQuery,
  type Department,
  type Role,
  type User,
} from "../api/admin.api";
import { getApiErrorMessage } from "../api/errors";

type Tab = "teams" | "people" | "roles" | "departments";

const TABS: TabOption<Tab>[] = [
  { value: "teams", label: "Teams" },
  { value: "people", label: "People" },
  { value: "roles", label: "Roles" },
  { value: "departments", label: "Departments" },
];

type Dialog =
  | { kind: "person" }
  | { kind: "edit-person"; user: User }
  | { kind: "delete-person"; user: User }
  | { kind: "team"; team?: QualityTeam }
  | { kind: "role"; role?: Role }
  | { kind: "delete-role"; role: Role }
  | { kind: "department" }
  | { kind: "delete-department"; department: Department }
  | null;

const attempt = async (action: () => Promise<unknown>, success: string, failure: string) => {
  try {
    await action();
    toast.success(success);
    return true;
  } catch (error) {
    toast.error(getApiErrorMessage(error, failure));
    return false;
  }
};

const memberColumns: ColDef<QualityTeam["people"][number]>[] = [
  { field: "name", headerName: "Name", flex: 1.4, minWidth: 180 },
  { field: "job_title", headerName: "Job title", flex: 1.4, minWidth: 180 },
  { field: "email", headerName: "Email", flex: 1.5, minWidth: 200 },
  { field: "department", headerName: "Department", flex: 1, minWidth: 140 },
  {
    headerName: "May approve / sign",
    flex: 1,
    minWidth: 150,
    valueGetter: (p) => (p.data ? `${p.data.can_approve ? "Approve" : "—"} / ${p.data.can_sign ? "Sign" : "—"}` : ""),
  },
];

/** People, quality teams, roles and departments (administrators). */
const PeopleTeamsPage = () => {
  const { data: me } = useMeQuery();
  const [tab, setTab] = useState<Tab>("teams");
  const [search, setSearch] = useState("");
  const [department, setDepartment] = useState("");
  const [activeTeamId, setActiveTeamId] = useState<string | null>(null);
  const [confirmRetire, setConfirmRetire] = useState(false);
  const [activeRoleId, setActiveRoleId] = useState<string | null>(null);
  const [dialog, setDialog] = useState<Dialog>(null);
  const close = () => setDialog(null);

  const teamsQ = useFormatTeamsQuery();
  const usersQ = useUsersQuery();
  const rolesQ = useRolesQuery();
  const departmentsQ = useDepartmentsQuery();
  const { data: capabilities = [] } = useCapabilitiesQuery();

  const [createUser, { isLoading: creatingUser }] = useCreateUserMutation();
  const [updateUser, { isLoading: updatingUser }] = useUpdateUserMutation();
  const [deleteUser] = useDeleteUserMutation();
  const [assignRole] = useAssignRoleMutation();
  const [createTeam, { isLoading: creatingTeam }] = useCreateTeamMutation();
  const [updateTeam, { isLoading: updatingTeam }] = useUpdateTeamMutation();
  const [setTeamActive] = useSetTeamActiveMutation();
  const [createRole, { isLoading: creatingRole }] = useCreateRoleMutation();
  const [updateRole, { isLoading: updatingRole }] = useUpdateRoleMutation();
  const [deleteRole] = useDeleteRoleMutation();
  const [createDepartment, { isLoading: creatingDept }] = useCreateDepartmentMutation();
  const [deleteDepartment] = useDeleteDepartmentMutation();

  const teams = useMemo(() => teamsQ.data?.teams ?? [], [teamsQ.data]);
  const users = useMemo(() => usersQ.data ?? [], [usersQ.data]);
  const roles = rolesQ.data ?? [];
  const departments = departmentsQ.data?.departments ?? [];
  const options = { roles, departments, teams };

  const activeTeam = teams.find((t) => t.id === activeTeamId) ?? null;
  const activeRole = roles.find((r) => r.id === activeRoleId) ?? null;

  const departmentOptions = useMemo(
    () => Array.from(new Set(users.map((u) => u.department).filter((d): d is string => !!d))).map((d) => ({ value: d, label: d })),
    [users],
  );
  const peopleRows = users.filter(
    (u) => (!department || u.department === department) && (!activeRole || u.role_ids.includes(activeRole.id)),
  );

  const peopleColumns = useMemo(
    () =>
      getPeopleColumns({
        onEdit: (u) => setDialog({ kind: "edit-person", user: u }),
        onDelete: (u) => setDialog({ kind: "delete-person", user: u }),
        meId: me?.id,
        teamName: (id) => teams.find((t) => t.id === id)?.name ?? "—",
      }),
    [me?.id, teams],
  );
  const roleColumns = useMemo(
    () =>
      getRoleColumns({
        onView: (r) => setActiveRoleId(r.id),
        onEdit: (r) => setDialog({ kind: "role", role: r }),
        onDelete: (r) => setDialog({ kind: "delete-role", role: r }),
      }),
    [],
  );
  const departmentColumns = useMemo(
    () =>
      getDepartmentColumns({
        onDelete: (d) => setDialog({ kind: "delete-department", department: d }),
        people: (d) => users.filter((u) => u.department_id === d.id || u.department === d.name).length,
      }),
    [users],
  );

  const changeTab = (next: Tab) => {
    setTab(next);
    setActiveTeamId(null);
    setActiveRoleId(null);
    setSearch("");
    setDepartment("");
  };

  /* ------------------------------------------------------------ actions */

  const addPerson = async (f: NewPersonData) => {
    try {
      const user = await createUser({
        username: f.username.trim(),
        email: f.email.trim(),
        full_name: f.fullName.trim(),
        password: f.password,
        role_id: f.roleId,
        department_id: f.departmentId || null,
        job_title: f.jobTitle.trim() || null,
      }).unwrap();
      if (f.teamId) await updateUser({ id: user.id, quality_team_id: f.teamId }).unwrap();
      toast.success(`${user.full_name ?? user.username} added.`);
      close();
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Could not add the person."));
    }
  };

  const savePerson = async (user: User, c: PersonChanges) => {
    try {
      await updateUser({
        id: user.id,
        full_name: c.full_name.trim(),
        email: c.email.trim(),
        job_title: c.job_title.trim() || null,
        quality_team_id: c.quality_team_id || null,
        is_active: c.is_active,
        ...(c.department_id ? { department_id: c.department_id } : {}),
        ...(c.password ? { password: c.password } : {}),
      }).unwrap();
      if (!user.is_admin && c.role_id && c.role_id !== user.role_ids[0]) {
        await assignRole({ userId: user.id, role_id: c.role_id }).unwrap();
      }
      toast.success("Saved.");
      close();
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Could not save."));
    }
  };

  /* -------------------------------------------------------------- view */

  const loading = teamsQ.isLoading || usersQ.isLoading || rolesQ.isLoading;
  const failed = teamsQ.isError || usersQ.isError || rolesQ.isError;

  const toolbar = (
    <div className="roles-toolbar">
      <CustomSelect
        options={departmentOptions}
        value={department}
        onChange={setDepartment}
        placeholder="All Departments"
        ariaLabel="Filter by department"
      />
      <div className="header-search">
        <CustomSearchBox
          ariaLabel="Search people by name, email or role"
          placeholder="Search people by name, email or role"
          value={search}
          onChange={setSearch}
        />
      </div>
    </div>
  );

  const headerActions = (
    <>
      {tab === "teams" && (
        <Button className="header-btn new-team-btn" startIcon={<AddIcon fontSize="small" />} onClick={() => setDialog({ kind: "team" })}>
          New team
        </Button>
      )}
      {tab === "roles" && (
        <Button className="header-btn new-team-btn" startIcon={<AddIcon fontSize="small" />} onClick={() => setDialog({ kind: "role" })}>
          Add Role
        </Button>
      )}
      {tab === "departments" && (
        <Button className="header-btn new-team-btn" startIcon={<AddIcon fontSize="small" />} onClick={() => setDialog({ kind: "department" })}>
          Add department
        </Button>
      )}
      <Button className="header-btn add-person-btn" variant="contained" startIcon={<AddIcon fontSize="small" />} onClick={() => setDialog({ kind: "person" })}>
        Add a person
      </Button>
    </>
  );

  const detail = activeTeam ?? activeRole;

  return (
    <Box className="people-teams-page" sx={peopleTeamsStyles}>
      {detail ? (
        <div className="detail-header">
          <IconButton className="back-btn" aria-label="Back" onClick={() => (activeTeam ? setActiveTeamId(null) : setActiveRoleId(null))}>
            <ChevronLeftIcon fontSize="small" />
          </IconButton>
          <span className="detail-avatar">{activeTeam ? activeTeam.code : initials(activeRole!.name)}</span>
          <div className="detail-titles">
            <h1 className="detail-title">{activeTeam ? activeTeam.name : activeRole!.name}</h1>
            <p className="detail-subtitle">
              {activeTeam
                ? `${activeTeam.people.length} people · ${activeTeam.format_count} formats${activeTeam.is_active ? "" : " · retired"}`
                : activeRole!.description ?? `${activeRole!.user_count} members`}
            </p>
          </div>
          {activeTeam && (
            <>
              <Button
                className="header-btn"
                onClick={() =>
                  activeTeam.is_active
                    ? setConfirmRetire(true) // retiring takes the team out of every picker: ask first
                    : attempt(() => setTeamActive({ id: activeTeam.id, active: true }).unwrap(), "Team restored.", "Could not change the team.")
                }
              >
                {activeTeam.is_active ? "Retire" : "Restore"}
              </Button>
              <Button className="header-btn edit-btn" startIcon={<EditOutlinedIcon fontSize="small" />} onClick={() => setDialog({ kind: "team", team: activeTeam })}>
                Edit
              </Button>
            </>
          )}
          {activeRole && (
            <Button className="header-btn edit-btn" startIcon={<EditOutlinedIcon fontSize="small" />} onClick={() => setDialog({ kind: "role", role: activeRole })}>
              Edit
            </Button>
          )}
        </div>
      ) : (
        <PageHeader title="Roles & Permissions" subtitle="Manage people, teams, roles, and access in one place." actions={headerActions} />
      )}

      <div className="page-body">
        {!detail && (
          <div className="tabs-bar">
            <CustomTabs tabs={TABS} value={tab} onChange={changeTab} />
          </div>
        )}

        {loading ? (
          <PageLoader />
        ) : failed ? (
          <ErrorState message="Could not load people and teams." onRetry={() => { teamsQ.refetch(); usersQ.refetch(); rolesQ.refetch(); }} />
        ) : activeTeam ? (
          <div className="roles-panel">
            <div className="roles-grid">
              <CustomAgGrid rowData={activeTeam.people} columnDefs={memberColumns} pagination pageSize={10} emptyText="Nobody is in this team yet" />
            </div>
          </div>
        ) : tab === "teams" ? (
          <div className="teams-grid">
            {teams.map((t) => (
              <TeamCard
                key={t.id}
                team={{
                  id: t.id,
                  code: t.code,
                  name: t.is_active ? t.name : `${t.name} (retired)`,
                  members: t.people.length,
                  memberInitials: t.people.slice(0, 3).map((p) => initials(p.name)),
                }}
                onOpen={() => setActiveTeamId(t.id)}
              />
            ))}
          </div>
        ) : tab === "people" || activeRole ? (
          <div className="roles-panel">
            {toolbar}
            <div className="roles-grid">
              <CustomAgGrid<User>
                rowData={peopleRows}
                columnDefs={peopleColumns}
                quickFilterText={search}
                pagination
                pageSize={10}
                emptyText="No people found"
              />
            </div>
          </div>
        ) : tab === "roles" ? (
          <div className="roles-panel">
            <div className="roles-grid">
              <CustomAgGrid<Role> rowData={roles} columnDefs={roleColumns} pagination pageSize={10} emptyText="No roles yet" />
            </div>
          </div>
        ) : (
          <div className="roles-panel">
            <div className="roles-grid">
              <CustomAgGrid<Department> rowData={departments} columnDefs={departmentColumns} emptyText="No departments yet" />
            </div>
          </div>
        )}
      </div>

      {dialog?.kind === "person" && <AddPersonDialog open onClose={close} onConfirm={addPerson} busy={creatingUser} {...options} />}
      {dialog?.kind === "edit-person" && (
        <EditPersonDialog user={dialog.user} onClose={close} onConfirm={(c) => savePerson(dialog.user, c)} busy={updatingUser} {...options} />
      )}
      {dialog?.kind === "team" && (
        <TeamDialog
          initial={dialog.team ? { code: dialog.team.code, name: dialog.team.name, responsibility: dialog.team.description ?? "" } : undefined}
          busy={creatingTeam || updatingTeam}
          onClose={close}
          onConfirm={async (d) => {
            const payload = { code: d.code, name: d.name, description: d.responsibility || null };
            const ok = await attempt(
              () => (dialog.team ? updateTeam({ id: dialog.team.id, ...payload }).unwrap() : createTeam(payload).unwrap()),
              dialog.team ? "Team saved." : `Team ${d.code} added.`,
              "Could not save the team.",
            );
            if (ok) close();
          }}
        />
      )}
      {dialog?.kind === "role" && (
        <RoleDialog
          initial={dialog.role}
          capabilities={capabilities}
          busy={creatingRole || updatingRole}
          onClose={close}
          onConfirm={async (d) => {
            const ok = await attempt(
              () => (dialog.role ? updateRole({ id: dialog.role.id, ...d }).unwrap() : createRole(d).unwrap()),
              dialog.role ? "Role saved." : `Role ${d.name} added.`,
              "Could not save the role.",
            );
            if (ok) close();
          }}
        />
      )}
      {dialog?.kind === "department" && (
        <DepartmentDialog
          busy={creatingDept}
          onClose={close}
          onConfirm={async (name) => {
            if (await attempt(() => createDepartment({ name }).unwrap(), `${name} added.`, "Could not add the department.")) close();
          }}
        />
      )}
      <CustomDialog
        open={confirmRetire && !!activeTeam}
        maxWidth="xs"
        onClose={() => setConfirmRetire(false)}
        title={`Retire ${activeTeam?.name ?? "the team"}?`}
        confirmText="Retire"
        onConfirm={async () => {
          if (!activeTeam) return;
          if (await attempt(() => setTeamActive({ id: activeTeam.id, active: false }).unwrap(), "Team retired.", "Could not change the team.")) setConfirmRetire(false);
        }}
      >
        <span>
          It is no longer offered for new templates or people. Its templates, records and people stay as they are, and it
          can be restored at any time.
        </span>
      </CustomDialog>
      <CustomDialog
        open={dialog?.kind === "delete-person" || dialog?.kind === "delete-role" || dialog?.kind === "delete-department"}
        maxWidth="xs"
        onClose={close}
        title="Delete?"
        confirmText="Delete"
        onConfirm={async () => {
          if (dialog?.kind === "delete-person") {
            if (await attempt(() => deleteUser(dialog.user.id).unwrap(), "Person deleted.", "Could not delete the person.")) close();
          } else if (dialog?.kind === "delete-role") {
            if (await attempt(() => deleteRole(dialog.role.id).unwrap(), "Role deleted.", "Could not delete the role.")) close();
          } else if (dialog?.kind === "delete-department") {
            if (await attempt(() => deleteDepartment(dialog.department.id).unwrap(), "Department deleted.", "Could not delete the department.")) close();
          }
        }}
      >
        <span>
          {dialog?.kind === "delete-person"
            ? `Delete ${dialog.user.full_name || dialog.user.username}? Consider making them inactive instead: their records keep their name either way.`
            : dialog?.kind === "delete-role"
              ? `Delete the role "${dialog.role.name}"?`
              : dialog?.kind === "delete-department"
                ? `Delete the department "${dialog.department.name}"?`
                : ""}
        </span>
      </CustomDialog>
    </Box>
  );
};

export default PeopleTeamsPage;
