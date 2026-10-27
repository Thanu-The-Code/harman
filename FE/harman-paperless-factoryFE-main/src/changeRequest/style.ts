import type { SxProps, Theme } from "@mui/material/styles";

const TEAL = "#14b8a6";
const BORDER = "#e5e7eb";
const MUTED = "#6b7280";

export const changeRequestStyles: SxProps<Theme> = {
  fontFamily: '"Plus Jakarta Sans", "Inter", Roboto, sans-serif',
  background: "#fff",
  minHeight: "100vh",

  "& .page-body": { padding: "12px 8px 16px", display: "flex", flexDirection: "column", gap: "12px" },

  "& .change-panel": {
    background: "#fff",
    border: `1px solid ${BORDER}`,
    borderRadius: "8px",
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    height: "calc(100vh - 250px)",
    minHeight: 420,
  },
  "& .change-toolbar": {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: "16px",
    padding: "0 12px",
    flexWrap: "wrap",
  },
  "& .toolbar-actions": { display: "flex", gap: "10px", alignItems: "center", padding: "8px 0", flexWrap: "wrap" },
  "& .header-search": { width: 220, minWidth: 0, flexShrink: 1 },
  "& .change-grid": { flex: 1, minHeight: 0 },

  /* cell renderers */
  "& .action-cell": { display: "flex", alignItems: "center", justifyContent: "center", width: "100%" },
  "& .eye-btn": {
    border: `1px solid ${BORDER}`,
    borderRadius: "6px",
    color: MUTED,
    padding: "6px",
    background: "#fff",
    boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
    "&:hover": { color: "#14b8a6", borderColor: "#14b8a6", background: "#fff" },
  },
  "& .ag-center-header .ag-header-cell-label": { justifyContent: "center" },
};

export const changeDetailStyles: SxProps<Theme> = {
  fontFamily: '"Plus Jakarta Sans", "Inter", Roboto, sans-serif',
  background: "#fff",
  minHeight: "100vh",
  display: "flex",
  flexDirection: "column",

  "& .detail-content": {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: "14px",
    padding: "14px 16px",
  },

  /* change request card */
  "& .cr-body": { padding: "14px 16px" },
  "& .cr-label": { fontSize: 12, fontWeight: 600, color: "#111827", marginBottom: "8px" },
  "& .cr-reason": {
    padding: "12px 14px",
    background: "#f7f8fa",
    border: `1px solid ${BORDER}`,
    borderRadius: "8px",
    fontSize: 12,
    lineHeight: 1.6,
    color: "#374151",
  },
  "& .cr-footer": {
    display: "flex",
    justifyContent: "flex-end",
    alignItems: "center",
    gap: "10px",
    padding: "12px 16px",
    borderTop: `1px solid ${BORDER}`,
  },
  "& .decision-btn": {
    textTransform: "none",
    whiteSpace: "nowrap",
    fontSize: 12,
    fontWeight: 600,
    borderRadius: "6px",
    padding: "5px 18px",
    boxShadow: "none",
  },
  "& .not-approved-btn": {
    color: "#dc2626",
    background: "#fde8e8",
    border: "1px solid #f7c1c1",
    "&:hover": { background: "#fbd5d5" },
  },
  "& .approved-btn": {
    color: "#fff",
    background: TEAL,
    "&:hover": { background: "#0f9e8e", boxShadow: "none" },
  },

  /* sticky bottom bar */
  "& .bottom-bar": {
    position: "sticky",
    bottom: 0,
    display: "flex",
    justifyContent: "flex-end",
    gap: "10px",
    padding: "12px 24px",
    background: "#fff",
    borderTop: `1px solid ${BORDER}`,
  },
  "& .bar-btn": {
    textTransform: "none",
    fontSize: 13,
    fontWeight: 600,
    borderRadius: "6px",
    padding: "5px 22px",
    boxShadow: "none",
    color: TEAL,
    background: "#e6f7f5",
    border: "1px solid #b8ebe4",
    "&:hover": { background: "#d3f1ed" },
    "&.Mui-disabled": { color: "#9ca3af", background: "#f3f4f6", borderColor: BORDER },
  },
  "& .assign-btn": {
    color: "#fff",
    background: TEAL,
    border: `1px solid ${TEAL}`,
    "&:hover": { background: "#0f9e8e" },
  },
};