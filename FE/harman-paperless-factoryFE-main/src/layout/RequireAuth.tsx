import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useMeQuery } from "../api/auth.api";
import { getToken, LOGIN_PATH } from "../api/session";
import { ErrorState, PageLoader } from "../base/feedback";

/**
 * Gate for every signed-in screen. No token → login (remembering where the
 * person was going). A rejected token is a 401, which the axios interceptor
 * turns into a redirect to the login page.
 */
const RequireAuth = () => {
  const location = useLocation();
  const token = getToken();
  const { data: me, isLoading, isError, error, refetch } = useMeQuery(undefined, { skip: !token });

  if (!token) {
    return <Navigate to={LOGIN_PATH} replace state={{ from: `${location.pathname}${location.search}` }} />;
  }
  if (isLoading) return <PageLoader fullScreen label="Signing you in…" />;
  if (isError || !me) {
    const message = (error && "message" in error && error.message) || "Could not load your account.";
    return <ErrorState message={message} onRetry={refetch} />;
  }
  return <Outlet />;
};

/** Screens only an administrator may open (template authoring, people). */
export const RequireAdmin = () => {
  const { data: me } = useMeQuery();
  // say why, rather than dropping the person on the dashboard without a word
  if (!me?.is_admin) return <ErrorState message="This screen is for administrators. Ask an administrator if you need something changed here." />;
  return <Outlet />;
};

export default RequireAuth;
