import type { SxProps, Theme } from "@mui/material/styles";

export const keyValueGridStyles: SxProps<Theme> = {
  display: "grid",
  gap: "0 24px",
  "@media (max-width: 700px)": { gridTemplateColumns: "1fr !important" },

  "& .kv-row": {
    display: "grid",
    gridTemplateColumns: "110px 1fr",
    padding: "9px 0",
    fontSize: 12,
    alignItems: "center",
  },
  "& .kv-label": { color: "#6b7280" },
  "& .kv-value": { color: "#111827", fontWeight: 600 },
};