import { Navigate, useSearchParams } from "react-router-dom";

/*
 * Links the backend writes into emails and notifications
 * (notification_service, capa_service, inspection_report, change_request_service),
 * sent on to the screens that now show those things.
 */

/** `/track?record=<id>` → the record's Track status. */
export const TrackRedirect = () => {
  const [params] = useSearchParams();
  const id = params.get("record");
  return <Navigate to={id ? `/my-forms/${id}?tab=track` : "/my-forms"} replace />;
};

/** `/records/new?format=<id>` → Resources, with that format selected to be filled. */
export const NewRecordRedirect = () => {
  const [params] = useSearchParams();
  const id = params.get("format");
  return <Navigate to={id ? `/resources?format=${id}` : "/resources"} replace />;
};

/** `/change-requests?id=<id>` (change-request emails sent before the link was fixed) → that request. */
export const ChangeRequestRedirect = () => {
  const [params] = useSearchParams();
  const id = params.get("id");
  return <Navigate to={id ? `/change-request/dcr/${id}` : "/request"} replace />;
};
