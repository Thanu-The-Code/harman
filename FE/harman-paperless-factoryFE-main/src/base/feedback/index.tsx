import { Box, Button, CircularProgress, Typography } from "@mui/material";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutlineOutlined";

/** Centred spinner for a page or panel that is loading. */
export const PageLoader = ({ label = "Loading…", fullScreen = false }: { label?: string; fullScreen?: boolean }) => (
  <Box
    role="status"
    sx={{
      minHeight: fullScreen ? "100vh" : 240,
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      gap: 1.5,
      color: "#6b7280",
    }}
  >
    <CircularProgress size={28} sx={{ color: "#14b8a6" }} />
    <Typography sx={{ fontSize: 13 }}>{label}</Typography>
  </Box>
);

/** A failed load, with a retry when the caller can offer one. */
export const ErrorState = ({ message, onRetry }: { message: string; onRetry?: () => void }) => (
  <Box
    role="alert"
    sx={{
      minHeight: 200,
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      gap: 1,
      color: "#6b7280",
      textAlign: "center",
      p: 3,
    }}
  >
    <ErrorOutlineIcon sx={{ color: "#ef4444" }} />
    <Typography sx={{ fontSize: 14, color: "#111827" }}>{message}</Typography>
    {onRetry && (
      <Button size="small" onClick={onRetry} sx={{ textTransform: "none", color: "#14b8a6" }}>
        Try again
      </Button>
    )}
  </Box>
);
