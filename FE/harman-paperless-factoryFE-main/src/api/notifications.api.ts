import { api } from "./baseApi";

/* In-app notifications: every process trigger is stored here, emailed or not
 * (`/api/records/notifications`). */

export interface AppNotification {
  id: string;
  kind: string;
  subject: string;
  body: string;
  related_type: "record" | "format" | "change_request" | "record_change_request" | "corrective_action" | string | null;
  related_id: string | null;
  status: "queued" | "sent" | "failed" | "skipped";
  read: boolean;
  created_at: string;
  sent_at: string | null;
}

/** How often the bell asks for news. */
export const NOTIFICATION_POLL_MS = 60_000;

export const notificationsApi = api.injectEndpoints({
  endpoints: (build) => ({
    myNotifications: build.query<{ notifications: AppNotification[]; unread: number }, { unread_only?: boolean; limit?: number }>({
      query: (params) => ({ url: "api/records/notifications/mine", params }),
      providesTags: ["Notifications"],
    }),
    markNotificationsRead: build.mutation<{ marked: number; unread: number }, { ids?: string[] }>({
      query: (data) => ({ url: "api/records/notifications/read", method: "POST", data }),
      invalidatesTags: ["Notifications"],
    }),
  }),
});

export const { useMyNotificationsQuery, useMarkNotificationsReadMutation } = notificationsApi;

export type NotificationTone = "blue" | "red" | "orange" | "green";

export interface NotificationLook {
  type: string; // the filter group
  tone: NotificationTone;
  icon: "document" | "change" | "checklist";
}

/** Group, colour and icon for a notification kind. */
export const notificationLook = (kind: string): NotificationLook => {
  if (["record.nok_flagged", "record.reverify", "inspection.failed"].includes(kind))
    return { type: "Attention", tone: "red", icon: "checklist" };
  if (kind.startsWith("record.") || kind === "inspection.completed")
    return { type: "Approval", tone: kind === "record.stored" ? "green" : "blue", icon: "document" };
  if (kind.startsWith("dcr.") || kind.startsWith("record_change_request.")) return { type: "Change Request", tone: "orange", icon: "change" };
  if (kind.startsWith("format.")) return { type: "Template", tone: "blue", icon: "document" };
  if (kind.startsWith("action.")) return { type: "Corrective Action", tone: "orange", icon: "checklist" };
  if (kind === "inspection.pending") return { type: "Due", tone: "orange", icon: "checklist" };
  return { type: "System", tone: "blue", icon: "document" };
};

export const NOTIFICATION_TYPES = ["Approval", "Attention", "Change Request", "Template", "Due", "Corrective Action", "System"];

const ACTION_KINDS = new Set(["record.submitted", "record.po_approved", "record.cft_review", "record.reverify", "record.nok_flagged"]);

/** The screen a notification is about, if there is one. */
export const notificationLink = (n: AppNotification): string | null => {
  const id = n.related_id;
  if (!id) return null;
  switch (n.related_type) {
    case "record":
      return ACTION_KINDS.has(n.kind) ? `/my-approvals/${id}` : `/my-forms/${id}?tab=track`;
    case "format":
      // a missed period is "format_id:period"; the format is filled from Resources
      return id.includes(":") ? `/resources?format=${id.split(":")[0]}` : `/builder/${id}`;
    case "change_request":
      return `/change-request/dcr/${id}`;
    case "record_change_request":
      return `/change-request/rcr/${id}`;
    default:
      return null;
  }
};
