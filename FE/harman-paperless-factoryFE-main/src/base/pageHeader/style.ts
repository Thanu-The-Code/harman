import type { SxProps, Theme } from "@mui/material/styles";

export const pageHeaderStyles: SxProps<Theme> = {
  display: "flex",
  alignItems: "center",
  gap: "16px",
  padding: "12px 24px",
  background: "#f1f3f5",

  "& .back-btn": {
    width: 38,
    height: 38,
    border: "1px solid #e5e7eb",
    borderRadius: "8px",
    background: "#fff",
    color: "#111827",
    boxShadow: "0 1px 2px rgba(0,0,0,0.06)",
    "&:hover": { background: "#fff", borderColor: "#14b8a6", color: "#14b8a6" },
  },
  "& .page-heading": { flex: 1, minWidth: 0 },
  "& .page-title": { fontSize: 20, fontWeight: 700, margin: 0, lineHeight: 1.25, color: "#111827" },
  "& .page-subtitle": { fontSize: 13, color: "#6b7280", margin: "2px 0 0" },
  "& .page-actions": { display: "flex", gap: "10px", flexShrink: 0 },
};