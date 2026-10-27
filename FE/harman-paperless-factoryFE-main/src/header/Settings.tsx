import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "react-toastify";
import CustomDialog from "../base/dialog/CustomDialog";
import CustomTextField from "../base/dialog/CustomTextField";
import { roleLabel, useChangePasswordMutation, useMeQuery } from "../api/auth.api";
import { getApiErrorMessage } from "../api/errors";
import { setToken } from "../api/session";
import {
  BackButton,
  NotificationSetting,
  ProfileFields,
  ProfileSection,
  SettingsCard,
  SettingsPageLayout,
  SettingsPageTitle,
} from "./settingsStyle";

// What the process tells people, in the bell and by email (when a mail server is set up).
// These are the chart's triggers, addressed by responsibility: they are not switched off.
const notificationSettings = [
  {
    id: "approvals",
    title: "Approvals waiting on you",
    description: "A record or template reaches a step that is yours: approve, sign, agree or decide.",
    icon: "approval",
  },
  {
    id: "documents",
    title: "Your records",
    description: "A record you fill is returned for correction, sent back, approved or filed.",
    icon: "document",
  },
  {
    id: "changes",
    title: "Change requests",
    description: "A change request you raised, or one waiting on you, is decided or carried out.",
    icon: "database",
  },
  {
    id: "team",
    title: "Out of specification",
    description: "A record is submitted with N-OK readings, or a check due this period has not been started.",
    icon: "team",
  },
  {
    id: "system",
    title: "Templates",
    description: "A template you sent for approval is released or returned for changes.",
    icon: "bell",
  },
] as const;

const SettingsIcon = ({ name }: { name: string }) => {
  const paths: Record<string, React.ReactNode> = {
    document: <path d="M7 3h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z M14 3v5h5" />,
    approval: <><path d="M12 3v3m6.36-.36-2.12 2.12M21 12h-3M5.64 5.64l2.12 2.12M12 8a4 4 0 1 0 4 4" /><path d="m10 13 1.5 1.5L14 12" /></>,
    database: <><ellipse cx="12" cy="5" rx="7" ry="3" /><path d="M5 5v14c0 1.66 3.13 3 7 3s7-1.34 7-3V5M5 12c0 1.66 3.13 3 7 3s7-1.34 7-3" /></>,
    team: <><circle cx="9" cy="8" r="3" /><path d="M3 19v-1a6 6 0 0 1 12 0v1M16 5a3 3 0 0 1 0 6m2 3a5 5 0 0 1 3 4v1" /></>,
    bell: <><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9m-8 12a2 2 0 0 0 4 0" /></>,
  };

  return (
    <svg
      aria-hidden="true"
      width="17"
      height="17"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[name]}
    </svg>
  );
};


const ChangePasswordDialog = ({ onClose }: { onClose: () => void }) => {
  const [changePassword, { isLoading }] = useChangePasswordMutation();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const problem = next && next.length < 8 ? "At least 8 characters." : confirm && next !== confirm ? "The two passwords differ." : "";

  return (
    <CustomDialog
      open
      maxWidth="xs"
      onClose={onClose}
      title="Change password"
      confirmText={isLoading ? "Saving…" : "Change password"}
      confirmDisabled={isLoading || !current || next.length < 8 || next !== confirm}
      onConfirm={async () => {
        try {
          const res = await changePassword({ current_password: current, new_password: next }).unwrap();
          if (res.access_token) setToken(res.access_token); // other sign-ins were ended
          toast.success("Password changed.");
          onClose();
        } catch (error) {
          toast.error(getApiErrorMessage(error, "Could not change the password."));
        }
      }}
    >
      <CustomTextField label="Current password" type="password" value={current} onChange={setCurrent} />
      <CustomTextField label="New password" type="password" value={next} onChange={setNext} helperText="At least 8 characters, mixing three of: lower-case, upper-case, digits, symbols." />
      <CustomTextField label="Confirm new password" type="password" value={confirm} onChange={setConfirm} helperText={problem} />
    </CustomDialog>
  );
};

const SettingsPage = () => {
  const navigate = useNavigate();
  const { data: me } = useMeQuery();
  const [passwordOpen, setPasswordOpen] = useState(false);

  const name = me?.full_name || me?.username || "";
  const authority = me
    ? [me.can_approve ? "May approve" : "", me.can_sign ? "May sign" : ""].filter(Boolean).join(" · ") || "View / fill"
    : "";

  return (
    <SettingsPageLayout>
      <SettingsPageTitle>
        <BackButton type="button" aria-label="Go back" onClick={() => navigate(-1)}>
          <svg
            aria-hidden="true"
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="m15 18-6-6 6-6" />
          </svg>
        </BackButton>
        <div>
          <h1>Settings</h1>
          <p>Your account, password and preferences on this device.</p>
        </div>
      </SettingsPageTitle>

      <SettingsCard>
        <header className="card-header">
          <div>
            <h2>Profile Setting</h2>
            <p>Your details are managed by an administrator in Roles &amp; Permissions.</p>
          </div>
          <button className="change-password" type="button" onClick={() => setPasswordOpen(true)}>
            Change Password
          </button>
        </header>

        <ProfileSection>
          <div className="profile-summary">
            <div className="avatar">{name.charAt(0).toUpperCase()}</div>
            <div className="identity">
              <strong>{name}</strong>
              <span>{roleLabel(me)}</span>
              <span className="status">{me?.is_active ? "Active" : "Inactive"}</span>
            </div>
          </div>

          <ProfileFields>
            <label>
              <span>Full Name</span>
              <input value={me?.full_name ?? ""} readOnly />
            </label>
            <label>
              <span>Username</span>
              <input value={me?.username ?? ""} readOnly />
            </label>
            <label>
              <span>Email</span>
              <input value={me?.email ?? ""} readOnly />
            </label>
            <label>
              <span>Department</span>
              <input value={me?.department ?? "—"} readOnly />
            </label>
            <label>
              <span>Job title</span>
              <input value={me?.job_title ?? "—"} readOnly />
            </label>
            <label>
              <span>Authority</span>
              <input value={authority} readOnly />
            </label>
          </ProfileFields>
        </ProfileSection>
      </SettingsCard>

      <SettingsCard>
        <header className="card-header">
          <div>
            <h2>Notification</h2>
            <p>What you are told, in the bell and by email to your work address. They follow your responsibilities.</p>
          </div>
        </header>
        <div>
          {notificationSettings.map((setting) => (
            <NotificationSetting key={setting.id}>
              <span className="setting-icon">
                <SettingsIcon name={setting.icon} />
              </span>
              <span className="setting-copy">
                <strong>{setting.title}</strong>
                <small>{setting.description}</small>
              </span>
            </NotificationSetting>
          ))}
        </div>
      </SettingsCard>

      {passwordOpen && <ChangePasswordDialog onClose={() => setPasswordOpen(false)} />}
    </SettingsPageLayout>
  );
};

export default SettingsPage;
