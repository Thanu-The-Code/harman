import { useState } from "react";
import { Checkbox, FormControlLabel, MenuItem, Switch, TextField } from "@mui/material";
import CustomDialog from "../base/dialog/CustomDialog";
import CustomTextField from "../base/dialog/CustomTextField";
import CustomTextArea from "../base/dialog/CustomTextarea";
import type { Capability, Department, Role, User } from "../api/admin.api";
import type { QualityTeam } from "../api/formats.api";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MIN_PASSWORD = 8;

interface BaseProps {
  open: boolean;
  onClose: () => void;
}

interface Options {
  roles: Role[];
  departments: Department[];
  teams: QualityTeam[];
}

const Select = ({
  label,
  value,
  onChange,
  options,
  helperText,
  emptyLabel,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  helperText?: string;
  emptyLabel?: string;
}) => (
  <TextField select fullWidth size="small" label={label} value={value} onChange={(e) => onChange(e.target.value)} helperText={helperText}>
    {emptyLabel !== undefined && (
      <MenuItem value="">
        <em>{emptyLabel}</em>
      </MenuItem>
    )}
    {options.map((o) => (
      <MenuItem key={o.value} value={o.value}>
        {o.label}
      </MenuItem>
    ))}
  </TextField>
);

/* ============================ Add a person ============================ */
export interface NewPersonData {
  fullName: string;
  username: string;
  email: string;
  teamId: string;
  jobTitle: string;
  departmentId: string;
  password: string;
  roleId: string;
}

const EMPTY_PERSON: NewPersonData = {
  fullName: "",
  username: "",
  email: "",
  teamId: "",
  jobTitle: "",
  departmentId: "",
  password: "",
  roleId: "",
};

export const AddPersonDialog = ({
  open,
  onClose,
  onConfirm,
  roles,
  departments,
  teams,
  busy,
}: BaseProps & Options & { onConfirm: (data: NewPersonData) => void; busy?: boolean }) => {
  const [form, setForm] = useState<NewPersonData>(EMPTY_PERSON);
  const set = (key: keyof NewPersonData) => (value: string) => setForm((f) => ({ ...f, [key]: value }));

  const valid =
    form.fullName.trim() &&
    form.username.trim() &&
    EMAIL_RE.test(form.email.trim()) &&
    form.password.length >= MIN_PASSWORD &&
    form.roleId;

  return (
    <CustomDialog
      open={open}
      onClose={onClose}
      title="Add a person"
      confirmText={busy ? "Adding…" : "Add Person"}
      confirmDisabled={!valid || busy}
      onConfirm={() => onConfirm(form)}
    >
      <div className="dialog-row">
        <CustomTextField label="Full name" placeholder="Enter name" value={form.fullName} onChange={set("fullName")} />
        <CustomTextField label="Username" placeholder="Enter username" value={form.username} onChange={set("username")} />
      </div>
      <CustomTextField
        label="Work email"
        type="email"
        placeholder="name@harman.com"
        value={form.email}
        onChange={set("email")}
        helperText="Every approval request goes here."
      />
      <div className="dialog-row" style={{ marginTop: 12 }}>
        <Select
          label="Quality team"
          value={form.teamId}
          onChange={set("teamId")}
          emptyLabel="None"
          options={teams.filter((t) => t.is_active).map((t) => ({ value: t.id, label: `${t.code} - ${t.name}` }))}
        />
        <CustomTextField label="Job title" placeholder="e.g. Process Owner — Machining" value={form.jobTitle} onChange={set("jobTitle")} />
      </div>
      <div style={{ marginTop: 12 }}>
        <Select
          label="Department"
          value={form.departmentId}
          onChange={set("departmentId")}
          emptyLabel="None"
          options={departments.map((d) => ({ value: d.id, label: d.name }))}
          helperText="Where they sit in the organisation; it can differ from their quality team."
        />
      </div>
      <CustomTextField
        label="Temporary password"
        type="password"
        placeholder={`At least ${MIN_PASSWORD} characters`}
        value={form.password}
        onChange={set("password")}
        helperText="They should change it after signing in."
      />
      <div className="dialog-section">
        <div className="dialog-section-title">What they may do</div>
        <Select
          label="Role"
          value={form.roleId}
          onChange={set("roleId")}
          options={roles.filter((r) => r.assignable).map((r) => ({ value: r.id, label: r.name }))}
          helperText="Approving and signing come from the role. Being named on a format decides which records they act on."
        />
      </div>
    </CustomDialog>
  );
};

