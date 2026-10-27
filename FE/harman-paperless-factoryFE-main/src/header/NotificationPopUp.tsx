import { notificationLook, useMyNotificationsQuery, type AppNotification } from "../api/notifications.api";
import { formatRelative } from "../utils/date";
import {
  NotificationChevron,
  NotificationCopy,
  NotificationIcon,
  NotificationItem,
  NotificationPanel,
  NotificationPanelHeader,
  NotificationTime,
} from "./style";

export const NotificationSymbol = ({ icon }: { icon: string }) => {
  if (icon === "change") {
    return (
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M7 7h10l-2.5-2.5M17 17H7l2.5 2.5" />
        <path d="M18.5 9.5a7 7 0 0 1 0 5M5.5 14.5a7 7 0 0 1 0-5" />
        <path d="M17 7a7 7 0 0 1 2 2.5M7 17a7 7 0 0 1-2-2.5" />
      </svg>
    );
  }

  if (icon === "checklist") {
    return (
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="m5 7 1.5 1.5L9 6M11 7h8M5 14l1.5 1.5L9 13m2 1h8" />
        <path d="M19 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2Z" />
      </svg>
    );
  }

  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M7 3h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" />
      <path d="M14 3v5h5M9 13h6m-6 4h4" />
    </svg>
  );
};

const NotificationPopUp = ({ onViewAll, onOpen }: { onViewAll: () => void; onOpen: (n: AppNotification) => void }) => {
  const { data, isLoading } = useMyNotificationsQuery({ limit: 5 });
  const items = data?.notifications ?? [];

  return (
    <NotificationPanel id="notification-panel" role="dialog" aria-label="Notifications">
      <NotificationPanelHeader>
        <h2>Notification{data?.unread ? ` (${data.unread} new)` : ""}</h2>
        <button type="button" onClick={onViewAll}>
          View all
        </button>
      </NotificationPanelHeader>

      {isLoading && <p style={{ padding: "16px 20px", margin: 0, fontSize: 13 }}>Loading…</p>}
      {!isLoading && items.length === 0 && (
        <p style={{ padding: "16px 20px", margin: 0, fontSize: 13, color: "#6b7280" }}>Nothing new.</p>
      )}
      {items.map((n) => {
        const look = notificationLook(n.kind);
        return (
          <NotificationItem
            key={n.id}
            role="button"
            tabIndex={0}
            style={{ cursor: "pointer" }}
            onClick={() => onOpen(n)}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onOpen(n)}
          >
            <NotificationIcon $tone={look.tone}>
              <NotificationSymbol icon={look.icon} />
              {!n.read && <span className="unread" />}
            </NotificationIcon>
            <NotificationCopy data-read={n.read}>
              <h3>{n.subject}</h3>
              <p>{n.body.split("\n")[0]}</p>
            </NotificationCopy>
            <NotificationTime dateTime={n.created_at}>{formatRelative(n.created_at)}</NotificationTime>
            <NotificationChevron aria-hidden="true">›</NotificationChevron>
          </NotificationItem>
        );
      })}
    </NotificationPanel>
  );
};

export default NotificationPopUp;
