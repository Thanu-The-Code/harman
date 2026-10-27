import type { SxProps, Theme } from "@mui/material/styles";

export const customTabsStyles: SxProps<Theme> = {
  minHeight: 46,
  "& .MuiTabs-indicator": { backgroundColor: "#14b8a6", height: 3 },
  "& .custom-tab": {
    textTransform: "none",
    fontSize: 13,
    fontWeight: 500,
    color: "#6b7280",
    minHeight: 46,
    minWidth: 0,
    padding: "0 16px",
    "&.Mui-selected": { color: "#14b8a6" },
  },
};