/* ============================ Edit a person ============================ */
export interface PersonChanges {
  full_name: string;
  email: string;
  job_title: string;
  department_id: string;
  quality_team_id: string;
  is_active: boolean;
  role_id: string;
  password: string;
}

export const EditPersonDialog = ({
  user,
  onClose,
  onConfirm,
  roles,
  departments,
  teams,
  busy,
}: Options & { user: User; onClose: () => void; onConfirm: (changes: PersonChanges) => void; busy?: boolean }) => {
  const [form, setForm] = useState<PersonChanges>({
    full_name: user.full_name ?? "",
    email: user.email,
    job_title: user.job_title ?? "",
    department_id: user.department_id ?? "",
    quality_team_id: user.quality_team_id ?? "",
    is_active: user.is_active,
    role_id: user.role_ids[0] ?? "",
    password: "",
  });
  const set = <K extends keyof PersonChanges>(key: K) => (value: PersonChanges[K]) => setForm((f) => ({ ...f, [key]: value }));
  const valid = form.full_name.trim() && EMAIL_RE.test(form.email.trim()) && (!form.password || form.password.length >= MIN_PASSWORD);

  return (
    <CustomDialog
      open
      onClose={onClose}
      title={`Edit ${user.full_name || user.username}`}
      subtitle={`Signed in as ${user.username}${user.last_login ? "" : " — has not signed in yet"}`}
      confirmText={busy ? "Saving…" : "Save"}
      confirmDisabled={!valid || busy}
      onConfirm={() => onConfirm(form)}
    >
      <div className="dialog-row">
        <CustomTextField label="Full name" value={form.full_name} onChange={set("full_name")} />
        <CustomTextField label="Job title" value={form.job_title} onChange={set("job_title")} />
      </div>
      <CustomTextField label="Work email" type="email" value={form.email} onChange={set("email")} />
      <div className="dialog-row" style={{ marginTop: 12 }}>
        <Select
          label="Quality team"
          value={form.quality_team_id}
          onChange={set("quality_team_id")}
          emptyLabel="None"
          options={teams.map((t) => ({ value: t.id, label: `${t.code} - ${t.name}` }))}
        />
        <Select
          label="Department"
          value={form.department_id}
          onChange={set("department_id")}
          emptyLabel={user.department && !user.department_id ? `${user.department} (unlisted)` : "None"}
          options={departments.map((d) => ({ value: d.id, label: d.name }))}
        />
      </div>
      {!user.is_admin && (
        <div style={{ marginTop: 12 }}>
          <Select
            label="Role"
            value={form.role_id}
            onChange={set("role_id")}
            emptyLabel="No role"
            options={roles.filter((r) => r.assignable).map((r) => ({ value: r.id, label: r.name }))}
          />
        </div>
      )}
      <CustomTextField
        label="New password"
        type="password"
        placeholder="Leave blank to keep the current one"
        value={form.password}
        onChange={set("password")}
      />
      <FormControlLabel
        control={<Switch checked={form.is_active} onChange={(e) => set("is_active")(e.target.checked)} />}
        label={form.is_active ? "Active — can sign in" : "Inactive — cannot sign in"}
      />
    </CustomDialog>
  );
};

/* ============================ Quality team ============================ */
export interface TeamData {
  code: string;
  name: string;
  responsibility: string;
}

