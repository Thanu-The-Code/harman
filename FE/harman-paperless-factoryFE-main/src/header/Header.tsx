import { useEffect, useRef, useState } from "react";
import {
  Avatar,
  HeaderContainer,
  HeaderLeft,
  HeaderRight,
  IconButton,
  NotificationControl,
  UserInfo,
  UserProfile,
} from "./style";
import { useLocation, useNavigate } from "react-router-dom";
import { metaFor } from "../constants/pageMeta";
import NotificationPopUp from "./NotificationPopUp";
import { roleLabel, useLogoutMutation, useMeQuery } from "../api/auth.api";
import { api } from "../api/baseApi";
import { clearSession, LOGIN_PATH } from "../api/session";
import { useAppDispatch } from "../redux/store";
import {
  NOTIFICATION_POLL_MS,
  notificationLink,
  useMarkNotificationsReadMutation,
  useMyNotificationsQuery,
  type AppNotification,
} from "../api/notifications.api";

const Header = () => {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const dispatch = useAppDispatch();
  const { data: me } = useMeQuery();
  const [logout] = useLogoutMutation();
  // the unread count, kept fresh by polling (and by every action that changes it)
  const { data: unread } = useMyNotificationsQuery(
    { unread_only: true, limit: 1 },
    { pollingInterval: NOTIFICATION_POLL_MS, refetchOnFocus: true },
  );
  const [markRead] = useMarkNotificationsReadMutation();
  const [notificationsOpen, setNotificationsOpen] = useState(false);

  const displayName = me?.full_name || me?.username || "";

  const handleLogout = async () => {
    try {
      await logout().unwrap(); // clears the session cookie
    } catch {
      /* signing out locally is enough if the server is unreachable */
    }
    clearSession();
    dispatch(api.util.resetApiState());
    navigate(LOGIN_PATH, { replace: true });
  };
  const notificationControlRef = useRef<HTMLDivElement>(null);

  const meta = metaFor(pathname);

  useEffect(() => {
    if (!notificationsOpen) return;

    const handlePointerDown = (event: PointerEvent) => {
      if (!notificationControlRef.current?.contains(event.target as Node)) {
        setNotificationsOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setNotificationsOpen(false);
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [notificationsOpen]);

  return (
    <HeaderContainer>
      <HeaderLeft>
        <h1>
          {meta.parent && (
            <>
              <button type="button" className="crumb" onClick={() => navigate(meta.parent!.path)}>
                {meta.parent.title}
              </button>
              <span className="crumb-sep"> / </span>
            </>
          )}
          {meta.title}
        </h1>
        {/* <p>{meta.subtitle}</p> */}
      </HeaderLeft>

      <HeaderRight>
        <NotificationControl ref={notificationControlRef}>
          <IconButton
            type="button"
            aria-label="Notifications"
            aria-haspopup="dialog"
            aria-expanded={notificationsOpen}
            aria-controls="notification-panel"
            onClick={() => setNotificationsOpen((open) => !open)}
          >
            <svg
              width="20"
              height="20"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              viewBox="0 0 24 24"
            >
              <path d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
            </svg>
            {!!unread?.unread && <span className="badge">{unread.unread > 99 ? "99+" : unread.unread}</span>}
          </IconButton>
          {notificationsOpen && (
            <NotificationPopUp
              onViewAll={() => {
                setNotificationsOpen(false);
                navigate("/notifications", { state: { from: pathname } });
              }}
              onOpen={(n: AppNotification) => {
                setNotificationsOpen(false);
                if (!n.read) markRead({ ids: [n.id] });
                navigate(notificationLink(n) ?? "/notifications", { state: { from: pathname } });
              }}
            />
          )}
        </NotificationControl>

        <IconButton
          type="button"
          aria-label="Settings"
          onClick={() => navigate("/settings")}
        >
          <svg
            width="20"
            height="20"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            viewBox="0 0 24 24"
          >
            <path d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path>
            <path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
          </svg>
        </IconButton>

        <IconButton
          type="button"
          aria-label="Log out"
          title="Log out"
          onClick={handleLogout}
        >
          <svg
            width="20"
            height="20"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path d="M10 17l5-5-5-5m5 5H3" />
            <path d="M12 3h6a2 2 0 012 2v14a2 2 0 01-2 2h-6" />
          </svg>
        </IconButton>

        <UserProfile>
          <Avatar>{displayName.charAt(0).toUpperCase()}</Avatar>
          <UserInfo>
            <span className="name">{displayName}</span>
            <span className="role">{roleLabel(me)}</span>
          </UserInfo>
        </UserProfile>
      </HeaderRight>
    </HeaderContainer>
  );
};

export default Header;
