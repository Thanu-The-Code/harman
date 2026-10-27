import type { SxProps, Theme } from "@mui/material/styles";

export const customChipStyles: SxProps<Theme> = {
  display: "inline-flex",
  alignItems: "center",
  fontSize: 11,
  fontWeight: 500,
  lineHeight: 1,
  padding: "5px 10px",
  borderRadius: "4px",
  border: "1px solid transparent",
  whiteSpace: "nowrap",

  "&.chip-blue": { background: "#e6f1ff", color: "#2b7de9", borderColor: "#cfe3fb" },
  "&.chip-purple": { background: "#f0eaff", color: "#7c3aed", borderColor: "#ddd0fb" },
  "&.chip-green": { background: "#e3f6ee", color: "#16a34a", borderColor: "#c9eddc" },
  "&.chip-orange": { background: "#fff1dc", color: "#f59e0b", borderColor: "#fbe2b8" },
  "&.chip-gray": { background: "#eceff1", color: "#6b7280", borderColor: "#dde1e4" },
};