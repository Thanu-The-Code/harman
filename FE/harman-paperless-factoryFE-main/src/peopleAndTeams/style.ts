import type { SxProps, Theme } from "@mui/material/styles";

const TEAL = "#14b8a6";
const BORDER = "#e5e7eb";
const MUTED = "#6b7280";

export const peopleTeamsStyles: SxProps<Theme> = {
  fontFamily: '"Plus Jakarta Sans", "Inter", Roboto, sans-serif',
  background: "#fff",
  minHeight: "100vh",

  /* header buttons */
  "& .header-btn": {
    textTransform: "none",
    fontSize: 13,
    fontWeight: 600,
    borderRadius: "6px",
    padding: "6px 16px",
    boxShadow: "none",
    whiteSpace: "nowrap",
  },
  "& .new-team-btn": {
    color: TEAL,
    background: "#e6f7f5",
    border: "1px solid #b8ebe4",
    "&:hover": { background: "#d3f1ed" },
  },
  "& .add-person-btn": {
    color: "#fff",
    background: TEAL,
    "&:hover": { background: "#0f9e8e", boxShadow: "none" },
  },

  "& .page-body": { padding: "0 16px 16px" },
  "& .tabs-bar": { borderBottom: `1px solid ${BORDER}`, marginBottom: "16px" },

  /* teams grid */
  "& .teams-grid": {
    display: "grid",
    gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
    gap: "14px",
    paddingBottom: "18px",
    marginBottom: "16px",
    borderBottom: `1px solid ${BORDER}`,
    "@media (max-width: 1100px)": { gridTemplateColumns: "repeat(2, minmax(0, 1fr))" },
    "@media (max-width: 600px)": { gridTemplateColumns: "1fr" },
  },
  "& .team-card": {
    border: `1px solid ${BORDER}`,
    borderRadius: "10px",
    padding: "14px",
    background: "#fff",
    boxShadow: "0 2px 6px rgba(15, 23, 42, 0.05)",
    display: "flex",
    flexDirection: "column",
    gap: "14px",
  },
  "& .team-card-top": { display: "flex", alignItems: "center", gap: "12px" },
  "& .team-name": { fontSize: 14, fontWeight: 600, color: "#111827" },
  "& .team-members": { fontSize: 11, color: MUTED, marginTop: "2px" },
  "& .team-card-bottom": { display: "flex", alignItems: "center", justifyContent: "space-between" },
  "& .open-team-btn": {
    border: `1px solid ${BORDER}`,
    borderRadius: "6px",
    color: "#111827",
    background: "#fff",
    "&:hover": { borderColor: TEAL, color: TEAL, background: "#fff" },
  },

  /* people section */
  "& .people-head": {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: "12px",
    flexWrap: "wrap",
    marginBottom: "12px",
  },
  "& .people-title": { fontSize: 16, fontWeight: 600, margin: 0, color: "#111827" },
  "& .people-filters": { display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" },
  "& .header-search": { width: 280, minWidth: 0, flexShrink: 1 },
  "& .people-grid": {
    height: 440,
    border: `1px solid ${BORDER}`,
    borderRadius: "8px",
    overflow: "hidden",
  },

  /* cell renderers */
  "& .person-cell": { display: "flex", alignItems: "center", gap: "10px", padding: "6px 0" },
  "& .person-name": { fontSize: 12, fontWeight: 600, color: "#111827", lineHeight: 1.3 },
  "& .person-title": { fontSize: 11, color: "#374151", lineHeight: 1.3 },
  "& .chip-row": { display: "flex", gap: "8px", flexWrap: "wrap", padding: "8px 0" },
  "& .action-cell": { display: "flex", alignItems: "center", justifyContent: "center", gap: "8px", width: "100%" },
  "& .icon-btn": {
    border: `1px solid ${BORDER}`,
    borderRadius: "6px",
    color: MUTED,
    padding: "6px",
    background: "#fff",
    boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
    "&:hover": { color: TEAL, borderColor: TEAL, background: "#fff" },
  },
  "& .ag-center-header .ag-header-cell-label": { justifyContent: "center" },

    /* roles panel (after opening a team) */
  "& .roles-panel": {
    border: `1px solid ${BORDER}`,
    borderRadius: "8px",
    background: "#fff",
    overflow: "hidden",
  },
  "& .roles-toolbar": {
    display: "flex",
    justifyContent: "flex-end",
    alignItems: "center",
    gap: "10px",
    padding: "12px 16px",
    flexWrap: "wrap",
  },
  "& .roles-grid": { height: "calc(100vh - 260px)", minHeight: 420 },

  "& .role-cell": { display: "flex", alignItems: "center", gap: "14px" },
  "& .role-avatar": {
    width: 28,
    height: 28,
    borderRadius: "6px",
    background: "#e6f7f5",
    color: TEAL,
    fontSize: 11,
    fontWeight: 700,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  "& .role-name": { fontSize: 12, fontWeight: 600, color: "#111827" },
  "& .action-cell-end": { justifyContent: "flex-end" },
  "& .ag-right-aligned-header .ag-header-cell-label": { justifyContent: "flex-end" },

    /* team detail header */
  "& .detail-header": {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    padding: "12px 16px",
    marginBottom: "12px",
    background: "#f3f6f8",
  },
  "& .back-btn": {
    width: 28,
    height: 28,
    border: `1px solid ${BORDER}`,
    borderRadius: "6px",
    background: "#fff",
    color: "#111827",
    "&:hover": { background: "#fff", borderColor: TEAL, color: TEAL },
  },
  "& .detail-avatar": {
    width: 32,
    height: 32,
    borderRadius: "8px",
    background: "#e6f7f5",
    border: "1px solid #b8ebe4",
    color: TEAL,
    fontSize: 12,
    fontWeight: 700,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  "& .detail-titles": { flex: 1, minWidth: 0 },
  "& .detail-title": { margin: 0, fontSize: 18, fontWeight: 700, color: "#0f1729", lineHeight: 1.2 },
  "& .detail-subtitle": { margin: "2px 0 0", fontSize: 11, color: MUTED },
  "& .edit-btn": {
    color: TEAL,
    background: "#e6f7f5",
    border: "1px solid #b8ebe4",
    padding: "3px 12px",
    "&:hover": { background: "#d3f1ed" },
  },

  /* status / role pills */
  "& .pill": {
    display: "inline-block",
    padding: "2px 10px",
    borderRadius: "4px",
    fontSize: 11,
    fontWeight: 600,
    lineHeight: "18px",
  },
  "& .pill-role": { background: "#ede9fe", color: "#6d4fd6", border: "1px solid #ddd6fe" },
  "& .pill-active": { background: "#dcfce7", color: "#16a34a" },
  "& .pill-inactive": { background: "#f3f4f6", color: MUTED },
};