export const TeamDialog = ({
  initial,
  onClose,
  onConfirm,
  busy,
}: { initial?: TeamData; onClose: () => void; onConfirm: (data: TeamData) => void; busy?: boolean }) => {
  const [form, setForm] = useState<TeamData>(initial ?? { code: "", name: "", responsibility: "" });
  const set = (key: keyof TeamData) => (value: string) => setForm((f) => ({ ...f, [key]: value }));

  return (
    <CustomDialog
      open
      onClose={onClose}
      title={initial ? "Edit quality team" : "New quality team"}
      subtitle="A team owns its own form templates and its own people."
      confirmText={busy ? "Saving…" : initial ? "Save" : "Add Team"}
      confirmDisabled={busy || !form.code || !form.name.trim()}
      onConfirm={() => onConfirm({ ...form, name: form.name.trim(), responsibility: form.responsibility.trim() })}
    >
      <div className="dialog-row">
        <CustomTextField
          label="Short code"
          placeholder="e.g. PQ"
          value={form.code}
          // letters and digits only, shown in capitals
          onChange={(v) => set("code")(v.replace(/[^a-zA-Z0-9]/g, "").toUpperCase())}
          helperText="Used in template codes. Letters and digits."
        />
        <CustomTextField label="Team name" placeholder="e.g. Process Quality" value={form.name} onChange={set("name")} />
      </div>
      <CustomTextArea
        label="What this team is responsible for"
        placeholder="e.g. In-process checks on the machining lines."
        value={form.responsibility}
        onChange={set("responsibility")}
        rows={4}
      />
    </CustomDialog>
  );
};

/* ============================ Role ============================ */
export const RoleDialog = ({
  initial,
  capabilities,
  onClose,
  onConfirm,
  busy,
}: {
  initial?: Role;
  capabilities: { key: Capability; description: string }[];
  onClose: () => void;
  onConfirm: (data: { name: string; description: string; permissions: Capability[] }) => void;
  busy?: boolean;
}) => {
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [chosen, setChosen] = useState<Capability[]>(initial?.permissions ?? ["documents.view"]);
  const toggle = (key: Capability) => setChosen((c) => (c.includes(key) ? c.filter((x) => x !== key) : [...c, key]));

  return (
    <CustomDialog
      open
      onClose={onClose}
      title={initial ? `Edit ${initial.name}` : "Add a role"}
      subtitle="A role grants capabilities. Which records a person acts on is decided by the formats that name them."
      confirmText={busy ? "Saving…" : "Save"}
      confirmDisabled={busy || !name.trim() || chosen.length === 0}
      onConfirm={() => onConfirm({ name: name.trim(), description: description.trim(), permissions: chosen })}
    >
      <CustomTextField label="Role name" value={name} onChange={setName} placeholder="e.g. Line Inspector" />
      <CustomTextArea label="Description" optional value={description} onChange={setDescription} rows={2} />
      <div className="dialog-section">
        <div className="dialog-section-title">What it allows</div>
        {capabilities.map((c) => (
          <div key={c.key}>
            <FormControlLabel
              control={<Checkbox size="small" checked={chosen.includes(c.key)} onChange={() => toggle(c.key)} />}
              label={c.description}
            />
          </div>
        ))}
        <p style={{ fontSize: 11, color: "#92400e", margin: "6px 0 0" }}>
          Note: "Approval" also lets the holder file any record, and "Fill records" lets them fill any format (open
          decision D11 in INTEGRATION_PLAN.md).
        </p>
      </div>
    </CustomDialog>
  );
};

/* ============================ Department ============================ */
export const DepartmentDialog = ({ onClose, onConfirm, busy }: { onClose: () => void; onConfirm: (name: string) => void; busy?: boolean }) => {
  const [name, setName] = useState("");
  return (
    <CustomDialog
      open
      maxWidth="xs"
      onClose={onClose}
      title="Add a department"
      confirmText={busy ? "Adding…" : "Add"}
      confirmDisabled={busy || !name.trim()}
      onConfirm={() => onConfirm(name.trim())}
    >
      <CustomTextField label="Department name" value={name} onChange={setName} placeholder="e.g. Manufacturing" />
    </CustomDialog>
  );
};
