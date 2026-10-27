import type { SxProps, Theme } from "@mui/material/styles";

const TEAL = "#0ebbb1";
const BORDER = "#e5e7eb";

export const builderStyles: SxProps<Theme> = {
  display: "flex",
  flexDirection: "column",
  gap: "14px",

  "& .builder-panel": {
    background: "#fff",
    border: `1px solid ${BORDER}`,
    borderRadius: "8px",
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    height: "calc(100vh - 300px)",
    minHeight: 420,
  },
  "& .builder-toolbar": {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: "16px",
    padding: "0 12px",
    flexWrap: "wrap",
  },
  "& .header-search": {
    width: 260,
    minWidth: 0,
    flexShrink: 1,
    padding: "8px 0",
  },
  "& .builder-grid": { flex: 1, minHeight: 0 },

  /* selected row: light teal + teal bar on the left */
  "& .ag-row-selected": { "--ag-selected-row-background-color": "#e6f7f5" },
  "& .ag-row-selected .ag-cell[col-id='name']": {
    boxShadow: `inset 3px 0 0 ${TEAL}`,
  },
  "& .ag-row-selected .eye-btn": { color: TEAL, borderColor: TEAL },

  /* cell renderer */
  "& .action-cell": {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width: "100%",
  },
  "& .eye-btn": {
    border: `1px solid ${BORDER}`,
    borderRadius: "6px",
    color: "#6b7280",
    padding: "6px",
    background: "#fff",
    boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
    "&:hover": { color: TEAL, borderColor: TEAL, background: "#fff" },
  },
  "& .ag-center-header .ag-header-cell-label": { justifyContent: "center" },
};

export const builderTemplateDetailStyles: SxProps<Theme> = {
  display: "flex",
  flex: 1,
  flexDirection: "column",
  minHeight: "100%",
  "& .builder-detail-header": { padding: "8px 14px", minHeight: 52 },
  "& .back-btn": { width: 30, height: 30, borderRadius: "6px" },
  "& .page-title": { fontSize: 17 },
  "& .page-subtitle": { fontSize: 12 },
  "& .review-content": { gap: "12px", padding: "12px 14px" },
  "& .review-col": { gap: "10px" },
  "& .info-card-head": { padding: "10px 12px", fontSize: 14, fontWeight: 600 },
  "& .summary-grid": { gap: "0 14px" },
  "& .summary-row": {
    gridTemplateColumns: "96px minmax(0, 1fr)",
    padding: "7px 0",
    fontSize: 12,
  },

//   "& .summary-label": { fontSize: 12},

  "& .detail-table": { margin: "10px 12px" },
  "& .detail-row": { fontSize: 11 },
  "& .detail-label, & .detail-value": { padding: "14px 12px", borderRadius: "6px"},
  "& .doc-head": { padding: "8px 10px 4px" },
  "& .doc-title": { fontSize: 11 },
  "& .open-btn": { fontSize: 12, padding: "3px 8px" },
  "& .doc-meta": { padding: "0 10px 8px", fontSize: 10 },
  "& .doc-preview": { margin: "0 10px 10px", height: 230 },
  "& .doc-page": { maxWidth: 345, padding: "18px 20px" },
  "& .doc-heading": { fontSize: 18 },
  "& .approval-timeline": { padding: "10px 12px" },
  "& .timeline-item": {
    gridTemplateColumns: "16px 52px minmax(0, 1fr)",
    gap: "6px",
    marginBottom: "8px",
  },
  "& .step-card": { padding: "8px 10px" },
  "& .step-title": { fontSize: 12 },
  "& .step-role": { fontSize: 11 },
  "& .step-meta": { fontSize: 10, marginTop: "8px" },
  "& .builder-detail-actions": {
    justifyContent: "flex-end",
    padding: "10px 24px",
    minHeight: 54,
    boxShadow: "0 -2px 8px rgba(15, 23, 42, 0.08)",
    "& .builder-delete-btn": {
      color: "#ef4444",
      background: "#fde8e8",
      border: "1px solid #f7c1c1",
      "&:hover": { background: "#fbd5d5" },
    },
    "& .builder-edit-btn": {
      minWidth: 76,
      color: "#fff",
      background: "#14b8a6",
      "&:hover": { background: "#0f9e8e", boxShadow: "none" },
    },
  },
  "@media (max-width: 900px)": {
    "& .summary-grid": { gridTemplateColumns: "1fr" },
    "& .review-content": { padding: "10px" },
  },
};
