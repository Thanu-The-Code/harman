// The header's title for each section, matched by the longest path prefix
// ("/" itself only matches the dashboard).
export interface PageMeta {
  title: string;
  subtitle?: string;
  /** Shown before the title as a breadcrumb: "Template builder / Document create". */
  parent?: { title: string; path: string };
}

export const PAGE_META: Record<string, PageMeta> = {
  "/": { title: "Dashboard" },
  "/resources": { title: "Resources Library" },
  "/my-forms": { title: "My Documents" },
  "/doc-repo": { title: "Doc Repository" },
  "/builder": { title: "Template Builder" },
  "/builder-repo": { title: "Template Repository" },
  "/my-approvals": { title: "My Approvals", subtitle: "Review and act on items waiting for your approval." },
  "/request": { title: "Change Request" },
  "/change-request": { title: "Change Request" },
  "/people-teams": { title: "Roles & Permissions", subtitle: "Manage users, roles, and team structures." },
  "/activity-log": { title: "Activity Log", subtitle: "Track system activity and audit history." },
  "/notifications": { title: "Notification", subtitle: "Stay updated on important actions, changes, and system alerts." },
  "/settings": { title: "Settings", subtitle: "Manage your account preferences, notification, and system setting." },
};

export const DEFAULT_META = {
  title: "Paperless Factory",
  subtitle: "Quality records management",
};

/** "/builder-repo/x" → Template Repository; "/builder/12" → Template Builder; "/" → Dashboard. */
// the template designer ("/builder/new/build", "/builder/<id>/build")
const DESIGNER: PageMeta = { title: "Document create", parent: { title: "Template builder", path: "/builder" } };

export const metaFor = (pathname: string): PageMeta => {
  if (/^\/builder\/[^/]+\/build$/.test(pathname)) return DESIGNER;
  if (PAGE_META[pathname]) return PAGE_META[pathname];
  const match = Object.keys(PAGE_META)
    .filter((path) => path !== "/" && (pathname === path || pathname.startsWith(`${path}/`)))
    .sort((a, b) => b.length - a.length)[0];
  return match ? PAGE_META[match] : DEFAULT_META;
};
