import type { SxProps, Theme } from "@mui/material/styles";

const TEAL = "#14b8a6";
const BORDER = "#e5e7eb";
const MUTED = "#6b7280";

export const designerStyles: SxProps<Theme> = {
  p: 2.5,
  bgcolor: "#f3f9f9",
  minHeight: "100%",
  fontFamily: '"Plus Jakarta Sans", "Inter", Roboto, sans-serif',

  "& .designer-header": {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 2,
    mb: 2,
    flexWrap: "wrap",
  },
  "& .designer-title": { display: "flex", alignItems: "center", gap: 1.25 },
  "& .designer-title h1": { m: 0, fontSize: 20, fontWeight: 700, color: "#111827" },
  "& .designer-actions": { display: "flex", gap: 1, flexWrap: "wrap" },
  "& .designer-actions .MuiButton-root": { textTransform: "none", fontWeight: 600, boxShadow: "none" },
  "& .btn-primary": { bgcolor: TEAL, "&:hover": { bgcolor: "#0f9e8e" } },
  "& .btn-outline": { color: "#374151", borderColor: BORDER, bgcolor: "#fff" },

  "& .status-chip": {
    fontSize: 12,
    fontWeight: 600,
    px: 1.25,
    py: 0.25,
    borderRadius: 999,
    bgcolor: "#e6f7f5",
    color: "#0f766e",
  },
  "& .status-chip.in_review": { bgcolor: "#fef3c7", color: "#b45309" },
  "& .status-chip.rejected": { bgcolor: "#fee2e2", color: "#b91c1c" },

  "& .designer-card": {
    bgcolor: "#fff",
    border: `1px solid ${BORDER}`,
    borderRadius: "8px",
    p: 2,
    mb: 2,
  },
  "& .card-title": { m: "0 0 4px", fontSize: 15, fontWeight: 600, color: "#111827" },
  "& .card-caption": { m: "0 0 14px", fontSize: 12, color: MUTED },
  "& .field-grid": {
    display: "grid",
    gap: 2,
    gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" },
  },
  "& .field-grid .span-2": { gridColumn: { md: "1 / -1" } },
  "& .field-grid-3": {
    display: "grid",
    gap: 2,
    gridTemplateColumns: { xs: "1fr", md: "1fr 1fr 1fr" },
  },

  "& .notice": {
    display: "flex",
    gap: 1,
    alignItems: "flex-start",
    p: 1.5,
    mb: 2,
    borderRadius: "8px",
    fontSize: 13,
    lineHeight: 1.5,
  },
  "& .notice.warn": { bgcolor: "#fffbeb", border: "1px solid #fde68a", color: "#92400e" },
  "& .notice.info": { bgcolor: "#eff6ff", border: "1px solid #bfdbfe", color: "#1e40af" },
  "& .notice ul": { m: "4px 0 0", pl: 2.5 },

  "& .limits-table": { width: "100%", borderCollapse: "collapse", fontSize: 13 },
  "& .limits-table th": {
    textAlign: "left",
    fontWeight: 600,
    color: "#374151",
    bgcolor: "#f7f8fa",
    p: "8px 10px",
    borderBottom: `1px solid ${BORDER}`,
  },
  "& .limits-table td": { p: "6px 10px", borderBottom: `1px solid ${BORDER}`, verticalAlign: "middle" },
  "& .limits-table input": {
    width: "100%",
    boxSizing: "border-box",
    border: `1px solid ${BORDER}`,
    borderRadius: "6px",
    p: "6px 8px",
    fontSize: 13,
  },
  "& .muted": { color: MUTED, fontSize: 12 },

  "& .blank-row": { display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap", fontSize: 13 },

  "& .builder-wrapper": {
    bgcolor: "#fff",
    border: `1px solid ${BORDER}`,
    borderRadius: "8px",
    p: 2,
  },
};
