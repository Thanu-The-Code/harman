import type { SxProps, Theme } from "@mui/material/styles";

const BORDER = "#e5e7eb";

export const activityLogStyles: SxProps<Theme> = {
  fontFamily: '"Plus Jakarta Sans", "Inter", Roboto, sans-serif',
  background: "#fff",
  minHeight: "100vh",

  "& .page-body": { padding: "12px 12px 16px" },
  "& .log-panel": {
    background: "#fff",
    border: `1px solid ${BORDER}`,
    borderRadius: "8px",
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    height: "calc(100vh - 110px)",
    minHeight: 420,
  },
  "& .log-toolbar": {
    display: "flex",
    justifyContent: "flex-end",
    alignItems: "center",
    gap: "10px",
    padding: "12px",
    borderBottom: `1px solid ${BORDER}`,
    flexWrap: "wrap",
  },
  "& .header-search": { width: 240, minWidth: 0, flexShrink: 1 },
  "& .log-grid": { flex: 1, minHeight: 0 },

  /* cell renderers */
  "& .datetime-cell": { lineHeight: 1.4, padding: "6px 0" },
  "& .datetime-date": { fontSize: 12, color: "#111827" },
  "& .datetime-time": { fontSize: 11, color: "#6b7280" },
  "& .user-cell": { display: "flex", alignItems: "center", gap: "6px", fontSize: 12, "& svg": { fontSize: 16, color: "#4b5563" } },
};