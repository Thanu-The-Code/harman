// The backend stores UTC and reasons in IST (BE app/utils/ist.py). Every date
// the app shows goes through here so the whole UI reads in factory time.
const TIME_ZONE = "Asia/Kolkata";

const parse = (value?: string | null): Date | null => {
  if (!value) return null;
  // A bare "YYYY-MM-DD" is a calendar date, not midnight UTC.
  const date = /^\d{4}-\d{2}-\d{2}$/.test(value)
    ? new Date(`${value}T00:00:00+05:30`)
    : // timestamps without an offset are UTC on the server
      new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(value) ? value : `${value}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
};

/** "22 Oct 2026" */
export const formatDate = (value?: string | null, fallback = "—") => {
  const date = parse(value);
  return date
    ? date.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: TIME_ZONE })
    : fallback;
};

/** "22 Oct 2026, 14:05" */
export const formatDateTime = (value?: string | null, fallback = "—") => {
  const date = parse(value);
  return date
    ? date.toLocaleString("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
        timeZone: TIME_ZONE,
      })
    : fallback;
};

/** "5 min ago", "3 hours ago", then the date. */
export const formatRelative = (value?: string | null, now = Date.now()) => {
  const date = parse(value);
  if (!date) return "—";
  const minutes = Math.round((now - date.getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days} day${days === 1 ? "" : "s"} ago`;
  return formatDate(value);
};
