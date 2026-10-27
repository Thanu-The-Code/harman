import type { SxProps, Theme } from "@mui/material/styles";

export const infoCardStyles: SxProps<Theme> = {
  background: "#fff",
  border: "1px solid #e5e7eb",
  borderRadius: "8px",
  overflow: "hidden",

  "& .info-card-head": {
    padding: "12px 16px",
    fontSize: 14,
    fontWeight: 600,
    color: "#0F172B",
    borderBottom: "1px solid #e5e7eb",
  },
  "& .info-card-body": { padding: "14px 16px" },
  "& .info-card-body.flush": { padding: 0 },
};