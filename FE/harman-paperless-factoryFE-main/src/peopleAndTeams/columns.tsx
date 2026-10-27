/* eslint-disable react-refresh/only-export-components */
import { IconButton } from "@mui/material";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import DeleteOutlinedIcon from "@mui/icons-material/DeleteOutlined";
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { InitialsAvatar } from "../base/avatar";
import CustomChip from "../base/chip/CustomChip";
import type { Capability, Department, Role, User } from "../api/admin.api";
import { formatDate } from "../utils/date";

export const initials = (name: string) =>
  name
    .split(/[\s.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");

export const CAPABILITY_LABEL: Record<Capability, string> = {
  "documents.view": "View",
  "records.fill": "Fill records",
  "templates.create": "Create templates",
  "approvals.approve": "Approval",
};

/* ---------- people ---------- */
const NameCell = ({ data }: ICellRendererParams<User>) =>
  data ? (
    <div className="person-cell">
      <InitialsAvatar initials={initials(data.full_name || data.username)} size={32} />
      <div>
        <div className="person-name">{data.full_name || data.username}</div>
        <div className="person-title">{data.job_title ?? data.username}</div>
      </div>
    </div>
  ) : null;

const RoleCell = ({ data }: ICellRendererParams<User>) =>
  data ? (
    <div className="chip-row">
      {data.is_admin ? (
        <CustomChip label="Administrator" variant="purple" />
      ) : data.role_names.length ? (
        data.role_names.map((r) => <CustomChip key={r} label={r} variant="blue" />)
      ) : (
        <CustomChip label="No role" variant="orange" />
      )}
    </div>
  ) : null;

const StatusCell = ({ data }: ICellRendererParams<User>) =>
  data ? <CustomChip label={data.is_active ? "Active" : "Inactive"} variant={data.is_active ? "green" : "gray"} /> : null;

interface PersonActions {
  onEdit: (u: User) => void;
  onDelete: (u: User) => void;
  meId?: string;
}

const PersonActionCell = ({ data, onEdit, onDelete, meId }: ICellRendererParams<User> & PersonActions) =>
  data ? (
    <div className="action-cell">
      <IconButton className="icon-btn" size="small" aria-label={`Edit ${data.username}`} onClick={() => onEdit(data)}>
        <EditOutlinedIcon fontSize="small" />
      </IconButton>
      {data.id !== meId && (
        <IconButton className="icon-btn" size="small" aria-label={`Delete ${data.username}`} onClick={() => onDelete(data)}>
          <DeleteOutlinedIcon fontSize="small" />
        </IconButton>
      )}
    </div>
  ) : null;

export const getPeopleColumns = (
  handlers: PersonActions & { teamName: (id: string | null) => string },
): ColDef<User>[] => [
  { headerName: "Name", flex: 1.6, minWidth: 220, cellRenderer: NameCell, autoHeight: true, getQuickFilterText: (p) => `${p.data?.full_name} ${p.data?.username}` },
  { field: "email", headerName: "Email", flex: 1.5, minWidth: 200 },
  { headerName: "Department", flex: 1.1, minWidth: 140, valueGetter: (p) => p.data?.department ?? "—" },
  { headerName: "Quality team", flex: 1.1, minWidth: 140, valueGetter: (p) => handlers.teamName(p.data?.quality_team_id ?? null) },
  { headerName: "Role", flex: 1.2, minWidth: 150, cellRenderer: RoleCell, getQuickFilterText: (p) => p.data?.role_names.join(" ") ?? "" },
  { headerName: "Status", width: 110, cellRenderer: StatusCell },
  {
    headerName: "Action",
    width: 110,
    headerClass: "ag-center-header",
    cellRenderer: PersonActionCell,
    cellRendererParams: { onEdit: handlers.onEdit, onDelete: handlers.onDelete, meId: handlers.meId },
  },
];

/* ---------- roles ---------- */
const CapabilitiesCell = ({ data }: ICellRendererParams<Role>) =>
  data ? (
    <div className="chip-row">
      {data.permissions.map((c) => (
        <CustomChip key={c} label={CAPABILITY_LABEL[c] ?? c} variant="blue" />
      ))}
    </div>
  ) : null;

interface RoleActions {
  onView: (r: Role) => void;
  onEdit: (r: Role) => void;
  onDelete: (r: Role) => void;
}

const RoleActionCell = ({ data, onView, onEdit, onDelete }: ICellRendererParams<Role> & RoleActions) =>
  data ? (
    <div className="action-cell">
      <IconButton className="icon-btn" size="small" aria-label={`Members of ${data.name}`} onClick={() => onView(data)}>
        <VisibilityOutlinedIcon fontSize="small" />
      </IconButton>
      <IconButton className="icon-btn" size="small" aria-label={`Edit ${data.name}`} onClick={() => onEdit(data)}>
        <EditOutlinedIcon fontSize="small" />
      </IconButton>
      {data.user_count === 0 && (
        <IconButton className="icon-btn" size="small" aria-label={`Delete ${data.name}`} onClick={() => onDelete(data)}>
          <DeleteOutlinedIcon fontSize="small" />
        </IconButton>
      )}
    </div>
  ) : null;

export const getRoleColumns = (handlers: RoleActions): ColDef<Role>[] => [
  { field: "name", headerName: "Role", flex: 1.2, minWidth: 170 },
  { headerName: "What it allows", flex: 2, minWidth: 260, cellRenderer: CapabilitiesCell, autoHeight: true },
  { field: "user_count", headerName: "Members", width: 110 },
  { headerName: "Created", flex: 0.8, minWidth: 120, valueGetter: (p) => formatDate(p.data?.created_at) },
  {
    headerName: "Action",
    width: 140,
    headerClass: "ag-center-header",
    cellRenderer: RoleActionCell,
    cellRendererParams: handlers,
  },
];

/* ---------- departments ---------- */
export const getDepartmentColumns = ({
  onDelete,
  people,
}: {
  onDelete: (d: Department) => void;
  people: (d: Department) => number;
}): ColDef<Department>[] => [
  { field: "name", headerName: "Department", flex: 2, minWidth: 220 },
  { headerName: "People", width: 120, valueGetter: (p) => (p.data ? people(p.data) : 0) },
  {
    headerName: "Action",
    width: 110,
    headerClass: "ag-center-header",
    cellRenderer: ({ data }: ICellRendererParams<Department>) =>
      data ? (
        <div className="action-cell">
          <IconButton className="icon-btn" size="small" aria-label={`Delete ${data.name}`} onClick={() => onDelete(data)}>
            <DeleteOutlinedIcon fontSize="small" />
          </IconButton>
        </div>
      ) : null,
  },
];
