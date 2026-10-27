import { useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { NotificationSymbol } from "./NotificationPopUp";
import {
  BackButton,
  DetailActions,
  DetailCloseButton,
  DetailHeader,
  DetailValue,
  DetailsContent,
  FilterSelect,
  NotificationDetails,
  NotificationsContent,
  NotificationsPageLayout,
  NotificationsPageTitle,
  NotificationsSearch,
  NotificationsToolbar,
  NotificationsWorkspace,
  TypeBadge,
} from "./notificationsStyle";
import { ConstantLogo } from "../assets";
import { PageLoader } from "../base/feedback";
import {
  NOTIFICATION_TYPES,
  notificationLink,
  notificationLook,
  useMarkNotificationsReadMutation,
  useMyNotificationsQuery,
  type AppNotification,
} from "../api/notifications.api";
import { formatDateTime, formatRelative } from "../utils/date";

const DELIVERY: Record<string, string> = {
  sent: "Emailed",
  queued: "Email queued",
  failed: "Email failed",
  skipped: "In-app only (email not configured)",
};

const DAY = 24 * 60 * 60 * 1000;

/** Every process trigger addressed to the signed-in person. */
const NotificationsPage = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("All Types");
  const [timeFilter, setTimeFilter] = useState("All Time");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(true);
  // the moment the page opened: time filters are relative to it
  const [openedAt] = useState(() => Date.now());

  const { data, isLoading } = useMyNotificationsQuery({ limit: 200 });
  const [markRead] = useMarkNotificationsReadMutation();
  const { noNotification } = ConstantLogo;

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (data?.notifications ?? []).filter((n) => {
      const at = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(n.created_at) ? n.created_at : `${n.created_at}Z`).getTime();
      return (
        (!q || `${n.subject} ${n.body}`.toLowerCase().includes(q)) &&
        (typeFilter === "All Types" || notificationLook(n.kind).type === typeFilter) &&
        (timeFilter === "All Time" ||
          (timeFilter === "Today" && openedAt - at < DAY) ||
          (timeFilter === "Last 7 days" && openedAt - at < 7 * DAY) ||
          (timeFilter === "Unread" && !n.read))
      );
    });
  }, [data, search, typeFilter, timeFilter, openedAt]);

  const index = Math.max(0, filtered.findIndex((n) => n.id === selectedId));
  const selected: AppNotification | undefined = filtered[index];
  const from = (location.state as { from?: string } | null)?.from || "/";

  const select = (n: AppNotification) => {
    setSelectedId(n.id);
    setDetailsOpen(true);
    if (!n.read) markRead({ ids: [n.id] });
  };

  const link = selected ? notificationLink(selected) : null;

  return (
    <NotificationsPageLayout>
      <NotificationsPageTitle>
        <BackButton type="button" aria-label="Go back" onClick={() => navigate(from)}>
          ‹
        </BackButton>
        <div>
          <h1>Notification</h1>
          <p>
            Approval requests, N-OK flags, change requests and process alerts.
            {data?.unread ? ` ${data.unread} unread.` : ""}
          </p>
        </div>
        {!!data?.unread && (
          <button
            type="button"
            onClick={() => markRead({})}
            style={{ marginLeft: "auto", border: 0, background: "none", color: "#14b8a6", cursor: "pointer", fontWeight: 600 }}
          >
            Mark all as read
          </button>
        )}
      </NotificationsPageTitle>

      <NotificationsWorkspace $detailsOpen={detailsOpen && filtered.length > 0}>
        <NotificationsContent>
          <NotificationsToolbar>
            <NotificationsSearch
              type="search"
              aria-label="Search notifications"
              placeholder="Search notification"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <FilterSelect aria-label="Filter by notification type" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
              <option>All Types</option>
              {NOTIFICATION_TYPES.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </FilterSelect>
            <FilterSelect aria-label="Filter by time" value={timeFilter} onChange={(e) => setTimeFilter(e.target.value)}>
              <option>All Time</option>
              <option>Unread</option>
              <option>Today</option>
              <option>Last 7 days</option>
            </FilterSelect>
          </NotificationsToolbar>

          {isLoading ? (
            <PageLoader />
          ) : filtered.length === 0 ? (
            <div className="empty-notifications" role="status">
              <img src={noNotification} alt="" />
              <h2>No notification yet</h2>
              <p>
                You’ll see notification here for approval requests, N-OK flags,
                <br />
                change requests and important process alerts.
              </p>
            </div>
          ) : (
            <div className="notification-list">
              {filtered.map((n, i) => {
                const look = notificationLook(n.kind);
                return (
                  <button
                    type="button"
                    className={`notification-row${i === index ? " selected" : ""}`}
                    key={n.id}
                    onClick={() => select(n)}
                    aria-pressed={i === index}
                  >
                    <span className="notification-icon">
                      <NotificationSymbol icon={look.icon} />
                      {!n.read && <span className="unread-dot" />}
                    </span>
                    <span className="notification-copy">
                      <strong>{n.subject}</strong>
                      <span>{n.body.split("\n")[0]}</span>
                    </span>
                    <time dateTime={n.created_at}>{formatRelative(n.created_at)}</time>
                    <span className="chevron" aria-hidden="true">
                      ›
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </NotificationsContent>

        {detailsOpen && filtered.length > 0 && selected && (
          <NotificationDetails>
            <DetailHeader>
              <h2>Details</h2>
              <DetailCloseButton type="button" aria-label="Close notification details" onClick={() => setDetailsOpen(false)}>
                ×
              </DetailCloseButton>
            </DetailHeader>

            <DetailsContent>
              <div className="selected-notification">
                <span className="notification-icon">
                  <NotificationSymbol icon={notificationLook(selected.kind).icon} />
                </span>
                <div>
                  <strong>{selected.subject}</strong>
                  <time dateTime={selected.created_at}>{formatDateTime(selected.created_at)}</time>
                </div>
              </div>

              <p className="description" style={{ whiteSpace: "pre-wrap" }}>
                {selected.body}
              </p>

              <dl>
                <dt>Type</dt>
                <dd>
                  <TypeBadge>{notificationLook(selected.kind).type}</TypeBadge>
                </dd>
                <dt>Delivery</dt>
                <DetailValue>{DELIVERY[selected.status] ?? selected.status}</DetailValue>
                <dt>Date &amp; Time</dt>
                <DetailValue>{formatDateTime(selected.created_at)}</DetailValue>
              </dl>
              {link && (
                <button
                  type="button"
                  onClick={() => navigate(link)}
                  style={{
                    marginTop: 12,
                    border: 0,
                    borderRadius: 6,
                    padding: "8px 16px",
                    background: "#14b8a6",
                    color: "#fff",
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  Open
                </button>
              )}
            </DetailsContent>

            <DetailActions>
              <button type="button" disabled={index === 0} onClick={() => select(filtered[index - 1])}>
                ‹ <span>Previous</span>
              </button>
              <button type="button" disabled={index >= filtered.length - 1} onClick={() => select(filtered[index + 1])}>
                <span>Next</span> ›
              </button>
            </DetailActions>
          </NotificationDetails>
        )}
      </NotificationsWorkspace>
    </NotificationsPageLayout>
  );
};

export default NotificationsPage;
