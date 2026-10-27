import type { SxProps, Theme } from "@mui/material/styles";

const TEAL = "#0ebbb1";
const BORDER = "#e5eaf0";
const MUTED = "#6b7280";

export const docRepositoryStyles: SxProps<Theme> = {
  minHeight: "100vh",
  background: "#fff",
  color: "#1f2937",
  fontFamily: '"Plus Jakarta Sans", "Inter", Roboto, sans-serif',

  "& .page-body": { padding: "12px 16px 18px" },
  "& .header-search": { width: 300, minWidth: 0, flexShrink: 1 },

  "& .repository-layout": {
    display: "grid",
    gridTemplateColumns: "250px minmax(0, 1fr)",
    gap: "12px",
    // the app header and this page's header take ~165px: the panel ends on screen, pagination included
    height: "calc(100vh - 170px)",
    minHeight: 420,
    "& > *": { minWidth: 0 },
    "@media (max-width: 760px)": {
      gridTemplateColumns: "1fr",
      height: "auto",
      "& .custom-folder-tree": { maxHeight: 360 },
      "& .documents-panel": { minHeight: 520 },
    },
  },
  "& .documents-panel": {
    background: "#fff",
    border: `1px solid ${BORDER}`,
    borderRadius: "8px",
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    minHeight: 0,
  },
  "& .documents-heading": {
    minHeight: 54,
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: "12px",
    padding: "8px 12px",
    borderBottom: `1px solid ${BORDER}`,
    "& h2": { margin: 0, fontSize: 16, lineHeight: 1.4, fontWeight: 700 },
    "& p": { margin: "2px 0 0", color: "#9A9A9A", fontSize: 10, lineHeight: 1.4 },
  },
  "& .date-filter": {
    width: 168,
    flexShrink: 0,
    "& .MuiInputBase-root": { height: 34, fontSize: 11, borderRadius: "6px" },
    "& .MuiInputBase-input": { padding: "7px 8px" },
    "& .MuiInputAdornment-root": { marginRight: "6px", color: MUTED },
    "& fieldset": { borderColor: BORDER },
  },

  "& .documents-table-wrap": { flex: 1, minHeight: 0, overflow: "auto" },
  "& .documents-table": {
    width: "100%",
    borderCollapse: "collapse",
    "& th": {
      position: "sticky",
      top: 0,
      zIndex: 1,
      textAlign: "left",
      background: "#f8fafc",
      color: "#0F172B",
      fontSize: 12,
      fontWeight: 500,
      whiteSpace: "nowrap",
      padding: "9px 10px",
      borderBottom: `1px solid ${BORDER}`,
    },
    "& td": {
      padding: "6px 10px",
      height: 38,
      boxSizing: "border-box",
      borderBottom: `1px solid ${BORDER}`,
      fontSize: 12,
      whiteSpace: "nowrap",
    },
    "& tbody tr": { cursor: "pointer" },
    "& tbody tr:hover": { background: "#f8fafc" },
    "& tbody tr.selected": {
      background: "#e6f7f5",
      boxShadow: `inset 3px 0 0 ${TEAL}`,
    },
  },
  "& .action-column": { width: 56, textAlign: "center !important" },
  // a long form title wraps instead of pushing the Open button off the table
  "& .documents-table td.record-cell": { whiteSpace: "normal", minWidth: 220, lineHeight: 1.35 },
  "& .file-action": {
    width: 26,
    height: 26,
    padding: "3px",
    border: `1px solid ${BORDER}`,
    borderRadius: "5px",
    color: "#9ca3af",
    background: "#fff",
    "&:hover": { color: TEAL, borderColor: TEAL },
    "& .MuiSvgIcon-root": { fontSize: 15 },
  },
  "& .empty-table": {
    height: 100,
    textAlign: "center",
    color: MUTED,
    whiteSpace: "normal !important",
  },
};
