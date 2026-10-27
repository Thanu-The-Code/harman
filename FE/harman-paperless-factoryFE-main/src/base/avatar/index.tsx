import { Box } from "@mui/material";
import { avatarStackStyles, initialsAvatarStyles } from "./style";

interface AvatarProps {
  initials: string;
  size?: number;
  shape?: "square" | "circle";
  tone?: "teal" | "gray";
  className?: string;
}

export const InitialsAvatar = ({
  initials,
  size = 32,
  shape = "square",
  tone = "teal",
  className,
}: AvatarProps) => (
  <Box
    component="span"
    className={`avatar-${shape} tone-${tone} ${className ?? ""}`}
    title={initials.length > 3 ? initials : undefined}
    sx={{
      ...initialsAvatarStyles,
      width: size,
      height: size,
      // a longer code (a team's "E2EQA1") gets smaller type rather than spilling out
      fontSize: Math.round(size * (initials.length <= 2 ? 0.38 : Math.max(0.2, 0.9 / initials.length))),
      flexShrink: 0,
      overflow: "hidden",
      whiteSpace: "nowrap",
    }}
  >
    {initials}
  </Box>
);

interface StackProps {
  initials: string[];
  extra?: string; // e.g. "9+"
  size?: number;
}

export const AvatarStack = ({ initials, extra, size = 24 }: StackProps) => (
  <Box className="avatar-stack" sx={avatarStackStyles}>
    {initials.map((i, idx) => (
      <InitialsAvatar key={idx} initials={i} size={size} shape="circle" tone="gray" />
    ))}
    {extra && <InitialsAvatar initials={extra} size={size} shape="circle" tone="gray" />}
  </Box>
);