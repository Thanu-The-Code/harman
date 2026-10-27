import type { SxProps, Theme } from "@mui/material/styles";

export const initialsAvatarStyles: SxProps<Theme> = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  flexShrink: 0,
  fontWeight: 500,
  userSelect: "none",

  "&.avatar-square": { borderRadius: "8px" },
  "&.avatar-circle": { borderRadius: "50%" },
  "&.tone-teal": { background: "#d9f3ef", color: "#14b8a6", border: "1px solid #bfeae4" },
  "&.tone-gray": { background: "#eceff1", color: "#6b7280" },
};

export const avatarStackStyles: SxProps<Theme> = {
  display: "flex",
  alignItems: "center",
  gap: "4px",
};